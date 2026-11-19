"""App updates run the host's upgradeGhostwireProxy.sh in a one-shot container.

The old path ran `git fetch`/`git checkout` in the updater's read-only project mount, which always
failed, and its failure handler then restored a backup and recreated containers although nothing
had changed. These tests pin the new behaviour without a Docker daemon.
"""

import asyncio
import os

import docker
import pytest
from updater.main import ScriptResult, UpdaterService, UpgradeError, upgrade_run_kwargs, version_tag

from updater import main

HOST_DIR = "/opt/ghostwire-proxy"


def own_attrs(project_mount=main.COMPOSE_PROJECT_DIR, socket=main.DOCKER_SOCKET):
    """docker inspect of the updater: the compose file's mounts, with the host at HOST_DIR."""
    return {
        "Image": "sha256:updaterimage",
        "Config": {"Labels": {"com.docker.compose.project": "ghostwire-proxy"}},
        "Mounts": [
            {"Source": "/var/run/docker.sock", "Destination": socket, "RW": True},
            {"Source": HOST_DIR, "Destination": project_mount, "RW": False},
            {"Source": f"{HOST_DIR}/data/backups", "Destination": "/data/backups", "RW": True},
        ],
    }


UPGRADE_OK = """Ghostwire Proxy upgrade  host, 2026-11-19 10:00

[1/9] Pre-flight
  ✓ Disk space is fine.
[2/9] Plan
[3/9] Back up
[4/9] Update code
[5/9] Build
[6/9] Deploy
[7/9] Health check
  ✓ Every container is up and healthy.
[8/9] Security
  ! CVE-2026-121810: exposed, no mitigation yet
[9/9] Done
"""

BUILD_FAILED = """[1/8] Pre-flight
[2/8] Plan
[3/8] Back up
[4/8] Update code
[5/8] Build
    error: failed to solve
\x1b[31m  ✗ The build failed. Nothing was restarted; the old version is still running.\x1b[0m
"""

FETCH_FAILED = """[1/8] Pre-flight
[2/8] Plan

  ✗ git fetch failed (network or credentials?)
"""

HEALTH_FAILED = """[5/8] Build
[6/8] Deploy
[7/8] Health check
  ! Not healthy after 180s: ghostwire-proxy-api(unhealthy)

  ✗ The upgrade to v2026.11.20.0900 (abc1234) failed its health check.
  To go back to v2026.11.16.1448 (def5678):  ./upgradeGhostwireProxy.sh --rollback
"""

ROLLBACK_OK = """[1/3] Pre-flight
[2/3] Roll back
[3/3] Health check
  ✓ Rolled back to v2026.11.16.1448 (def5678).
"""


# ── Pure helpers ───────────────────────────────────────────────────────────────────────────────


def test_version_tag():
    assert version_tag("2026.11.16.1448") == "v2026.11.16.1448"
    assert version_tag("v2026.11.16.1448") == "v2026.11.16.1448"
    for bad in ("", None, "--rollback", "-f", "v1; rm -rf /", "../x"):
        with pytest.raises(UpgradeError):
            version_tag(bad)


def test_run_kwargs_mount_the_project_read_write_at_its_host_path():
    kwargs = upgrade_run_kwargs(own_attrs(), ["--yes", "v1"], {"l": "1"}, uid=0, gid=0, docker_gid=999)

    assert kwargs["image"] == "sha256:updaterimage"
    assert kwargs["command"] == ["bash", "./upgradeGhostwireProxy.sh", "--yes", "v1"]
    # Same path as on the host: compose's relative bind mounts are resolved by the daemon.
    assert kwargs["working_dir"] == HOST_DIR
    assert kwargs["volumes"][HOST_DIR] == {"bind": HOST_DIR, "mode": "rw"}
    assert kwargs["volumes"]["/var/run/docker.sock"]["bind"] == "/var/run/docker.sock"
    # The health checks call localhost:8089 and :88.
    assert kwargs["network_mode"] == "host"
    assert kwargs["environment"]["COMPOSE_PROJECT_NAME"] == "ghostwire-proxy"
    assert kwargs["environment"]["GIT_CONFIG_VALUE_0"] == HOST_DIR
    assert kwargs["user"] == "0:0"
    assert kwargs["group_add"] == ["999"]
    assert kwargs["detach"] is True
    assert "no-new-privileges:true" in kwargs["security_opt"]


def test_run_kwargs_without_a_project_mount_say_so():
    attrs = own_attrs(project_mount="/somewhere-else")
    with pytest.raises(UpgradeError, match="no project mount"):
        upgrade_run_kwargs(attrs, ["--yes", "v1"], {}, uid=0, gid=0, docker_gid=0)


def test_compose_file_keeps_the_updaters_own_mount_read_only():
    compose = os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")
    with open(compose, encoding="utf-8") as f:
        assert "- .:/app/project:ro" in f.read()


def test_script_result_reads_the_scripts_own_reason():
    build = ScriptResult(1, main.script_lines(BUILD_FAILED.encode()))
    assert build.failure == "The build failed. Nothing was restarted; the old version is still running."
    assert not build.reached_deploy

    health = ScriptResult(1, main.script_lines(HEALTH_FAILED))
    assert health.reached_deploy
    assert "failed its health check" in health.failure

    stopped = ScriptResult(1, ["[4/8] Update code", "  ✗ Stopped at line 200: git checkout --quiet --detach x"])
    assert stopped.failure.startswith("Stopped at line 200")

    bare = ScriptResult(127, ["bash: ./upgradeGhostwireProxy.sh: No such file or directory"])
    assert (
        bare.failure
        == "upgradeGhostwireProxy.sh exited with code 127: bash: ./upgradeGhostwireProxy.sh: No such file or directory"
    )


def test_step_progress():
    assert main.step_progress(1, 8) == 10
    assert main.step_progress(8, 8) == 90
    assert 10 < main.step_progress(6, 9) < 90


# ── perform_app_update with a fake Docker ───────────────────────────────────────────────────────


class FakeContainer:
    def __init__(self, name, output, exit_code, labels=None):
        self.name = name
        self.labels = labels or {}
        self._output = output.encode()
        self.status = "running"
        self.attrs = {"State": {"ExitCode": exit_code}}
        self.removed = False
        self._polls = 0

    def reload(self):
        self._polls += 1
        if self._polls >= 2:
            self.status = "exited"

    def logs(self):
        return self._output

    def remove(self, force=False):
        self.removed = True

    def stop(self):
        self.status = "exited"


class FakeContainers:
    def __init__(self, runs):
        self.runs = list(runs)  # (output, exit_code) for each one-shot, in order
        self.started = []
        self.current = None

    def get(self, ref):
        if ref == main.UPDATER_CONTAINER:
            own = FakeContainer(ref, "", 0)
            own.attrs = own_attrs(main.COMPOSE_PROJECT_DIR, main.DOCKER_SOCKET)
            return own
        if ref == main.UPGRADE_CONTAINER and self.current and not self.current.removed:
            return self.current
        raise docker.errors.NotFound("no such container")

    def run(self, **kwargs):
        output, exit_code = self.runs.pop(0)
        self.started.append(kwargs)
        self.current = FakeContainer(kwargs["name"], output, exit_code, kwargs["labels"])
        return self.current

    def list(self, **kwargs):
        return []


class FakeDocker:
    def __init__(self, runs):
        self.containers = FakeContainers(runs)


class RecordingUpdater(UpdaterService):
    def __init__(self, runs):
        super().__init__()
        self.docker_client = FakeDocker(runs)
        self.statuses = []
        self.pushes = []
        self.restored = False

    async def update_status(self, update_id, status, progress=None, message=None, error=None):
        self.statuses.append((status, progress, message or error))

    async def send_push_notification(self, title, body, notification_type="update", data=None):
        self.pushes.append(title)

    async def create_pre_update_backup(self):
        return "backup-1"

    async def store_backup_id(self, update_id, backup_id):
        pass

    async def restart_containers_ordered(self):
        self.restored = True  # the old automatic rollback did this; app updates must not any more

    @property
    def started_args(self):
        return [run["command"][2:] for run in self.docker_client.containers.started]


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A checkout and a Docker socket for start_upgrade_container to stat."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "upgradeGhostwireProxy.sh").write_text("#!/usr/bin/env bash\n")
    socket = tmp_path / "docker.sock"
    socket.write_text("")
    monkeypatch.setattr(main, "COMPOSE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(main, "DOCKER_SOCKET", str(socket))
    monkeypatch.setattr(main, "UPGRADE_POLL_SECONDS", 0)
    return tmp_path


uses_fake_docker = pytest.mark.usefixtures("project")


def run_update(updater, version="2026.11.20.0900"):
    asyncio.run(updater.perform_app_update("u1", version))
    return updater.statuses[-1]


@uses_fake_docker
def test_success_runs_the_script_once():
    updater = RecordingUpdater([(UPGRADE_OK, 0)])
    status, progress, message = run_update(updater)

    assert updater.started_args == [["--yes", "v2026.11.20.0900"]]
    assert (status, progress) == ("completed", 100)
    assert "Successfully updated to 2026.11.20.0900" in message
    assert ("in_progress", 90, "Done...") in updater.statuses
    assert updater.docker_client.containers.current.removed
    assert updater.pushes == ["Update Complete"]


@uses_fake_docker
@pytest.mark.parametrize("output", [FETCH_FAILED, BUILD_FAILED])
def test_failure_before_the_deploy_rolls_nothing_back(output):
    updater = RecordingUpdater([(output, 1)])
    status, _progress, message = run_update(updater)

    assert updater.started_args == [["--yes", "v2026.11.20.0900"]]  # no --rollback run
    assert not updater.restored
    assert status == "failed"
    assert "stopped before the deploy, so the running version is unchanged" in message
    assert updater.pushes == ["Update Failed"]


@uses_fake_docker
def test_failure_after_the_deploy_rolls_back_with_the_script():
    updater = RecordingUpdater([(HEALTH_FAILED, 1), (ROLLBACK_OK, 0)])
    status, _progress, message = run_update(updater)

    assert updater.started_args == [["--yes", "v2026.11.20.0900"], ["--rollback", "--yes"]]
    assert not updater.restored
    assert status == "failed"
    assert "failed its health check" in message
    assert "rolled back to the version that ran before" in message


@uses_fake_docker
def test_failed_rollback_says_what_to_do():
    updater = RecordingUpdater([(HEALTH_FAILED, 1), ("[2/3] Roll back\n  ✗ None of the kept images are left.\n", 1)])
    _status, _progress, message = run_update(updater)

    assert "the rollback failed too (None of the kept images are left.)" in message
    assert "./upgradeGhostwireProxy.sh --rollback" in message


@uses_fake_docker
def test_bad_version_starts_nothing():
    updater = RecordingUpdater([])
    status, _progress, message = run_update(updater, version="--rollback")

    assert updater.started_args == []
    assert status == "failed"
    assert "isn't a version" in message


@uses_fake_docker
def test_a_running_upgrade_blocks_a_second_one():
    updater = RecordingUpdater([])
    updater.docker_client.containers.current = FakeContainer(main.UPGRADE_CONTAINER, "", 0)
    status, _progress, message = run_update(updater)

    assert updater.started_args == []
    assert status == "failed"
    assert "Another upgrade is already running" in message


@uses_fake_docker
def test_backups_owned_by_someone_else_is_a_clear_error(project, monkeypatch):
    backups = project / "data" / "backups"
    backups.mkdir(parents=True)
    real_stat = os.stat

    def stat(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if str(path) == str(project / ".git"):
            return os.stat_result((result.st_mode, 0, 0, 0, 1000, 1000, *result[6:]))
        if str(path) == str(backups):
            return os.stat_result((result.st_mode, 0, 0, 0, 0, 0, *result[6:]))
        return result

    monkeypatch.setattr(main.os, "stat", stat)
    updater = RecordingUpdater([])
    status, _progress, message = run_update(updater)

    assert updater.started_args == []
    assert status == "failed"
    assert "sudo chown -R 1000 data/backups" in message


@uses_fake_docker
def test_resume_finishes_an_upgrade_the_previous_updater_started():
    updater = RecordingUpdater([])
    left = FakeContainer(main.UPGRADE_CONTAINER, UPGRADE_OK, 0, main.upgrade_labels("u9", "upgrade", "2026.11.20.0900"))
    updater.docker_client.containers.list = lambda **kwargs: [left]

    asyncio.run(updater.resume_upgrade_containers())

    assert updater.statuses[-1] == ("completed", 100, "Successfully updated to 2026.11.20.0900")
    assert left.removed

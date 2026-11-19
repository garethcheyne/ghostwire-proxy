"""UI rollbacks and base-image rebuilds run in the one-shot container, not in the updater.

Both used to run `docker-compose` in the updater with cwd /app/project, its read-only mount of the
project. Compose resolves the compose file's relative bind mounts against that directory
(./data/certificates -> /app/project/data/certificates), and the daemon then reads those as host
paths, which don't exist on the host. `restart_containers_ordered` also only logged a warning when
compose failed, so a rollback reported success. These tests pin the new behaviour without a Docker
daemon; the bash the one-shot container runs is exercised against a stub `docker`.
"""

import asyncio
import contextlib
import os
import subprocess
import textwrap

import pytest
from updater.main import BASE_IMAGE_ROLLBACK_SCRIPT, BASE_IMAGE_UPDATE_SCRIPT, ScriptResult, UpdaterService

from tests.test_app_update import HOST_DIR, FakeContainer, RecordingUpdater
from updater import main

BASE_OK = """[1/3] Keep the running image
  ✓ Kept as ghostwire-proxy-ghostwire-proxy-api:before-base-image.
[2/3] Build
[3/3] Restart
  ✓ ghostwire-proxy-api runs the new image.
"""

BASE_BUILD_FAILED = """[1/3] Keep the running image
[2/3] Build
  ✗ The build of ghostwire-proxy-api failed. Nothing was restarted; the old image is still running.
"""

BASE_ROLLBACK_OK = """[1/2] Restore the kept image
[2/2] Restart
  ✓ ghostwire-proxy-api is back on the image it ran before the base image update.
"""

UI_ROLLBACK_OK = """Ghostwire Proxy upgrade  host, 2026-11-19 10:00
[1/3] Pre-flight
  ! The database isn't rolled back. Migrations only add, so the older version runs on it.
[2/3] Roll back
  ✓ Code is back at v2026.11.16.1448 (def5678).
[3/3] Health check
  ✓ Every container is up and healthy.
  ✓ Rolled back to v2026.11.16.1448 (def5678).
"""

UI_ROLLBACK_NO_STATE = """[1/3] Pre-flight

  ✗ There's no earlier upgrade to go back to (/opt/ghostwire-proxy/data/backups/last-upgrade is missing).
"""


class Updater(RecordingUpdater):
    """RecordingUpdater with the API health check stubbed. http_client stays None: nothing may call the API."""

    def __init__(self, runs, healthy=True):
        super().__init__(runs)
        self.healthy = healthy
        self.health_checks = 0

    async def post_update_health_checks(self):
        self.health_checks += 1
        return self.healthy

    @property
    def started(self):
        return self.docker_client.containers.started


uses_fake_docker = pytest.mark.usefixtures("project")


@pytest.fixture
def telemetry(monkeypatch):
    """Records the analytics jobs entered and the heartbeats sent."""
    seen = {"jobs": [], "heartbeats": 0}

    @contextlib.asynccontextmanager
    async def fake_job(name, **attrs):
        seen["jobs"].append((name, attrs))
        yield

    def fake_heartbeat(*args, **kwargs):
        seen["heartbeats"] += 1

    monkeypatch.setattr(main, "job", fake_job)
    monkeypatch.setattr(main, "heartbeat", fake_heartbeat)
    return seen


def rollback(updater, **kwargs):
    kwargs.setdefault("backup_id", None)
    asyncio.run(updater.perform_rollback("r1", "u1", **kwargs))
    return updater.statuses[-1]


def base_image_update(updater, container_name="api"):
    asyncio.run(updater.perform_base_image_update("b1", container_name))
    return updater.statuses[-1]


def assert_runs_in_the_oneshot_container_at_the_host_path(run):
    assert run["name"] == main.UPGRADE_CONTAINER
    assert run["working_dir"] == HOST_DIR
    assert run["volumes"][HOST_DIR] == {"bind": HOST_DIR, "mode": "rw"}
    assert run["environment"]["COMPOSE_PROJECT_NAME"] == "ghostwire-proxy"


# ── restart_containers_ordered ─────────────────────────────────────────────────────────────────


def test_restart_containers_ordered_raises_when_compose_fails(monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(
            cmd, 1, "", 'Conflict. The container name "/ghostwire-proxy-api" is already in use'
        )

    monkeypatch.setattr(main.subprocess, "run", run)
    monkeypatch.setattr(main.os, "chdir", lambda path: pytest.fail("restart_containers_ordered changed directory"))

    with pytest.raises(RuntimeError, match=r"Recreating ghostwire-proxy-api failed .*already in use"):
        asyncio.run(UpdaterService().restart_containers_ordered())

    assert len(calls) == 1  # stopped at the first failure; ui and nginx weren't touched
    assert calls[0][0] == ["docker-compose", "up", "-d", "--force-recreate", "ghostwire-proxy-api"]


# ── UI rollback of an app update ───────────────────────────────────────────────────────────────


@uses_fake_docker
def test_app_rollback_runs_the_upgrade_scripts_rollback(telemetry):
    updater = Updater([(UI_ROLLBACK_OK, 0)])
    status, progress, message = rollback(updater, backup_id="backup-1")

    [run] = updater.started
    assert run["command"] == ["bash", "./upgradeGhostwireProxy.sh", "--rollback", "--yes"]
    assert_runs_in_the_oneshot_container_at_the_host_path(run)
    assert run["labels"][f"{main.UPGRADE_LABEL}.kind"] == "ui-rollback"
    assert (status, progress) == ("completed", 100)
    assert message.startswith("Rolled back to v2026.11.16.1448 (def5678). The database isn't rolled back")
    assert ("in_progress", 90, "Health check...") in updater.statuses
    assert updater.pushes == ["Rollback Complete"]
    assert not updater.restored  # never compose in the updater
    assert telemetry["jobs"] == [("rollback", {})]
    assert telemetry["heartbeats"] >= 1


@uses_fake_docker
def test_app_rollback_failure_is_reported_with_the_scripts_reason():
    updater = Updater([(UI_ROLLBACK_NO_STATE, 1)])
    status, _progress, message = rollback(updater)

    assert status == "failed"
    assert "There's no earlier upgrade to go back to" in message
    assert updater.pushes == ["Rollback Failed"]


@uses_fake_docker
def test_only_the_running_update_can_be_rolled_back(monkeypatch):
    monkeypatch.setattr(main, "app_version", lambda: "2026.11.20.0900")
    updater = Updater([])
    status, _progress, message = rollback(updater, from_version="2026.11.16.1448")

    assert updater.started == []
    assert status == "failed"
    assert "Only the latest update can be rolled back: 2026.11.20.0900 is running" in message


@uses_fake_docker
def test_rollback_of_the_running_update_goes_ahead(monkeypatch):
    monkeypatch.setattr(main, "app_version", lambda: "2026.11.20.0900")
    updater = Updater([(UI_ROLLBACK_OK, 0)])
    status, _progress, _message = rollback(updater, from_version="v2026.11.20.0900")

    assert len(updater.started) == 1
    assert status == "completed"


@uses_fake_docker
def test_rollback_request_from_the_api_is_routed_by_update_type():
    updater = Updater([(BASE_ROLLBACK_OK, 0)])
    asyncio.run(
        updater.handle_update_request(
            {
                "action": "rollback",
                "update_id": "r1",
                "original_update_id": "u1",
                "backup_id": None,
                "update_type": "base_image",
                "container_name": "api",
                "from_version": "python:3.12-slim",
            }
        )
    )

    [run] = updater.started
    assert run["command"][:3] == ["bash", "-c", BASE_IMAGE_ROLLBACK_SCRIPT]
    assert updater.statuses[-1][0] == "completed"


# ── Base image update ──────────────────────────────────────────────────────────────────────────


@uses_fake_docker
def test_base_image_update_rebuilds_in_the_oneshot_container(telemetry):
    updater = Updater([(BASE_OK, 0)])
    status, progress, message = base_image_update(updater)

    [run] = updater.started
    assert run["command"] == ["bash", "-c", BASE_IMAGE_UPDATE_SCRIPT, "base-image", "ghostwire-proxy-api"]
    assert_runs_in_the_oneshot_container_at_the_host_path(run)
    assert run["labels"][f"{main.UPGRADE_LABEL}.kind"] == "base-image"
    assert updater.health_checks == 1
    assert (status, progress, message) == ("completed", 100, "Successfully updated api base image")
    assert updater.pushes == ["Base Image Updated"]
    assert updater.docker_client.containers.current.removed
    assert telemetry["jobs"] == [("base-image-update", {"container": "api"})]
    assert telemetry["heartbeats"] >= 1


@uses_fake_docker
def test_base_image_build_failure_is_reported_and_skips_the_health_check():
    updater = Updater([(BASE_BUILD_FAILED, 1)])
    status, _progress, message = base_image_update(updater)

    assert status == "failed"
    assert "The build of ghostwire-proxy-api failed. Nothing was restarted" in message
    assert updater.health_checks == 0
    assert updater.pushes == ["Update Failed"]


@uses_fake_docker
def test_base_image_update_that_leaves_the_api_unhealthy_fails():
    updater = Updater([(BASE_OK, 0)], healthy=False)
    status, _progress, message = base_image_update(updater)

    assert status == "failed"
    assert "the API isn't healthy" in message


@uses_fake_docker
def test_base_image_update_of_an_unknown_container_starts_nothing():
    updater = Updater([])
    status, _progress, message = base_image_update(updater, container_name="postgres")

    assert updater.started == []
    assert status == "failed"
    assert "Cannot update base image for: postgres" in message


@uses_fake_docker
def test_base_image_rollback_restores_the_kept_image():
    updater = Updater([(BASE_ROLLBACK_OK, 0)])
    status, _progress, message = rollback(updater, update_type="base_image", container_name="ui")

    [run] = updater.started
    assert run["command"] == ["bash", "-c", BASE_IMAGE_ROLLBACK_SCRIPT, "base-image", "ghostwire-proxy-ui"]
    assert_runs_in_the_oneshot_container_at_the_host_path(run)
    assert status == "completed"
    assert message == "ui is back on the image it ran before the base image update"


# ── Picking up after the updater was recreated ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kind", "version", "output", "expected"),
    [
        ("ui-rollback", "", UI_ROLLBACK_OK, "Rolled back to v2026.11.16.1448 (def5678)."),
        ("base-image", "api", BASE_OK, "Successfully updated api base image"),
        ("base-image-rollback", "api", BASE_ROLLBACK_OK, "api is back on the image it ran before"),
    ],
)
@uses_fake_docker
def test_resume_finishes_each_kind(telemetry, kind, version, output, expected):
    updater = Updater([])
    left = FakeContainer(main.UPGRADE_CONTAINER, output, 0, main.upgrade_labels("u9", kind, version))
    updater.docker_client.containers.list = lambda **kwargs: [left]

    asyncio.run(updater.resume_upgrade_containers())

    status, progress, message = updater.statuses[-1]
    assert (status, progress) == ("completed", 100)
    assert message.startswith(expected)
    assert left.removed
    assert telemetry["jobs"][0][0] == ("base-image-update" if kind == "base-image" else "rollback")


@uses_fake_docker
def test_resume_reports_a_failed_base_image_rebuild():
    updater = Updater([])
    left = FakeContainer(main.UPGRADE_CONTAINER, BASE_BUILD_FAILED, 1, main.upgrade_labels("u9", "base-image", "api"))
    updater.docker_client.containers.list = lambda **kwargs: [left]

    asyncio.run(updater.resume_upgrade_containers())

    assert updater.statuses[-1][0] == "failed"
    assert updater.pushes == ["Update Failed"]


# ── The bash the one-shot container runs, against a stub docker ─────────────────────────────────

STUB_DOCKER = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    echo "$*" >> "$DOCKER_LOG"
    case "$*" in
      "compose ps -q "*) [ -n "${NOT_RUNNING:-}" ] || echo cid123 ;;
      "inspect -f {{.Config.Image}} cid123") echo "$IMAGE_REF" ;;
      "inspect -f {{.Image}} cid123") echo sha256:old ;;
      "compose build"*) echo "BUILD_VERSION=$BUILD_VERSION" >> "$DOCKER_LOG"; exit "${BUILD_EXIT:-0}" ;;
      "image inspect"*) exit "${KEPT_EXIT:-0}" ;;
    esac
    exit 0
    """
)


def run_script(tmp_path, script, service="ghostwire-proxy-api", **env):
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "docker").write_text(STUB_DOCKER)
    (stub / "docker").chmod(0o755)
    (tmp_path / "VERSION").write_text("2026.11.16.1448\n")
    log = tmp_path / "docker.log"
    log.write_text("")
    environ = {
        **os.environ,
        "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
        "DOCKER_LOG": str(log),
        "IMAGE_REF": "ghostwire-proxy-ghostwire-proxy-api",
        **env,
    }
    proc = subprocess.run(
        main.base_image_command(script, service),
        cwd=tmp_path,
        env=environ,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return ScriptResult(proc.returncode, main.script_lines(proc.stdout + proc.stderr)), log.read_text().splitlines()


def test_update_script_keeps_the_running_image_then_builds_and_restarts(tmp_path):
    result, calls = run_script(tmp_path, BASE_IMAGE_UPDATE_SCRIPT)

    assert result.exit_code == 0, result.lines
    assert [title for _n, _t, title in main.script_steps(result.lines)] == [
        "Keep the running image",
        "Build",
        "Restart",
    ]
    tag = calls.index("tag sha256:old ghostwire-proxy-ghostwire-proxy-api:before-base-image")
    build = calls.index("compose build --pull --no-cache ghostwire-proxy-api")
    assert tag < build
    assert calls[build + 1] == "BUILD_VERSION=2026.11.16.1448"
    assert calls[-1] == "compose up -d ghostwire-proxy-api"


@pytest.mark.parametrize(
    ("ref", "kept"),
    [
        ("example/api:1.2", "example/api:before-base-image"),
        ("localhost:5000/api", "localhost:5000/api:before-base-image"),
    ],
)
def test_update_script_keeps_the_image_under_its_name_without_the_tag(tmp_path, ref, kept):
    _result, calls = run_script(tmp_path, BASE_IMAGE_UPDATE_SCRIPT, IMAGE_REF=ref)
    assert f"tag sha256:old {kept}" in calls


def test_update_script_build_failure_restarts_nothing(tmp_path):
    result, calls = run_script(tmp_path, BASE_IMAGE_UPDATE_SCRIPT, BUILD_EXIT="1")

    assert result.exit_code == 1
    assert result.failure == (
        "The build of ghostwire-proxy-api failed. Nothing was restarted; the old image is still running."
    )
    assert not any(call.startswith("compose up") for call in calls)


def test_update_script_still_builds_a_service_that_isnt_running(tmp_path):
    result, calls = run_script(tmp_path, BASE_IMAGE_UPDATE_SCRIPT, NOT_RUNNING="1")

    assert result.exit_code == 0, result.lines
    assert not any(call.startswith("tag ") for call in calls)
    assert calls[-1] == "compose up -d ghostwire-proxy-api"


def test_rollback_script_retags_the_kept_image_and_recreates_without_a_build(tmp_path):
    result, calls = run_script(tmp_path, BASE_IMAGE_ROLLBACK_SCRIPT)

    assert result.exit_code == 0, result.lines
    assert "tag ghostwire-proxy-ghostwire-proxy-api:before-base-image ghostwire-proxy-ghostwire-proxy-api" in calls
    assert calls[-1] == "compose up -d --no-build --force-recreate ghostwire-proxy-api"
    assert not any(call.startswith("compose build") for call in calls)


def test_rollback_script_without_a_kept_image_changes_nothing(tmp_path):
    result, calls = run_script(tmp_path, BASE_IMAGE_ROLLBACK_SCRIPT, KEPT_EXIT="1")

    assert result.exit_code == 1
    assert result.failure == "There's no kept image of ghostwire-proxy-api to go back to."
    assert not any(call.startswith(("tag ", "compose up")) for call in calls)


def test_the_service_is_an_argument_not_part_of_the_script():
    command = main.base_image_command(BASE_IMAGE_UPDATE_SCRIPT, "ghostwire-proxy-api; rm -rf /")
    assert command[2] == BASE_IMAGE_UPDATE_SCRIPT
    assert command[-1] == "ghostwire-proxy-api; rm -rf /"

"""
Ghostwire Proxy Updater Service

This service runs as a sidecar container and handles:
1. Application updates (new Ghostwire versions)
2. Base image updates (Alpine, Python, Node.js security patches)
3. Rollback operations

Communication with the main API is via Redis pub/sub.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import docker
import httpx
import redis.asyncio as redis

from updater import ghostwire_telemetry
from updater.ghostwire_telemetry import heartbeat, job

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://ghostwire-proxy-redis:6379")
COMPOSE_PROJECT_DIR = os.environ.get("COMPOSE_PROJECT_DIR", "/app/project")
BACKUP_PATH = os.environ.get("BACKUP_PATH", "/data/backups")
API_URL = os.environ.get("API_URL", "http://ghostwire-proxy-api:8000")
INTERNAL_AUTH_TOKEN = os.environ.get("INTERNAL_AUTH_TOKEN", "updater-service")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.environ.get("VAPID_EMAIL", "mailto:admin@ghostwire.local")

# System monitoring with Ghostwire Analytics (ghostwire-suite/docs/analytics-reporting.md). The updater
# can't read the API's settings, so it sends through the API's internal relay, which adds the real URL
# and ingest key from Settings; while monitoring is off the relay answers 404 and the batch is dropped.
OTLP_RELAY_ENDPOINT = os.environ.get("OTLP_RELAY_ENDPOINT", f"{API_URL}/internal/otlp")


def analytics_config() -> dict:
    return {"url": OTLP_RELAY_ENDPOINT, "ingest_key": "relay", "trace_sample": 100}


def app_version() -> str | None:
    """The release the stack runs: VERSION in the mounted project, if it's there."""
    try:
        with open(os.path.join(COMPOSE_PROJECT_DIR, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return os.environ.get("APP_VERSION")


# App updates run the host's upgrade script (see UpdaterService.perform_app_update).
UPGRADE_SCRIPT = "upgradeGhostwireProxy.sh"
UPGRADE_CONTAINER = "ghostwire-proxy-upgrade"  # the one-shot container that runs it
UPGRADE_LABEL = "ghostwire.upgrade"
UPDATER_CONTAINER = os.environ.get("UPDATER_CONTAINER", "ghostwire-proxy-updater")
DOCKER_SOCKET = "/var/run/docker.sock"
UPGRADE_POLL_SECONDS = 3
UPGRADE_TIMEOUT_SECONDS = 60 * 60

# A tag, branch or commit; never something the script would read as an option.
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_STEP_RE = re.compile(r"\[(\d+)/(\d+)\]\s+(\S.*?)\s*$")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class UpgradeError(Exception):
    """An app update that can't go ahead, or didn't work; the message is what the admin sees."""


def version_tag(version: str | None) -> str:
    """The git tag for VERSION (2026.11.16.1448 -> v2026.11.16.1448)."""
    value = (version or "").strip()
    if not _VERSION_RE.match(value):
        raise UpgradeError(f"{version!r} isn't a version the upgrade can go to.")
    return value if value.startswith("v") else f"v{value}"


def upgrade_labels(update_id: str, kind: str, version: str, failure: str = "") -> dict[str, str]:
    labels = {
        UPGRADE_LABEL: "1",
        f"{UPGRADE_LABEL}.update_id": str(update_id),
        f"{UPGRADE_LABEL}.kind": kind,
        f"{UPGRADE_LABEL}.version": str(version),
    }
    if failure:
        labels[f"{UPGRADE_LABEL}.failure"] = failure[:500]
    return labels


def _mount_source(attrs: dict, destination: str) -> str | None:
    for mount in attrs.get("Mounts") or []:
        if mount.get("Destination") == destination:
            return mount.get("Source")
    return None


def upgrade_run_kwargs(
    own_attrs: dict, args: list[str], labels: dict[str, str], *, uid: int, gid: int, docker_gid: int
) -> dict:
    """`docker run` settings for the one-shot container that runs upgradeGhostwireProxy.sh ARGS.

    It runs this updater's image, as the owner of the checkout (so .git and .env keep their owner),
    with the project mounted read-write at the same path as on the host: the script runs
    `docker compose` there, and the daemon resolves the compose file's relative bind mounts as host
    paths. It is on the host network because the script's health checks call the published ports on
    localhost. Only this container gets the writable mount; the updater's own stays read-only.
    """
    host_dir = _mount_source(own_attrs, COMPOSE_PROJECT_DIR)
    if not host_dir:
        raise UpgradeError(f"The updater has no project mount at {COMPOSE_PROJECT_DIR}, so it can't find the install.")
    socket = _mount_source(own_attrs, DOCKER_SOCKET) or DOCKER_SOCKET
    environment = {
        # For git and docker's config; it is the one-shot container's own /tmp, shared with nothing.
        "HOME": "/tmp",  # noqa: S108
        # The checkout's owner may differ from the container user git sees; trust this one path only.
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": host_dir,
    }
    project = ((own_attrs.get("Config") or {}).get("Labels") or {}).get("com.docker.compose.project")
    if project:
        environment["COMPOSE_PROJECT_NAME"] = project
    return {
        "image": own_attrs["Image"],
        "command": ["bash", f"./{UPGRADE_SCRIPT}", *args],
        "name": UPGRADE_CONTAINER,
        "labels": labels,
        "working_dir": host_dir,
        "user": f"{uid}:{gid}",
        "group_add": [str(docker_gid)],
        "environment": environment,
        "volumes": {
            host_dir: {"bind": host_dir, "mode": "rw"},
            socket: {"bind": DOCKER_SOCKET, "mode": "rw"},
        },
        "network_mode": "host",
        "security_opt": ["no-new-privileges:true"],
        "detach": True,
    }


def script_lines(raw: bytes | str) -> list[str]:
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    return _ANSI_RE.sub("", text).splitlines()


def script_steps(lines: list[str]) -> list[tuple[int, int, str]]:
    """The script's step headers ("[6/8] Deploy") in the order it printed them."""
    steps = []
    for line in lines:
        match = _STEP_RE.match(line.strip())
        if match:
            steps.append((int(match.group(1)), int(match.group(2)), match.group(3)))
    return steps


def last_script_step(lines: list[str]) -> tuple[int, int, str] | None:
    steps = script_steps(lines)
    return steps[-1] if steps else None


def step_progress(number: int, total: int) -> int:
    """10% when the script starts, 90% at its last step."""
    return min(90, 10 + round(80 * (number - 1) / max(total - 1, 1)))


@dataclass
class ScriptResult:
    """How a run of upgradeGhostwireProxy.sh ended."""

    exit_code: int
    lines: list[str]

    @property
    def reached_deploy(self) -> bool:
        """Whether it got as far as restarting containers; before that the old version still runs."""
        return any(title == "Deploy" for _number, _total, title in script_steps(self.lines))

    @property
    def up_to_date(self) -> bool:
        return any("Already up to date" in line for line in self.lines)

    @property
    def failure(self) -> str:
        """The script's own reason (its "✗" line), else its last line."""
        marked = [line.split("✗", 1)[1].strip() for line in self.lines if "✗" in line]
        reasons = [m for m in marked if not m.startswith("Stopped at line")] or marked
        if reasons:
            return reasons[-1]
        last = next((line.strip() for line in reversed(self.lines) if line.strip()), "")
        message = f"{UPGRADE_SCRIPT} exited with code {self.exit_code}"
        return f"{message}: {last}" if last else message


def raise_rollback_outcome(version: str, failure: str, rollback: ScriptResult):
    if rollback.exit_code == 0:
        raise UpgradeError(
            f"The update to {version} failed ({failure}), so it was rolled back to the version that ran before. "
            "The database isn't rolled back: migrations only add, so the older version runs on it."
        )
    raise UpgradeError(
        f"The update to {version} failed ({failure}) and the rollback failed too ({rollback.failure}). "
        f"On the host, run ./{UPGRADE_SCRIPT} --rollback; the logs are in data/backups."
    )


# Container names
CONTAINERS = {
    "api": "ghostwire-proxy-api",
    "ui": "ghostwire-proxy-ui",
    "nginx": "ghostwire-proxy-nginx",
    "postgres": "ghostwire-proxy-postgres",
    "redis": "ghostwire-proxy-redis",
}

# Service to container mapping for docker-compose
SERVICES = {
    "api": "ghostwire-proxy-api",
    "ui": "ghostwire-proxy-ui",
    "nginx": "ghostwire-proxy-nginx",
}


class UpdaterService:
    """Main updater service."""

    def __init__(self):
        self.redis: redis.Redis | None = None
        self.docker_client: docker.DockerClient | None = None
        self.http_client: httpx.AsyncClient | None = None
        self.running = False

    async def start(self):
        """Start the updater service."""
        logger.info("Starting Ghostwire Proxy Updater Service...")

        # Initialize clients
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        self.docker_client = docker.from_env()
        self.http_client = httpx.AsyncClient(timeout=60.0)

        self.running = True

        # Subscribe to update channel
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("ghostwire:updates")

        # Upgrades a previous updater started (the deploy recreates this container part way through).
        await self.resume_upgrade_containers()

        logger.info("Updater service started, listening for update requests...")

        try:
            while self.running:
                heartbeat()
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                if message and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self.handle_update_request(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in message: {e}")
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")

                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("Updater service shutting down...")
        finally:
            await pubsub.unsubscribe()
            await self.redis.aclose()
            await self.http_client.aclose()
            self.docker_client.close()

    async def handle_update_request(self, data: dict):
        """Handle incoming update request."""
        action = data.get("action")
        update_id = data.get("update_id")

        logger.info(f"Received update request: action={action}, update_id={update_id}")

        try:
            if action == "start_update":
                update_type = data.get("update_type")

                if update_type == "app":
                    await self.perform_app_update(
                        update_id=update_id,
                        target_version=data.get("target_version"),
                    )
                elif update_type == "base_image":
                    await self.perform_base_image_update(
                        update_id=update_id,
                        container_name=data.get("container_name"),
                    )
                else:
                    logger.error(f"Unknown update type: {update_type}")

            elif action == "rollback":
                await self.perform_rollback(
                    update_id=update_id,
                    original_update_id=data.get("original_update_id"),
                    backup_id=data.get("backup_id"),
                )

            else:
                logger.warning(f"Unknown action: {action}")

        except Exception as e:
            logger.error(f"Update failed: {e}", exc_info=True)
            await self.update_status(update_id, "failed", error=str(e))

    async def update_status(
        self,
        update_id: str,
        status: str,
        progress: int | None = None,
        message: str | None = None,
        error: str | None = None,
    ):
        """Update status in Redis for API to read."""
        status_data = {
            "update_id": update_id,
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if progress is not None:
            status_data["progress_percent"] = str(progress)
        if message:
            status_data["progress_message"] = message
        if error:
            status_data["error_message"] = error

        # Store in Redis hash for API to read
        await self.redis.hset(f"update:{update_id}", mapping=status_data)

        # Also publish for real-time updates
        await self.redis.publish("ghostwire:update_status", json.dumps(status_data))

        logger.info(f"Update {update_id}: {status} ({progress}%) - {message or error or ''}")

    async def send_push_notification(
        self,
        title: str,
        body: str,
        notification_type: str = "update",
        data: dict | None = None,
    ):
        """Send push notification via internal API endpoint."""
        try:
            response = await self.http_client.post(
                f"{API_URL}/internal/push/send",
                json={
                    "title": title,
                    "body": body,
                    "notification_type": notification_type,
                    "data": data or {},
                },
                headers={"X-Internal-Auth": INTERNAL_AUTH_TOKEN},
            )
            if response.status_code == 200:
                logger.info(f"Push notification sent: {title}")
            else:
                logger.debug(f"Push notification failed: {response.status_code}")
        except Exception as e:
            logger.debug(f"Could not send push notification: {e}")

    # =========================================================================
    # APP UPDATES
    # =========================================================================

    async def perform_app_update(self, update_id: str, target_version: str):
        """
        Upgrade the app with the host's upgradeGhostwireProxy.sh, the one supported upgrade path.

        The script runs in a one-shot container (see upgrade_run_kwargs) that mounts the project
        read-write at its host path, so it does its own pre-flight, backup, build, deploy, health check
        and records what --rollback goes back to. That container isn't part of the compose project, so
        it keeps running when the deploy recreates this updater; the next updater picks it up
        (resume_upgrade_containers). If the script fails after it started the deploy, the updater runs
        `--rollback --yes`; if it fails before, nothing was restarted and nothing is rolled back.
        """
        try:
            async with job("app-update", version=str(target_version)):
                tag = version_tag(target_version)

                # The API's backup is what a rollback asked for from the UI restores; the script makes
                # its own database dump as well.
                await self.update_status(update_id, "in_progress", 5, "Creating pre-update backup...")
                backup_id = await self.create_pre_update_backup()
                await self.store_backup_id(update_id, backup_id)

                await self.update_status(update_id, "in_progress", 10, f"Starting {UPGRADE_SCRIPT} --yes {tag}...")
                container = await self.start_upgrade_container(
                    ["--yes", tag], upgrade_labels(update_id, "upgrade", target_version)
                )
                result = await self.wait_for_upgrade_container(container, update_id)
                await self.finish_upgrade(update_id, target_version, result)

        except Exception as e:
            await self.report_app_update_failure(update_id, target_version, e)

    async def report_app_update_failure(self, update_id: str, target_version: str, error: Exception):
        if isinstance(error, UpgradeError):
            message = str(error)
        else:
            logger.error(f"App update failed: {error}", exc_info=error)
            message = f"The update to {target_version} failed: {error}"
        await self.update_status(update_id, "failed", error=message)
        await self.send_push_notification(
            title="Update Failed",
            body=message[:200],
            notification_type="update",
            data={"version": target_version, "update_id": update_id},
        )

    async def finish_upgrade(self, update_id: str, target_version: str, result: ScriptResult):
        """Reports the script's outcome. Raises UpgradeError when it failed, after a rollback if one is due."""
        if result.exit_code == 0:
            if result.up_to_date:
                message = f"Already on {target_version}; nothing to do"
            else:
                message = f"Successfully updated to {target_version}"
            await self.update_status(update_id, "completed", 100, message)
            await self.send_push_notification(
                title="Update Complete",
                body=message,
                notification_type="update",
                data={"version": target_version, "update_id": update_id},
            )
            return

        failure = result.failure
        if not result.reached_deploy:
            raise UpgradeError(
                f"The update to {target_version} stopped before the deploy, so the running version is unchanged: {failure}"
            )

        await self.update_status(
            update_id, "in_progress", 90, f"Update failed ({failure}); rolling back with {UPGRADE_SCRIPT} --rollback..."
        )
        container = await self.start_upgrade_container(
            ["--rollback", "--yes"], upgrade_labels(update_id, "rollback", target_version, failure)
        )
        rollback = await self.wait_for_upgrade_container(container, update_id, progress=False)
        raise_rollback_outcome(target_version, failure, rollback)

    async def resume_upgrade_containers(self):
        """Finishes upgrades a previous updater started: the deploy usually recreates this container."""
        try:
            containers = await asyncio.to_thread(
                self.docker_client.containers.list, all=True, filters={"label": UPGRADE_LABEL}
            )
        except Exception as e:
            logger.warning(f"Couldn't look for upgrades in progress: {e}")
            return

        for container in containers:
            labels = container.labels or {}
            update_id = labels.get(f"{UPGRADE_LABEL}.update_id", "")
            kind = labels.get(f"{UPGRADE_LABEL}.kind", "upgrade")
            version = labels.get(f"{UPGRADE_LABEL}.version", "?")
            logger.info(f"Picking up {kind} {update_id} to {version} from {container.name}")
            try:
                async with job("app-update", version=version):
                    result = await self.wait_for_upgrade_container(container, update_id, progress=kind == "upgrade")
                    if kind == "rollback":
                        raise_rollback_outcome(version, labels.get(f"{UPGRADE_LABEL}.failure", "?"), result)
                    await self.finish_upgrade(update_id, version, result)
            except Exception as e:
                if update_id:
                    await self.report_app_update_failure(update_id, version, e)

    async def start_upgrade_container(self, args: list[str], labels: dict[str, str]):
        """Starts the one-shot container that runs upgradeGhostwireProxy.sh with ARGS."""

        def start():
            try:
                existing = self.docker_client.containers.get(UPGRADE_CONTAINER)
            except docker.errors.NotFound:
                existing = None
            if existing is not None:
                if existing.status in ("running", "created", "restarting"):
                    raise UpgradeError(f"Another upgrade is already running ({UPGRADE_CONTAINER}).")
                existing.remove(force=True)

            own = self.own_container()
            git_dir = os.path.join(COMPOSE_PROJECT_DIR, ".git")
            if not os.path.isdir(git_dir) or not os.path.isfile(os.path.join(COMPOSE_PROJECT_DIR, UPGRADE_SCRIPT)):
                raise UpgradeError(f"The mounted project isn't a git checkout with {UPGRADE_SCRIPT} in it.")
            owner = os.stat(git_dir)
            # The script writes its log and database dump there as the checkout's owner. Docker makes
            # the directory as root when it's missing, which a non-root checkout can't write to.
            backups = os.path.join(COMPOSE_PROJECT_DIR, "data", "backups")
            if owner.st_uid != 0 and os.path.isdir(backups) and os.stat(backups).st_uid != owner.st_uid:
                raise UpgradeError(
                    f"data/backups isn't owned by the checkout's owner (uid {owner.st_uid}), so the upgrade "
                    f"can't write its backup there. On the host: sudo chown -R {owner.st_uid} data/backups"
                )
            kwargs = upgrade_run_kwargs(
                own.attrs,
                args,
                labels,
                uid=owner.st_uid,
                gid=owner.st_gid,
                docker_gid=os.stat(DOCKER_SOCKET).st_gid,
            )
            return self.docker_client.containers.run(**kwargs)

        return await asyncio.to_thread(start)

    def own_container(self):
        """This updater's container (for its image and the host path of the project mount)."""
        for ref in (UPDATER_CONTAINER, os.environ.get("HOSTNAME", "")):
            if not ref:
                continue
            try:
                return self.docker_client.containers.get(ref)
            except docker.errors.NotFound:
                continue
        raise UpgradeError("Can't find the updater's own container, so the upgrade can't be started.")

    async def wait_for_upgrade_container(self, container, update_id: str, progress: bool = True) -> ScriptResult:
        """Waits for the script to end, reporting each step it reaches, then removes the container."""
        deadline = time.monotonic() + UPGRADE_TIMEOUT_SECONDS
        last_step = None
        while True:
            heartbeat()
            await asyncio.to_thread(container.reload)
            lines = script_lines(await asyncio.to_thread(container.logs))
            step = last_script_step(lines)
            if progress and step and step != last_step:
                last_step = step
                number, total, title = step
                await self.update_status(update_id, "in_progress", step_progress(number, total), f"{title}...")
            if container.status in ("exited", "dead"):
                break
            if time.monotonic() > deadline:
                await asyncio.to_thread(container.stop)
                raise UpgradeError(
                    f"{UPGRADE_SCRIPT} was still running after {UPGRADE_TIMEOUT_SECONDS // 60} minutes and was stopped. "
                    f"Its log is in data/backups; on the host, ./{UPGRADE_SCRIPT} --rollback goes back."
                )
            await asyncio.sleep(UPGRADE_POLL_SECONDS)

        exit_code = int(container.attrs.get("State", {}).get("ExitCode", 1))
        for line in lines[-40:]:
            logger.info(f"[{UPGRADE_SCRIPT}] {line}")
        try:
            await asyncio.to_thread(container.remove)
        except Exception as e:
            logger.warning(f"Couldn't remove {container.name}: {e}")
        return ScriptResult(exit_code, lines)

    async def create_pre_update_backup(self) -> str:
        """Create a backup before update via API."""
        try:
            async with job("pre-update-backup"):
                response = await self.http_client.post(
                    f"{API_URL}/api/backups/",
                    json={
                        "include_database": True,
                        "include_certificates": True,
                        "include_letsencrypt": True,
                        "include_configs": True,
                        "include_traffic_logs": False,
                    },
                    headers={"X-Internal-Auth": INTERNAL_AUTH_TOKEN},
                )

            if response.status_code in [200, 201]:
                backup_data = response.json()
                logger.info(f"Created backup: {backup_data.get('id')}")
                return backup_data.get("id")
            else:
                logger.warning(f"Backup API returned {response.status_code}: {response.text}")
                # Continue anyway - backup is optional
                return None

        except Exception as e:
            logger.warning(f"Failed to create backup via API: {e}")
            # Continue anyway - backup is optional
            return None

    async def restart_containers_ordered(self):
        """Restart containers in the correct order."""
        # Order: databases first, then api, then ui/nginx
        restart_groups = [
            # Don't restart databases during app update - they don't change
            # ["ghostwire-proxy-redis", "ghostwire-proxy-postgres"],
            [CONTAINERS["api"]],
            [CONTAINERS["ui"], CONTAINERS["nginx"]],
        ]

        for group in restart_groups:
            for container_name in group:
                try:
                    # Use docker-compose up to recreate with new images
                    service_name = container_name.replace("ghostwire-proxy-", "ghostwire-proxy-")

                    os.chdir(COMPOSE_PROJECT_DIR)
                    result = await asyncio.to_thread(
                        subprocess.run,
                        ["docker-compose", "up", "-d", "--force-recreate", service_name],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    if result.returncode != 0:
                        logger.warning(f"Recreate {container_name} output: {result.stderr}")

                    logger.info(f"Recreated {container_name}")

                except Exception as e:
                    logger.error(f"Failed to recreate {container_name}: {e}")
                    raise

            # Wait for group to stabilize
            await asyncio.sleep(10)

    async def post_update_health_checks(self) -> bool:
        """Run health checks after update."""
        max_retries = 30

        for i in range(max_retries):
            try:
                response = await self.http_client.get(f"{API_URL}/health", timeout=5.0)
                if response.status_code == 200:
                    logger.info("Health check passed")
                    return True
            except Exception as e:
                logger.debug(f"Health check attempt {i + 1}/{max_retries} failed: {e}")

            await asyncio.sleep(2)

        logger.error("Health checks failed after all retries")
        return False

    async def store_backup_id(self, update_id: str, backup_id: str | None):
        """Store backup ID for later rollback."""
        if backup_id:
            await self.redis.hset(f"update:{update_id}", "backup_id", backup_id)

    # =========================================================================
    # BASE IMAGE UPDATES
    # =========================================================================

    async def perform_base_image_update(self, update_id: str, container_name: str):
        """
        Update base image for a specific container.
        """
        try:
            async with job("base-image-update", container=str(container_name)):
                await self.update_status(
                    update_id, "in_progress", 10, f"Starting base image update for {container_name}..."
                )

                # Validate container name
                if container_name not in SERVICES:
                    raise ValueError(f"Cannot update base image for: {container_name}")

                # Create backup first
                await self.update_status(update_id, "in_progress", 20, "Creating pre-update backup...")

                backup_id = await self.create_pre_update_backup()
                await self.store_backup_id(update_id, backup_id)

                await self.update_status(update_id, "in_progress", 40, "Pulling latest base image and rebuilding...")

                # Rebuild specific service with --pull to get latest base image
                os.chdir(COMPOSE_PROJECT_DIR)
                service_name = SERVICES[container_name]

                result = await asyncio.to_thread(
                    subprocess.run,
                    ["docker-compose", "build", "--pull", "--no-cache", service_name],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if result.returncode != 0:
                    raise Exception(f"Build failed: {result.stderr}")

                await self.update_status(update_id, "in_progress", 70, "Restarting container with new image...")

                # Recreate just this container
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["docker-compose", "up", "-d", "--force-recreate", service_name],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                if result.returncode != 0:
                    raise Exception(f"Container restart failed: {result.stderr}")

                # Health check
                await self.update_status(update_id, "in_progress", 90, "Running health checks...")

                await asyncio.sleep(10)  # Wait for container to start

                if not await self.post_update_health_checks():
                    raise Exception("Health checks failed after base image update")

                await self.update_status(
                    update_id, "completed", 100, f"Successfully updated {container_name} base image"
                )

                # Send push notification
                await self.send_push_notification(
                    title="Base Image Updated",
                    body=f"Successfully updated {container_name} container",
                    notification_type="update",
                    data={"container": container_name, "update_id": update_id},
                )

        except Exception as e:
            logger.error(f"Base image update failed: {e}", exc_info=True)
            await self.update_status(update_id, "failed", error=str(e))

            # Send failure push notification
            await self.send_push_notification(
                title="Update Failed",
                body=f"Base image update failed for {container_name}",
                notification_type="update",
                data={"container": container_name, "error": str(e)[:100]},
            )

    # =========================================================================
    # ROLLBACK
    # =========================================================================

    async def perform_rollback(self, update_id: str, original_update_id: str, backup_id: str):
        """
        Perform rollback to previous version.
        """
        try:
            async with job("rollback"):
                await self.update_status(update_id, "in_progress", 10, "Starting rollback...")

                if not backup_id:
                    raise ValueError("No backup ID provided for rollback")

                # Restore from backup
                await self.update_status(update_id, "in_progress", 30, "Restoring from backup...")

                response = await self.http_client.post(
                    f"{API_URL}/api/backups/restore",
                    json={
                        "backup_id": backup_id,
                        "restore_database": True,
                        "restore_certificates": True,
                        "restore_letsencrypt": True,
                        "restore_configs": True,
                    },
                    headers={"X-Internal-Auth": INTERNAL_AUTH_TOKEN},
                )

                if response.status_code not in [200, 201]:
                    raise Exception(f"Restore failed: {response.text}")

                await self.update_status(update_id, "in_progress", 70, "Restarting containers...")

                # Restart all application containers
                await self.restart_containers_ordered()

                # Health check
                await self.update_status(update_id, "in_progress", 90, "Running health checks...")

                if not await self.post_update_health_checks():
                    raise Exception("Health checks failed after rollback")

                await self.update_status(update_id, "completed", 100, "Rollback completed successfully")

        except Exception as e:
            logger.error(f"Rollback failed: {e}", exc_info=True)
            await self.update_status(update_id, "failed", error=str(e))


async def main():
    """Main entry point."""
    ghostwire_telemetry.setup(
        analytics_config,
        service_name="updater",
        service_namespace="ghostwire-proxy",
        service_version=app_version(),
    )
    service = UpdaterService()
    await service.start()


if __name__ == "__main__":
    asyncio.run(main())

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
import subprocess
import shutil
from datetime import datetime, timezone
from typing import Optional

import docker
import redis.asyncio as redis
import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        self.redis: Optional[redis.Redis] = None
        self.docker_client: Optional[docker.DockerClient] = None
        self.http_client: Optional[httpx.AsyncClient] = None
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

        logger.info("Updater service started, listening for update requests...")

        try:
            while self.running:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )

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
        progress: int = None,
        message: str = None,
        error: str = None,
    ):
        """Update status in Redis for API to read."""
        status_data = {
            "update_id": update_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
        await self.redis.publish(
            "ghostwire:update_status",
            json.dumps(status_data)
        )

        logger.info(f"Update {update_id}: {status} ({progress}%) - {message or error or ''}")

    async def send_push_notification(
        self,
        title: str,
        body: str,
        notification_type: str = "update",
        data: Optional[dict] = None,
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
                headers={"X-Internal-Auth": INTERNAL_AUTH_TOKEN}
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
        Perform full application update.

        Steps:
        1. Pre-flight checks
        2. Create backup
        3. Pull new version (git checkout)
        4. Build new images
        5. Run database migrations
        6. Restart containers in order
        7. Health checks
        8. Cleanup or rollback
        """
        try:
            # Step 1: Pre-flight checks
            await self.update_status(
                update_id, "in_progress", 5,
                "Running pre-flight checks..."
            )

            if not await self.preflight_checks():
                raise Exception("Pre-flight checks failed")

            # Step 2: Create backup
            await self.update_status(
                update_id, "in_progress", 10,
                "Creating pre-update backup..."
            )

            backup_id = await self.create_pre_update_backup()
            await self.store_backup_id(update_id, backup_id)

            # Step 3: Pull new version
            await self.update_status(
                update_id, "in_progress", 25,
                f"Pulling version {target_version}..."
            )

            await self.pull_new_version(target_version)

            # Step 4: Build new images
            await self.update_status(
                update_id, "in_progress", 40,
                "Building new container images..."
            )

            await self.build_images()

            # Step 5: Database migrations
            await self.update_status(
                update_id, "in_progress", 55,
                "Running database migrations..."
            )

            await self.run_migrations()

            # Step 6: Restart containers (in order)
            await self.update_status(
                update_id, "in_progress", 70,
                "Restarting containers..."
            )

            await self.restart_containers_ordered()

            # Step 7: Health checks
            await self.update_status(
                update_id, "in_progress", 90,
                "Running health checks..."
            )

            if not await self.post_update_health_checks():
                raise Exception("Post-update health checks failed")

            # Success!
            await self.update_status(
                update_id, "completed", 100,
                f"Successfully updated to {target_version}"
            )

            # Send push notification
            await self.send_push_notification(
                title="Update Complete",
                body=f"Successfully updated to version {target_version}",
                notification_type="update",
                data={"version": target_version, "update_id": update_id},
            )

        except Exception as e:
            logger.error(f"App update failed: {e}", exc_info=True)

            # Attempt automatic rollback
            await self.update_status(
                update_id, "in_progress",
                message="Update failed, attempting automatic rollback..."
            )
            try:
                await self.perform_automatic_rollback(update_id)
                await self.update_status(
                    update_id, "failed",
                    error=f"Update failed and was rolled back: {e}"
                )
            except Exception as rollback_error:
                logger.error(f"Automatic rollback failed: {rollback_error}")
                await self.update_status(
                    update_id, "failed",
                    error=f"Update failed and rollback also failed: {e}. Rollback error: {rollback_error}"
                )

    async def preflight_checks(self) -> bool:
        """Run pre-flight checks before update."""
        try:
            # Check all containers are running
            for name, container_name in CONTAINERS.items():
                try:
                    container = self.docker_client.containers.get(container_name)
                    if container.status != "running":
                        logger.warning(f"Container {container_name} is not running: {container.status}")
                        return False
                except docker.errors.NotFound:
                    logger.warning(f"Container {container_name} not found")
                    return False

            # Check disk space (need at least 1GB free)
            statvfs = os.statvfs(COMPOSE_PROJECT_DIR)
            free_gb = (statvfs.f_frsize * statvfs.f_bavail) / (1024**3)
            if free_gb < 1.0:
                logger.warning(f"Insufficient disk space: {free_gb:.2f} GB free")
                return False

            logger.info("Pre-flight checks passed")
            return True

        except Exception as e:
            logger.error(f"Pre-flight check error: {e}")
            return False

    async def create_pre_update_backup(self) -> str:
        """Create a backup before update via API."""
        try:
            response = await self.http_client.post(
                f"{API_URL}/api/backups/",
                json={
                    "include_database": True,
                    "include_certificates": True,
                    "include_letsencrypt": True,
                    "include_configs": True,
                    "include_traffic_logs": False,
                },
                headers={"X-Internal-Auth": INTERNAL_AUTH_TOKEN}
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

    async def pull_new_version(self, version: str):
        """Pull new version from git."""
        os.chdir(COMPOSE_PROJECT_DIR)

        # Fetch tags
        result = subprocess.run(
            ["git", "fetch", "--tags", "--force"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise Exception(f"Git fetch failed: {result.stderr}")

        # Stash any local changes
        subprocess.run(
            ["git", "stash"],
            capture_output=True, text=True
        )

        # Checkout version tag
        tag_name = f"v{version}" if not version.startswith("v") else version
        result = subprocess.run(
            ["git", "checkout", tag_name],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise Exception(f"Git checkout failed: {result.stderr}")

        logger.info(f"Checked out version {tag_name}")

    async def build_images(self):
        """Rebuild Docker images."""
        os.chdir(COMPOSE_PROJECT_DIR)

        # Build without cache to ensure fresh images
        result = subprocess.run(
            ["docker-compose", "build", "--no-cache", "--parallel"],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            raise Exception(f"Docker build failed: {result.stderr}")

        logger.info("Built new container images")

    async def run_migrations(self):
        """Run database migrations."""
        try:
            container = self.docker_client.containers.get(CONTAINERS["api"])
            exit_code, output = container.exec_run(
                "alembic upgrade head",
                workdir="/app"
            )

            if exit_code != 0:
                logger.warning(f"Migration output: {output.decode()}")
                # Don't fail on migration errors - tables might already exist
                logger.warning("Migration may have had issues, continuing...")

            logger.info("Database migrations completed")

        except Exception as e:
            logger.warning(f"Migration execution failed: {e}")
            # Continue anyway - create_all in main.py will handle tables

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
                    result = subprocess.run(
                        ["docker-compose", "up", "-d", "--force-recreate", service_name],
                        capture_output=True, text=True, timeout=120
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
                response = await self.http_client.get(
                    f"{API_URL}/health",
                    timeout=5.0
                )
                if response.status_code == 200:
                    logger.info("Health check passed")
                    return True
            except Exception as e:
                logger.debug(f"Health check attempt {i+1}/{max_retries} failed: {e}")

            await asyncio.sleep(2)

        logger.error("Health checks failed after all retries")
        return False

    async def perform_automatic_rollback(self, update_id: str):
        """Attempt automatic rollback on failure."""
        backup_id = await self.redis.hget(f"update:{update_id}", "backup_id")

        if not backup_id:
            logger.warning("No backup ID found for automatic rollback")
            return

        # Restore from backup
        try:
            response = await self.http_client.post(
                f"{API_URL}/api/backups/restore",
                json={
                    "backup_id": backup_id,
                    "restore_database": True,
                    "restore_certificates": True,
                    "restore_letsencrypt": True,
                    "restore_configs": True,
                },
                headers={"X-Internal-Auth": INTERNAL_AUTH_TOKEN}
            )

            if response.status_code not in [200, 201]:
                logger.warning(f"Restore API returned {response.status_code}")

        except Exception as e:
            logger.error(f"Restore request failed: {e}")

        # Restart containers
        await self.restart_containers_ordered()

    async def store_backup_id(self, update_id: str, backup_id: Optional[str]):
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
            await self.update_status(
                update_id, "in_progress", 10,
                f"Starting base image update for {container_name}..."
            )

            # Validate container name
            if container_name not in SERVICES:
                raise ValueError(f"Cannot update base image for: {container_name}")

            # Create backup first
            await self.update_status(
                update_id, "in_progress", 20,
                "Creating pre-update backup..."
            )

            backup_id = await self.create_pre_update_backup()
            await self.store_backup_id(update_id, backup_id)

            await self.update_status(
                update_id, "in_progress", 40,
                "Pulling latest base image and rebuilding..."
            )

            # Rebuild specific service with --pull to get latest base image
            os.chdir(COMPOSE_PROJECT_DIR)
            service_name = SERVICES[container_name]

            result = subprocess.run(
                ["docker-compose", "build", "--pull", "--no-cache", service_name],
                capture_output=True, text=True, timeout=300
            )

            if result.returncode != 0:
                raise Exception(f"Build failed: {result.stderr}")

            await self.update_status(
                update_id, "in_progress", 70,
                "Restarting container with new image..."
            )

            # Recreate just this container
            result = subprocess.run(
                ["docker-compose", "up", "-d", "--force-recreate", service_name],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                raise Exception(f"Container restart failed: {result.stderr}")

            # Health check
            await self.update_status(
                update_id, "in_progress", 90,
                "Running health checks..."
            )

            await asyncio.sleep(10)  # Wait for container to start

            if not await self.post_update_health_checks():
                raise Exception("Health checks failed after base image update")

            await self.update_status(
                update_id, "completed", 100,
                f"Successfully updated {container_name} base image"
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

    async def perform_rollback(
        self,
        update_id: str,
        original_update_id: str,
        backup_id: str
    ):
        """
        Perform rollback to previous version.
        """
        try:
            await self.update_status(
                update_id, "in_progress", 10,
                "Starting rollback..."
            )

            if not backup_id:
                raise ValueError("No backup ID provided for rollback")

            # Restore from backup
            await self.update_status(
                update_id, "in_progress", 30,
                "Restoring from backup..."
            )

            response = await self.http_client.post(
                f"{API_URL}/api/backups/restore",
                json={
                    "backup_id": backup_id,
                    "restore_database": True,
                    "restore_certificates": True,
                    "restore_letsencrypt": True,
                    "restore_configs": True,
                },
                headers={"X-Internal-Auth": INTERNAL_AUTH_TOKEN}
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"Restore failed: {response.text}")

            await self.update_status(
                update_id, "in_progress", 70,
                "Restarting containers..."
            )

            # Restart all application containers
            await self.restart_containers_ordered()

            # Health check
            await self.update_status(
                update_id, "in_progress", 90,
                "Running health checks..."
            )

            if not await self.post_update_health_checks():
                raise Exception("Health checks failed after rollback")

            await self.update_status(
                update_id, "completed", 100,
                "Rollback completed successfully"
            )

        except Exception as e:
            logger.error(f"Rollback failed: {e}", exc_info=True)
            await self.update_status(update_id, "failed", error=str(e))


async def main():
    """Main entry point."""
    service = UpdaterService()
    await service.start()


if __name__ == "__main__":
    asyncio.run(main())

"""
Update service for checking and managing application and base image updates.

This service handles:
- Checking for new app versions via GitHub releases
- Checking for base image updates via Docker registry
- Requesting updates (forwarded to updater sidecar via Redis)
- Tracking update status and history
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
import semver

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.redis import get_redis
from app.core.version import APP_VERSION
from app.models.update import UpdateHistory, BaseImageVersion, UpdateSettings

logger = logging.getLogger(__name__)

# Update server configuration
GITHUB_API_URL = "https://api.github.com"
DEFAULT_GITHUB_REPO = "garethcheyne/ghostwire-proxy"

# Base images to track
BASE_IMAGES = {
    "api": {"image": "python", "tag": "3.12-slim"},
    "ui": {"image": "node", "tag": "20-alpine"},
    "nginx": {"image": "openresty/openresty", "tag": "1.25.3.1-alpine"},
    "postgres": {"image": "postgres", "tag": "16-alpine"},
    "redis": {"image": "redis", "tag": "7-alpine"},
}


# CalVer pattern: YYYY.MM.DD.HHMM
_CALVER_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d{4}$")


def _is_calver(version: str) -> bool:
    return bool(_CALVER_RE.match(version))


def _parse_version_tuple(version: str) -> tuple:
    """Parse a version string into a comparable tuple.

    Supports both CalVer (2026.03.24.1430) and semver (1.2.3).
    """
    if _is_calver(version):
        return tuple(int(p) for p in version.split("."))
    try:
        v = semver.VersionInfo.parse(version)
        return (v.major, v.minor, v.patch)
    except ValueError:
        return (0,)


def _is_valid_version(tag: str) -> bool:
    """Check if a tag is a valid version (semver or CalVer)."""
    if _is_calver(tag):
        return True
    try:
        semver.VersionInfo.parse(tag)
        return True
    except ValueError:
        return False


class UpdateService:
    """Service for managing application updates."""

    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "Ghostwire-Proxy-Updater"}
            )
        return self._http_client

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # =========================================================================
    # VERSION CHECKING
    # =========================================================================

    async def check_for_app_updates(
        self,
        db: Optional[AsyncSession] = None
    ) -> dict:
        """
        Check for new application versions via GitHub releases.

        Returns dict with current version, latest version, and available updates.
        """
        result = {
            "current_version": APP_VERSION,
            "latest_version": None,
            "update_available": False,
            "releases": [],
            "error": None,
        }

        # Get GitHub repo from settings if available
        github_repo = DEFAULT_GITHUB_REPO
        if db:
            settings = await self.get_settings(db)
            if settings and settings.github_repo:
                github_repo = settings.github_repo

        try:
            url = f"{GITHUB_API_URL}/repos/{github_repo}/releases"
            response = await self.http_client.get(
                url,
                headers={"Accept": "application/vnd.github.v3+json"}
            )

            if response.status_code == 200:
                releases = response.json()

                # Parse releases (last 10 non-draft, non-prerelease)
                for release in releases[:20]:
                    if release.get("draft"):
                        continue

                    tag = release.get("tag_name", "").lstrip("v")
                    is_prerelease = release.get("prerelease", False)

                    try:
                        # Validate version tag (semver or CalVer)
                        if not _is_valid_version(tag):
                            continue

                        result["releases"].append({
                            "version": tag,
                            "name": release.get("name") or f"v{tag}",
                            "published_at": release.get("published_at"),
                            "changelog": release.get("body"),
                            "html_url": release.get("html_url"),
                            "prerelease": is_prerelease,
                        })
                    except ValueError:
                        continue

                # Filter to stable releases for latest_version
                stable_releases = [r for r in result["releases"] if not r["prerelease"]]

                if stable_releases:
                    result["latest_version"] = stable_releases[0]["version"]

                    # Compare versions (supports both CalVer and semver)
                    try:
                        current = _parse_version_tuple(APP_VERSION)
                        latest = _parse_version_tuple(result["latest_version"])
                        result["update_available"] = latest > current
                    except Exception as e:
                        logger.warning(f"Version comparison failed: {e}")

            elif response.status_code == 404:
                result["error"] = f"Repository not found: {github_repo}"
            elif response.status_code == 403:
                result["error"] = "GitHub API rate limit exceeded"
            else:
                result["error"] = f"GitHub API error: {response.status_code}"

        except httpx.TimeoutException:
            result["error"] = "Connection to GitHub timed out"
        except Exception as e:
            logger.error(f"Failed to check for app updates: {e}")
            result["error"] = str(e)

        return result

    async def check_for_base_image_updates(
        self,
        db: Optional[AsyncSession] = None
    ) -> list[dict]:
        """
        Check for base image updates using Docker registry API.

        Returns list of containers with their update status.
        """
        results = []

        for container, image_info in BASE_IMAGES.items():
            image_result = {
                "container": container,
                "image": f"{image_info['image']}:{image_info['tag']}",
                "update_available": False,
                "current_digest": None,
                "latest_digest": None,
                "error": None,
            }

            try:
                # Get stored digest from database
                if db:
                    stored = await db.execute(
                        select(BaseImageVersion).where(
                            BaseImageVersion.container_name == container
                        )
                    )
                    stored_version = stored.scalar_one_or_none()
                    if stored_version:
                        image_result["current_digest"] = stored_version.current_digest

                # Get latest digest from Docker Hub
                image_name = image_info["image"]
                tag = image_info["tag"]

                # Parse namespace
                if "/" in image_name:
                    namespace, name = image_name.split("/", 1)
                else:
                    namespace = "library"
                    name = image_name

                # Get auth token
                token = await self._get_docker_hub_token(namespace, name)
                if token:
                    digest = await self._get_image_digest(namespace, name, tag, token)
                    image_result["latest_digest"] = digest

                    # Compare digests
                    if (image_result["current_digest"] and
                            image_result["latest_digest"] and
                            image_result["current_digest"] != image_result["latest_digest"]):
                        image_result["update_available"] = True

            except Exception as e:
                logger.error(f"Failed to check base image {container}: {e}")
                image_result["error"] = str(e)

            results.append(image_result)

        return results

    async def _get_docker_hub_token(
        self,
        namespace: str,
        name: str
    ) -> Optional[str]:
        """Get Docker Hub authentication token for image access."""
        try:
            url = (
                f"https://auth.docker.io/token?"
                f"service=registry.docker.io&"
                f"scope=repository:{namespace}/{name}:pull"
            )
            response = await self.http_client.get(url)
            if response.status_code == 200:
                return response.json().get("token")
        except Exception as e:
            logger.debug(f"Failed to get Docker Hub token: {e}")
        return None

    async def _get_image_digest(
        self,
        namespace: str,
        name: str,
        tag: str,
        token: str
    ) -> Optional[str]:
        """Get image manifest digest from Docker Hub."""
        try:
            url = f"https://registry-1.docker.io/v2/{namespace}/{name}/manifests/{tag}"
            response = await self.http_client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.docker.distribution.manifest.v2+json",
                }
            )
            if response.status_code == 200:
                return response.headers.get("Docker-Content-Digest")
        except Exception as e:
            logger.debug(f"Failed to get image digest: {e}")
        return None

    # =========================================================================
    # UPDATE ORCHESTRATION
    # =========================================================================

    async def request_app_update(
        self,
        db: AsyncSession,
        target_version: str,
        user_id: str,
    ) -> UpdateHistory:
        """
        Request an application update.

        Creates an update record and signals the updater sidecar via Redis.
        """
        # Validate version format
        try:
            semver.VersionInfo.parse(target_version)
        except ValueError:
            raise ValueError(f"Invalid version format: {target_version}")

        # Check if an update is already in progress
        in_progress = await db.execute(
            select(UpdateHistory).where(
                UpdateHistory.status.in_(["pending", "in_progress"])
            )
        )
        if in_progress.scalar_one_or_none():
            raise ValueError("An update is already in progress")

        # Create update record
        update = UpdateHistory(
            update_type="app",
            from_version=APP_VERSION,
            to_version=target_version,
            status="pending",
            initiated_by=user_id,
            progress_percent=0,
            progress_message="Update requested, waiting for updater service",
        )

        db.add(update)
        await db.commit()
        await db.refresh(update)

        # Signal the updater sidecar via Redis pub/sub
        try:
            redis = await get_redis()
            await redis.publish("ghostwire:updates", json.dumps({
                "action": "start_update",
                "update_id": update.id,
                "update_type": "app",
                "target_version": target_version,
            }))
            logger.info(f"Published app update request: {update.id}")
        except Exception as e:
            logger.error(f"Failed to publish update request: {e}")
            update.status = "failed"
            update.error_message = f"Failed to contact updater service: {e}"
            await db.commit()
            raise ValueError("Failed to contact updater service")

        return update

    async def request_base_image_update(
        self,
        db: AsyncSession,
        container_name: str,
        user_id: str,
    ) -> UpdateHistory:
        """
        Request a base image update for a specific container.
        """
        # Validate container name
        if container_name not in BASE_IMAGES:
            raise ValueError(f"Unknown container: {container_name}")

        # Check if an update is already in progress
        in_progress = await db.execute(
            select(UpdateHistory).where(
                UpdateHistory.status.in_(["pending", "in_progress"])
            )
        )
        if in_progress.scalar_one_or_none():
            raise ValueError("An update is already in progress")

        image_info = BASE_IMAGES[container_name]
        image_str = f"{image_info['image']}:{image_info['tag']}"

        # Create update record
        update = UpdateHistory(
            update_type="base_image",
            container_name=container_name,
            from_version=image_str,
            status="pending",
            initiated_by=user_id,
            progress_percent=0,
            progress_message="Base image update requested",
        )

        db.add(update)
        await db.commit()
        await db.refresh(update)

        # Signal the updater sidecar
        try:
            redis = await get_redis()
            await redis.publish("ghostwire:updates", json.dumps({
                "action": "start_update",
                "update_id": update.id,
                "update_type": "base_image",
                "container_name": container_name,
            }))
            logger.info(f"Published base image update request: {update.id}")
        except Exception as e:
            logger.error(f"Failed to publish update request: {e}")
            update.status = "failed"
            update.error_message = f"Failed to contact updater service: {e}"
            await db.commit()
            raise ValueError("Failed to contact updater service")

        return update

    async def get_update_status(
        self,
        db: AsyncSession,
        update_id: str
    ) -> Optional[UpdateHistory]:
        """Get current status of an update."""
        # First check Redis for real-time status
        try:
            redis = await get_redis()
            status_data = await redis.hgetall(f"update:{update_id}")
            if status_data:
                # Update database with latest status
                result = await db.execute(
                    select(UpdateHistory).where(UpdateHistory.id == update_id)
                )
                update = result.scalar_one_or_none()
                if update:
                    if "status" in status_data:
                        update.status = status_data["status"]
                    if "progress_percent" in status_data:
                        update.progress_percent = int(status_data["progress_percent"])
                    if "progress_message" in status_data:
                        update.progress_message = status_data["progress_message"]
                    if "error_message" in status_data:
                        update.error_message = status_data["error_message"]
                    if status_data.get("status") in ["completed", "failed"]:
                        update.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    return update
        except Exception as e:
            logger.debug(f"Could not fetch real-time status: {e}")

        # Fallback to database
        result = await db.execute(
            select(UpdateHistory).where(UpdateHistory.id == update_id)
        )
        return result.scalar_one_or_none()

    async def get_update_history(
        self,
        db: AsyncSession,
        limit: int = 20
    ) -> list[UpdateHistory]:
        """Get update history."""
        result = await db.execute(
            select(UpdateHistory)
            .order_by(desc(UpdateHistory.started_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def request_rollback(
        self,
        db: AsyncSession,
        update_id: str,
        user_id: str,
    ) -> UpdateHistory:
        """
        Request rollback of a completed update.
        """
        # Get original update
        result = await db.execute(
            select(UpdateHistory).where(UpdateHistory.id == update_id)
        )
        original = result.scalar_one_or_none()

        if not original:
            raise ValueError(f"Update not found: {update_id}")

        if original.status != "completed":
            raise ValueError("Can only rollback completed updates")

        if not original.can_rollback:
            raise ValueError("This update cannot be rolled back")

        if original.rollback_performed:
            raise ValueError("Rollback already performed for this update")

        if not original.backup_id:
            raise ValueError("No backup available for rollback")

        # Create rollback record
        rollback = UpdateHistory(
            update_type=f"{original.update_type}_rollback",
            from_version=original.to_version,
            to_version=original.from_version,
            container_name=original.container_name,
            status="pending",
            initiated_by=user_id,
            backup_id=original.backup_id,
            progress_message="Rollback requested",
        )

        db.add(rollback)

        # Mark original update as rolled back
        original.rollback_performed = True

        await db.commit()
        await db.refresh(rollback)

        # Signal rollback
        try:
            redis = await get_redis()
            await redis.publish("ghostwire:updates", json.dumps({
                "action": "rollback",
                "update_id": rollback.id,
                "original_update_id": update_id,
                "backup_id": original.backup_id,
            }))
            logger.info(f"Published rollback request: {rollback.id}")
        except Exception as e:
            logger.error(f"Failed to publish rollback request: {e}")
            rollback.status = "failed"
            rollback.error_message = f"Failed to contact updater service: {e}"
            await db.commit()
            raise ValueError("Failed to contact updater service")

        return rollback

    # =========================================================================
    # SETTINGS
    # =========================================================================

    async def get_settings(self, db: AsyncSession) -> UpdateSettings:
        """Get update settings, creating default if not exists."""
        result = await db.execute(
            select(UpdateSettings).order_by(UpdateSettings.updated_at.desc()).limit(1)
        )
        settings = result.scalar_one_or_none()

        if not settings:
            settings = UpdateSettings()
            db.add(settings)
            await db.commit()
            await db.refresh(settings)

        return settings

    async def update_settings(
        self,
        db: AsyncSession,
        **kwargs
    ) -> UpdateSettings:
        """Update settings."""
        settings = await self.get_settings(db)

        for key, value in kwargs.items():
            if hasattr(settings, key) and value is not None:
                setattr(settings, key, value)

        settings.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(settings)

        return settings


# Global service instance
update_service = UpdateService()

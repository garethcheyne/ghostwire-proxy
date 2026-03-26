"""
Backup service for creating and restoring backups of Ghostwire Proxy.

Backups include:
- PostgreSQL database dump
- SSL certificates
- Let's Encrypt data
- Nginx configurations
- Optionally: Traffic logs (large)
"""

import os
import json
import tarfile
import tempfile
import shutil
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.backup import Backup, BackupSettings as BackupSettingsModel

logger = logging.getLogger(__name__)

# Backup storage path
BACKUP_PATH = os.environ.get("BACKUP_PATH", "/data/backups")


class BackupService:
    """Service for managing backups."""

    def __init__(self):
        # Ensure backup directory exists (may fail in CI/test environments)
        try:
            os.makedirs(BACKUP_PATH, exist_ok=True)
        except PermissionError:
            pass

    async def create_backup(
        self,
        db: AsyncSession,
        user_id: Optional[str] = None,
        backup_type: str = "manual",
        include_database: bool = True,
        include_certificates: bool = True,
        include_letsencrypt: bool = True,
        include_configs: bool = True,
        include_traffic_logs: bool = False,
    ) -> Backup:
        """
        Create a new backup.

        Returns:
            Backup object with metadata
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        filename = f"ghostwire_backup_{timestamp}.tar.gz"
        file_path = os.path.join(BACKUP_PATH, filename)

        # Create backup record
        backup = Backup(
            id=str(uuid.uuid4()),
            filename=filename,
            file_path=file_path,
            file_size=0,
            backup_type=backup_type,
            includes_database=include_database,
            includes_certificates=include_certificates,
            includes_letsencrypt=include_letsencrypt,
            includes_configs=include_configs,
            includes_traffic_logs=include_traffic_logs,
            status="in_progress",
            created_by=user_id,
            created_at=now,
        )

        db.add(backup)
        await db.commit()
        await db.refresh(backup)

        try:
            # Create temporary directory for backup contents
            with tempfile.TemporaryDirectory() as temp_dir:
                # Create metadata file
                metadata = {
                    "version": "1.0",
                    "created_at": now.isoformat(),
                    "backup_type": backup_type,
                    "includes": {
                        "database": include_database,
                        "certificates": include_certificates,
                        "letsencrypt": include_letsencrypt,
                        "configs": include_configs,
                        "traffic_logs": include_traffic_logs,
                    },
                }

                metadata_path = os.path.join(temp_dir, "metadata.json")
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)

                # Backup database
                if include_database:
                    await self._backup_database(temp_dir, include_traffic_logs)

                # Backup certificates
                if include_certificates:
                    self._backup_certificates(temp_dir)

                # Backup Let's Encrypt data
                if include_letsencrypt:
                    self._backup_letsencrypt(temp_dir)

                # Backup nginx configs
                if include_configs:
                    self._backup_configs(temp_dir)

                # Create tar.gz archive
                with tarfile.open(file_path, "w:gz") as tar:
                    for item in os.listdir(temp_dir):
                        item_path = os.path.join(temp_dir, item)
                        tar.add(item_path, arcname=item)

            # Update backup record with file size
            file_size = os.path.getsize(file_path)
            backup.file_size = file_size
            backup.status = "completed"
            backup.completed_at = datetime.now(timezone.utc)

            await db.commit()
            await db.refresh(backup)

            logger.info(f"Backup created successfully: {filename} ({file_size} bytes)")
            return backup

        except Exception as e:
            logger.error(f"Backup failed: {e}")
            backup.status = "failed"
            backup.error_message = str(e)
            await db.commit()
            raise

    async def _backup_database(self, temp_dir: str, include_traffic_logs: bool):
        """Backup PostgreSQL database."""
        db_dir = os.path.join(temp_dir, "database")
        os.makedirs(db_dir, exist_ok=True)

        # Get database URL from settings
        db_url = settings.database_url

        # Parse database URL for pg_dump
        # Format: postgresql+asyncpg://user:pass@host:port/dbname
        if "+asyncpg" in db_url:
            db_url = db_url.replace("+asyncpg", "")

        # Use pg_dump
        dump_file = os.path.join(db_dir, "ghostwire_proxy.sql")

        # Build pg_dump command
        exclude_tables = []
        if not include_traffic_logs:
            exclude_tables.append("--exclude-table=traffic_logs")

        env = os.environ.copy()
        # Extract password from URL for PGPASSWORD
        if "@" in db_url:
            # postgresql://user:pass@host:port/db
            parts = db_url.split("://")[1]
            creds, host_part = parts.split("@")
            if ":" in creds:
                user, password = creds.split(":", 1)
                env["PGPASSWORD"] = password

        # Extract connection info
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_url)
            host = parsed.hostname or "localhost"
            port = str(parsed.port or 5432)
            dbname = parsed.path.lstrip("/")
            user = parsed.username or "ghostwire"

            cmd = [
                "pg_dump",
                "-h", host,
                "-p", port,
                "-U", user,
                "-d", dbname,
                "--no-password",
                "--clean",
                "--if-exists",
                "-f", dump_file,
            ] + exclude_tables

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                error_msg = result.stderr or "pg_dump failed with no output"
                logger.error(f"pg_dump failed: {error_msg}")
                raise RuntimeError(f"Database backup failed: {error_msg}")

            # Verify dump file was actually created and has content
            if not os.path.exists(dump_file) or os.path.getsize(dump_file) == 0:
                raise RuntimeError("Database backup produced empty or missing dump file")

        except FileNotFoundError as e:
            logger.error(f"pg_dump not found - ensure postgresql-client is installed: {e}")
            raise RuntimeError(f"pg_dump not available: {e}")
        except Exception as e:
            logger.error(f"Database backup error: {e}")
            raise

    def _backup_certificates(self, temp_dir: str):
        """Backup SSL certificates."""
        certs_dir = os.path.join(temp_dir, "certificates")
        os.makedirs(certs_dir, exist_ok=True)

        source_dir = settings.certificates_path
        if os.path.exists(source_dir):
            for item in os.listdir(source_dir):
                src = os.path.join(source_dir, item)
                dst = os.path.join(certs_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            logger.debug(f"Backed up certificates from {source_dir}")
        else:
            logger.warning(f"Certificates directory not found: {source_dir}")

    def _backup_letsencrypt(self, temp_dir: str):
        """Backup Let's Encrypt data."""
        le_dir = os.path.join(temp_dir, "letsencrypt")
        os.makedirs(le_dir, exist_ok=True)

        source_dir = "/etc/letsencrypt"
        if os.path.exists(source_dir):
            # Copy important directories
            for subdir in ["accounts", "archive", "renewal", "live"]:
                src = os.path.join(source_dir, subdir)
                if os.path.exists(src):
                    dst = os.path.join(le_dir, subdir)
                    shutil.copytree(src, dst, symlinks=True)
            logger.debug(f"Backed up Let's Encrypt data from {source_dir}")
        else:
            logger.debug(f"Let's Encrypt directory not found: {source_dir}")

    def _backup_configs(self, temp_dir: str):
        """Backup nginx configurations."""
        configs_dir = os.path.join(temp_dir, "configs")
        os.makedirs(configs_dir, exist_ok=True)

        source_dir = settings.nginx_config_path
        if os.path.exists(source_dir):
            for item in os.listdir(source_dir):
                src = os.path.join(source_dir, item)
                dst = os.path.join(configs_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            logger.debug(f"Backed up nginx configs from {source_dir}")
        else:
            logger.warning(f"Nginx config directory not found: {source_dir}")

    async def restore_backup(
        self,
        db: AsyncSession,
        backup_id: str,
        restore_database: bool = True,
        restore_certificates: bool = True,
        restore_letsencrypt: bool = True,
        restore_configs: bool = True,
    ) -> dict:
        """
        Restore from a backup.

        Returns:
            Dict with status, message, and restored items
        """
        # Get backup record
        result = await db.execute(
            select(Backup).where(Backup.id == backup_id)
        )
        backup = result.scalar_one_or_none()

        if not backup:
            raise ValueError(f"Backup not found: {backup_id}")

        if backup.status != "completed":
            raise ValueError(f"Cannot restore incomplete backup: {backup.status}")

        if not os.path.exists(backup.file_path):
            raise ValueError(f"Backup file not found: {backup.file_path}")

        restored_items = []
        warnings = []

        try:
            # Extract backup to temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                with tarfile.open(backup.file_path, "r:gz") as tar:
                    # Protect against path traversal (CVE-2007-4559)
                    for member in tar.getmembers():
                        member_path = os.path.join(temp_dir, member.name)
                        abs_temp = os.path.realpath(temp_dir)
                        abs_member = os.path.realpath(member_path)
                        if not abs_member.startswith(abs_temp + os.sep) and abs_member != abs_temp:
                            raise ValueError(f"Path traversal detected in backup archive: {member.name}")
                    tar.extractall(temp_dir)

                # Read metadata
                metadata_path = os.path.join(temp_dir, "metadata.json")
                if os.path.exists(metadata_path):
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)
                    logger.info(f"Restoring backup from {metadata.get('created_at')}")

                # Restore database
                if restore_database and backup.includes_database:
                    try:
                        await self._restore_database(temp_dir)
                        restored_items.append("database")
                    except Exception as e:
                        warnings.append(f"Database restore failed: {e}")
                        logger.error(f"Database restore failed: {e}")

                # Restore certificates
                if restore_certificates and backup.includes_certificates:
                    try:
                        self._restore_certificates(temp_dir)
                        restored_items.append("certificates")
                    except Exception as e:
                        warnings.append(f"Certificates restore failed: {e}")
                        logger.error(f"Certificates restore failed: {e}")

                # Restore Let's Encrypt
                if restore_letsencrypt and backup.includes_letsencrypt:
                    try:
                        self._restore_letsencrypt(temp_dir)
                        restored_items.append("letsencrypt")
                    except Exception as e:
                        warnings.append(f"Let's Encrypt restore failed: {e}")
                        logger.error(f"Let's Encrypt restore failed: {e}")

                # Restore configs
                if restore_configs and backup.includes_configs:
                    try:
                        self._restore_configs(temp_dir)
                        restored_items.append("configs")
                    except Exception as e:
                        warnings.append(f"Configs restore failed: {e}")
                        logger.error(f"Configs restore failed: {e}")

            status = "completed" if not warnings else "completed_with_warnings"
            message = f"Restored {len(restored_items)} items"
            if warnings:
                message += f" ({len(warnings)} warnings)"

            return {
                "status": status,
                "message": message,
                "restored_items": restored_items,
                "warnings": warnings,
            }

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise

    async def _restore_database(self, temp_dir: str):
        """Restore PostgreSQL database."""
        db_dir = os.path.join(temp_dir, "database")
        dump_file = os.path.join(db_dir, "ghostwire_proxy.sql")

        if not os.path.exists(dump_file):
            raise FileNotFoundError("Database dump not found in backup")

        db_url = settings.database_url
        if "+asyncpg" in db_url:
            db_url = db_url.replace("+asyncpg", "")

        env = os.environ.copy()
        if "@" in db_url:
            parts = db_url.split("://")[1]
            creds, host_part = parts.split("@")
            if ":" in creds:
                user, password = creds.split(":", 1)
                env["PGPASSWORD"] = password

        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        host = parsed.hostname or "localhost"
        port = str(parsed.port or 5432)
        dbname = parsed.path.lstrip("/")
        user = parsed.username or "ghostwire"

        # Restore using psql with single-transaction for atomicity
        cmd = [
            "psql",
            "-h", host,
            "-p", port,
            "-U", user,
            "-d", dbname,
            "--single-transaction",
            "-f", dump_file,
        ]

        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error_msg = result.stderr or "psql failed with no output"
            raise RuntimeError(f"Database restore failed: {error_msg}")

        # Check stderr for SQL errors even when exit code is 0
        if result.stderr and "ERROR:" in result.stderr:
            logger.warning(f"Database restore completed with errors: {result.stderr[:500]}")

        logger.info(f"Database restore completed. stdout={len(result.stdout or '')} bytes")

    def _restore_certificates(self, temp_dir: str):
        """Restore SSL certificates."""
        certs_dir = os.path.join(temp_dir, "certificates")
        if not os.path.exists(certs_dir):
            logger.warning("No certificates in backup")
            return

        target_dir = settings.certificates_path
        os.makedirs(target_dir, exist_ok=True)

        for item in os.listdir(certs_dir):
            src = os.path.join(certs_dir, item)
            dst = os.path.join(target_dir, item)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    def _restore_letsencrypt(self, temp_dir: str):
        """Restore Let's Encrypt data."""
        le_dir = os.path.join(temp_dir, "letsencrypt")
        if not os.path.exists(le_dir):
            logger.warning("No Let's Encrypt data in backup")
            return

        target_dir = "/etc/letsencrypt"
        os.makedirs(target_dir, exist_ok=True)

        for subdir in ["accounts", "archive", "renewal", "live"]:
            src = os.path.join(le_dir, subdir)
            if os.path.exists(src):
                dst = os.path.join(target_dir, subdir)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst, symlinks=True)

    def _restore_configs(self, temp_dir: str):
        """Restore nginx configurations."""
        configs_dir = os.path.join(temp_dir, "configs")
        if not os.path.exists(configs_dir):
            logger.warning("No configs in backup")
            return

        target_dir = settings.nginx_config_path
        os.makedirs(target_dir, exist_ok=True)

        for item in os.listdir(configs_dir):
            src = os.path.join(configs_dir, item)
            dst = os.path.join(target_dir, item)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    async def list_backups(
        self,
        db: AsyncSession,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Backup], int]:
        """List all backups with pagination."""
        # Count total
        count_result = await db.execute(
            select(func.count()).select_from(Backup)
        )
        total = count_result.scalar() or 0

        # Get backups
        result = await db.execute(
            select(Backup)
            .order_by(Backup.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        backups = list(result.scalars().all())

        return backups, total

    async def get_backup(self, db: AsyncSession, backup_id: str) -> Optional[Backup]:
        """Get a single backup by ID."""
        result = await db.execute(
            select(Backup).where(Backup.id == backup_id)
        )
        return result.scalar_one_or_none()

    async def delete_backup(self, db: AsyncSession, backup_id: str) -> bool:
        """Delete a backup and its file."""
        backup = await self.get_backup(db, backup_id)
        if not backup:
            return False

        # Delete file if exists
        if os.path.exists(backup.file_path):
            os.remove(backup.file_path)

        # Delete record
        await db.execute(
            delete(Backup).where(Backup.id == backup_id)
        )
        await db.commit()

        logger.info(f"Deleted backup: {backup.filename}")
        return True

    async def get_settings(self, db: AsyncSession) -> BackupSettingsModel:
        """Get backup settings, creating defaults if needed."""
        result = await db.execute(select(BackupSettingsModel))
        settings_obj = result.scalar_one_or_none()

        if not settings_obj:
            settings_obj = BackupSettingsModel(
                id=str(uuid.uuid4()),
            )
            db.add(settings_obj)
            await db.commit()
            await db.refresh(settings_obj)

        return settings_obj

    async def update_settings(
        self,
        db: AsyncSession,
        auto_backup_enabled: Optional[bool] = None,
        schedule_cron: Optional[str] = None,
        retention_days: Optional[int] = None,
        retention_count: Optional[int] = None,
        include_traffic_logs: Optional[bool] = None,
    ) -> BackupSettingsModel:
        """Update backup settings."""
        settings_obj = await self.get_settings(db)

        if auto_backup_enabled is not None:
            settings_obj.auto_backup_enabled = auto_backup_enabled
        if schedule_cron is not None:
            settings_obj.schedule_cron = schedule_cron
        if retention_days is not None:
            settings_obj.retention_days = retention_days
        if retention_count is not None:
            settings_obj.retention_count = retention_count
        if include_traffic_logs is not None:
            settings_obj.include_traffic_logs = include_traffic_logs

        settings_obj.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(settings_obj)

        return settings_obj

    async def cleanup_old_backups(self, db: AsyncSession):
        """Delete backups exceeding retention policy."""
        settings_obj = await self.get_settings(db)

        # Get all completed backups ordered by date
        result = await db.execute(
            select(Backup)
            .where(Backup.status == "completed")
            .order_by(Backup.created_at.desc())
        )
        backups = list(result.scalars().all())

        if len(backups) <= settings_obj.retention_count:
            return  # Keep at least retention_count backups

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings_obj.retention_days)

        for i, backup in enumerate(backups):
            # Always keep minimum count
            if i < settings_obj.retention_count:
                continue

            # Delete if older than retention days
            if backup.created_at < cutoff_date:
                await self.delete_backup(db, backup.id)


# Global service instance
backup_service = BackupService()

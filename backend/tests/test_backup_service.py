"""Tests for backup service."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

from app.services.backup_service import BackupService
from app.models.backup import Backup, BackupSettings


class TestBackupService:
    """Tests for backup CRUD operations."""

    @pytest.mark.asyncio
    async def test_list_backups_empty(self, db_session):
        svc = BackupService()
        backups, total = await svc.list_backups(db_session)
        assert backups == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_backup_not_found(self, db_session):
        svc = BackupService()
        result = await svc.get_backup(db_session, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_backup_not_found(self, db_session):
        svc = BackupService()
        result = await svc.delete_backup(db_session, "nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_create_backup(self, db_session):
        svc = BackupService()
        with patch("os.makedirs"), \
             patch("shutil.make_archive", return_value="/data/backups/test.tar.gz"), \
             patch("os.path.getsize", return_value=1024), \
             patch("shutil.rmtree"), \
             patch("shutil.copy2"), \
             patch("os.path.exists", return_value=True), \
             patch("os.listdir", return_value=[]), \
             patch("tarfile.open", MagicMock()), \
             patch("builtins.open", MagicMock()):
            backup = await svc.create_backup(
                db=db_session,
                user_id="user-1",
                backup_type="manual",
                include_database=False,
                include_certificates=False,
                include_letsencrypt=False,
                include_configs=True,
                include_traffic_logs=False,
            )

        assert backup is not None
        assert backup.backup_type == "manual"
        assert backup.created_by == "user-1"

    @pytest.mark.asyncio
    async def test_get_settings_returns_defaults(self, db_session):
        svc = BackupService()
        settings = await svc.get_settings(db_session)
        assert settings is not None

    @pytest.mark.asyncio
    async def test_update_settings(self, db_session):
        svc = BackupService()
        # First get/create settings
        settings = await svc.get_settings(db_session)

        updated = await svc.update_settings(
            db=db_session,
            auto_backup_enabled=True,
            schedule_cron="0 2 * * *",
        )
        assert updated is not None

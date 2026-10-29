"""Backup API endpoints."""

import asyncio
import json
import os
import tarfile
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.database import get_db
from app.models.backup import Backup
from app.models.user import User
from app.schemas.backup import (
    BackupCreate,
    BackupListResponse,
    BackupResponse,
    BackupSettingsResponse,
    BackupSettingsUpdate,
    RestoreRequest,
    RestoreResponse,
)
from app.services.backup_service import BACKUP_PATH, backup_service, remove_if_exists

router = APIRouter()


class _UnsafeArchiveError(Exception):
    """An uploaded archive has absolute or parent-relative member names."""


def _save_and_inspect_upload(file_path: str, content: bytes) -> dict | None:
    """Write an uploaded backup to disk and read its metadata.json (blocking).

    Raises _UnsafeArchiveError (after deleting the file) on path traversal, and
    tarfile.TarError if it isn't a tar.gz.
    """
    with open(file_path, "wb") as f:
        f.write(content)

    with tarfile.open(file_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                os.remove(file_path)
                raise _UnsafeArchiveError(member.name)
        try:
            meta_file = tar.extractfile(tar.getmember("metadata.json"))
            if meta_file:
                return json.loads(meta_file.read().decode("utf-8"))
        except KeyError, json.JSONDecodeError:
            pass
    return None


@router.get("/", response_model=BackupListResponse)
async def list_backups(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all backups with pagination."""
    backups, total = await backup_service.list_backups(db, page, per_page)

    return BackupListResponse(
        backups=[BackupResponse.model_validate(b) for b in backups],
        total=total,
    )


@router.post("/", response_model=BackupResponse)
async def create_backup(
    backup_options: BackupCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new backup.

    Options:
    - include_database: Include PostgreSQL database dump (default: true)
    - include_certificates: Include SSL certificates (default: true)
    - include_letsencrypt: Include Let's Encrypt data (default: true)
    - include_configs: Include nginx configurations (default: true)
    - include_traffic_logs: Include traffic logs - WARNING: Large! (default: false)
    """
    try:
        backup = await backup_service.create_backup(
            db=db,
            user_id=current_user.id,
            backup_type="manual",
            include_database=backup_options.include_database,
            include_certificates=backup_options.include_certificates,
            include_letsencrypt=backup_options.include_letsencrypt,
            include_configs=backup_options.include_configs,
            include_traffic_logs=backup_options.include_traffic_logs,
        )

        return BackupResponse.model_validate(backup)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/upload", response_model=BackupResponse)
async def upload_backup(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload an existing backup file (.tar.gz) for restore.

    The file must be a valid Ghostwire Proxy backup archive containing a metadata.json.
    """
    if not file.filename or not file.filename.endswith(('.tar.gz', '.tgz')):
        raise HTTPException(status_code=400, detail="File must be a .tar.gz archive")

    # Limit upload size to 500MB
    max_size = 500 * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="File too large (max 500MB)")

    # Save to temp location first, then validate
    backup_id = str(uuid.uuid4())
    safe_filename = f"uploaded_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.tar.gz"
    file_path = os.path.join(BACKUP_PATH, safe_filename)

    try:
        try:
            metadata = await asyncio.to_thread(_save_and_inspect_upload, file_path, content)
        except _UnsafeArchiveError:
            raise HTTPException(status_code=400, detail="Invalid archive: path traversal detected") from None

        # Create backup record
        includes = metadata.get("includes", {}) if metadata else {}
        backup = Backup(
            id=backup_id,
            filename=safe_filename,
            file_path=file_path,
            file_size=len(content),
            backup_type="uploaded",
            includes_database=includes.get("database", False),
            includes_certificates=includes.get("certificates", False),
            includes_letsencrypt=includes.get("letsencrypt", False),
            includes_configs=includes.get("configs", False),
            includes_traffic_logs=includes.get("traffic_logs", False),
            status="completed",
            created_by=current_user.id,
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

        db.add(backup)
        await db.commit()
        await db.refresh(backup)

        return BackupResponse.model_validate(backup)

    except HTTPException:
        raise
    except tarfile.TarError:
        await asyncio.to_thread(remove_if_exists, file_path)
        raise HTTPException(status_code=400, detail="Invalid or corrupted tar.gz archive") from None
    except Exception as e:
        await asyncio.to_thread(remove_if_exists, file_path)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{backup_id}", response_model=BackupResponse)
async def get_backup(
    backup_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single backup by ID."""
    backup = await backup_service.get_backup(db, backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    return BackupResponse.model_validate(backup)


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a backup file."""
    backup = await backup_service.get_backup(db, backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if backup.status != "completed":
        raise HTTPException(status_code=400, detail="Backup is not complete")

    if not await asyncio.to_thread(os.path.exists, backup.file_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    return FileResponse(
        path=backup.file_path,
        filename=backup.filename,
        media_type="application/gzip",
    )


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a backup."""
    deleted = await backup_service.delete_backup(db, backup_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Backup not found")

    return {"status": "ok", "message": "Backup deleted"}


@router.post("/restore", response_model=RestoreResponse)
async def restore_backup(
    restore_request: RestoreRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Restore from a backup.

    WARNING: This will overwrite existing data!

    Options:
    - backup_id: ID of the backup to restore
    - restore_database: Restore database (default: true)
    - restore_certificates: Restore SSL certificates (default: true)
    - restore_letsencrypt: Restore Let's Encrypt data (default: true)
    - restore_configs: Restore nginx configurations (default: true)
    """
    if not restore_request.backup_id:
        raise HTTPException(status_code=400, detail="backup_id is required")

    try:
        result = await backup_service.restore_backup(
            db=db,
            backup_id=restore_request.backup_id,
            restore_database=restore_request.restore_database,
            restore_certificates=restore_request.restore_certificates,
            restore_letsencrypt=restore_request.restore_letsencrypt,
            restore_configs=restore_request.restore_configs,
        )

        return RestoreResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/settings/current", response_model=BackupSettingsResponse)
async def get_backup_settings(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get backup settings."""
    settings = await backup_service.get_settings(db)
    return BackupSettingsResponse.model_validate(settings)


@router.put("/settings/current", response_model=BackupSettingsResponse)
async def update_backup_settings(
    settings_update: BackupSettingsUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update backup settings."""
    settings = await backup_service.update_settings(
        db=db,
        auto_backup_enabled=settings_update.auto_backup_enabled,
        schedule_cron=settings_update.schedule_cron,
        retention_days=settings_update.retention_days,
        retention_count=settings_update.retention_count,
        include_traffic_logs=settings_update.include_traffic_logs,
    )
    return BackupSettingsResponse.model_validate(settings)


@router.post("/cleanup")
async def cleanup_old_backups(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger cleanup of old backups based on retention policy."""
    await backup_service.cleanup_old_backups(db)
    return {"status": "ok", "message": "Cleanup completed"}

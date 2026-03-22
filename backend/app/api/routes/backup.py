"""Backup API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
import os
import tarfile
import json
import uuid
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.user import User
from app.models.backup import Backup
from app.api.deps import get_current_user
from app.services.backup_service import backup_service, BACKUP_PATH
from app.schemas.backup import (
    BackupCreate,
    BackupResponse,
    BackupListResponse,
    BackupSettingsResponse,
    BackupSettingsUpdate,
    RestoreRequest,
    RestoreResponse,
)

router = APIRouter()


@router.get("/", response_model=BackupListResponse)
async def list_backups(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=BackupResponse)
async def upload_backup(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
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
    safe_filename = f"uploaded_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.tar.gz"
    file_path = os.path.join(BACKUP_PATH, safe_filename)

    try:
        with open(file_path, "wb") as f:
            f.write(content)

        # Validate it's a valid tar.gz with metadata
        metadata = None
        with tarfile.open(file_path, "r:gz") as tar:
            # Security: check for path traversal
            for member in tar.getmembers():
                if member.name.startswith('/') or '..' in member.name:
                    os.remove(file_path)
                    raise HTTPException(status_code=400, detail="Invalid archive: path traversal detected")

            # Look for metadata.json
            try:
                meta_member = tar.getmember("metadata.json")
                meta_file = tar.extractfile(meta_member)
                if meta_file:
                    metadata = json.loads(meta_file.read().decode('utf-8'))
            except (KeyError, json.JSONDecodeError):
                pass

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
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )

        db.add(backup)
        await db.commit()
        await db.refresh(backup)

        return BackupResponse.model_validate(backup)

    except HTTPException:
        raise
    except tarfile.TarError:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail="Invalid or corrupted tar.gz archive")
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{backup_id}", response_model=BackupResponse)
async def get_backup(
    backup_id: str,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a backup file."""
    backup = await backup_service.get_backup(db, backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if backup.status != "completed":
        raise HTTPException(status_code=400, detail="Backup is not complete")

    if not os.path.exists(backup.file_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    return FileResponse(
        path=backup.file_path,
        filename=backup.filename,
        media_type="application/gzip",
    )


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: str,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/current", response_model=BackupSettingsResponse)
async def get_backup_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get backup settings."""
    settings = await backup_service.get_settings(db)
    return BackupSettingsResponse.model_validate(settings)


@router.put("/settings/current", response_model=BackupSettingsResponse)
async def update_backup_settings(
    settings_update: BackupSettingsUpdate,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger cleanup of old backups based on retention policy."""
    await backup_service.cleanup_old_backups(db)
    return {"status": "ok", "message": "Cleanup completed"}

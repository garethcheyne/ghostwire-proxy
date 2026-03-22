from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import engine, Base
from app.core.redis import close_redis
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.api import router as api_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_app_version() -> str:
    """Read application version from VERSION file."""
    version_file = Path(__file__).parent.parent.parent / "VERSION"
    try:
        if version_file.exists():
            return version_file.read_text().strip()
    except Exception:
        pass
    return os.environ.get("APP_VERSION", "1.0.0")


APP_VERSION = get_app_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Ghostwire Proxy API...")

    # Ensure data directories exist
    os.makedirs(settings.nginx_config_path, exist_ok=True)
    os.makedirs(settings.certificates_path, exist_ok=True)

    # Create database tables if they don't exist
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            # Add preset_id columns if missing (for existing databases)
            from sqlalchemy import text, inspect as sa_inspect

            def _add_missing_columns(connection):
                inspector = sa_inspect(connection)
                # Add preset_id columns
                tables = ["waf_rule_sets", "waf_rules", "rate_limit_rules", "geoip_rules", "threat_thresholds"]
                for table in tables:
                    if table in inspector.get_table_names():
                        columns = [c["name"] for c in inspector.get_columns(table)]
                        if "preset_id" not in columns:
                            connection.execute(text(f'ALTER TABLE {table} ADD COLUMN preset_id VARCHAR(100)'))
                            logger.info(f"Added preset_id column to {table}")
                # Add tags/country_name to threat_actors
                if "threat_actors" in inspector.get_table_names():
                    columns = [c["name"] for c in inspector.get_columns("threat_actors")]
                    if "tags" not in columns:
                        connection.execute(text('ALTER TABLE threat_actors ADD COLUMN tags TEXT'))
                        logger.info("Added tags column to threat_actors")
                    if "country_name" not in columns:
                        connection.execute(text('ALTER TABLE threat_actors ADD COLUMN country_name VARCHAR(100)'))
                        logger.info("Added country_name column to threat_actors")
                # Add country_name to traffic_logs
                if "traffic_logs" in inspector.get_table_names():
                    columns = [c["name"] for c in inspector.get_columns("traffic_logs")]
                    if "country_name" not in columns:
                        connection.execute(text('ALTER TABLE traffic_logs ADD COLUMN country_name VARCHAR(100)'))
                        logger.info("Added country_name column to traffic_logs")

            await conn.run_sync(_add_missing_columns)

        logger.info("Database tables verified/created")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    # Check if setup is required
    from app.models.user import User
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count(User.id)))
        count = result.scalar() or 0

        if count == 0:
            logger.info("No users found - initial setup required at /auth/login")
        else:
            logger.info(f"Found {count} users in database")

    # Start background metrics collection task
    from app.services.system_service import system_monitor_service

    async def metrics_collection_loop():
        """Periodically collect system metrics."""
        while True:
            try:
                await asyncio.sleep(60)  # Collect every 60 seconds
                await system_monitor_service.collect_and_store_metrics()
            except asyncio.CancelledError:
                logger.info("Metrics collection task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in metrics collection: {e}")

    metrics_task = asyncio.create_task(metrics_collection_loop())
    logger.info("Started background metrics collection task")

    # Scheduled backup task
    from app.services.backup_service import backup_service
    from croniter import croniter

    async def scheduled_backup_loop():
        """Check and run scheduled backups based on cron settings."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                async with AsyncSessionLocal() as session:
                    settings_obj = await backup_service.get_settings(session)
                    if not settings_obj.auto_backup_enabled:
                        continue

                    # Calculate next run time from cron expression
                    now = datetime.now(timezone.utc)
                    try:
                        cron = croniter(settings_obj.schedule_cron, now - timedelta(minutes=1))
                        next_run = cron.get_next(datetime)
                    except (ValueError, KeyError):
                        logger.error(f"Invalid cron expression: {settings_obj.schedule_cron}")
                        continue

                    # Check if we're within the current minute window
                    if abs((next_run - now).total_seconds()) < 60:
                        logger.info("Running scheduled backup...")
                        try:
                            await backup_service.create_backup(
                                db=session,
                                backup_type="scheduled",
                                include_database=True,
                                include_certificates=True,
                                include_letsencrypt=True,
                                include_configs=True,
                                include_traffic_logs=settings_obj.include_traffic_logs,
                            )
                            # Run cleanup after scheduled backup
                            await backup_service.cleanup_old_backups(session)
                            logger.info("Scheduled backup completed successfully")
                        except Exception as e:
                            logger.error(f"Scheduled backup failed: {e}")
            except asyncio.CancelledError:
                logger.info("Scheduled backup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in backup scheduler: {e}")

    backup_task = asyncio.create_task(scheduled_backup_loop())
    logger.info("Started scheduled backup task")

    yield

    # Cancel background tasks
    metrics_task.cancel()
    backup_task.cancel()
    try:
        await metrics_task
    except asyncio.CancelledError:
        pass
    try:
        await backup_task
    except asyncio.CancelledError:
        pass

    # Shutdown
    logger.info("Shutting down Ghostwire Proxy API...")
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Ghostwire Proxy API",
    description="Reverse Proxy Management API",
    version=APP_VERSION,
    lifespan=lifespan,
    redirect_slashes=True,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        # Remove server identification headers
        if "server" in response.headers:
            del response.headers["server"]
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ghostwire-proxy-api"}


@app.get("/version")
async def get_version():
    """Get application version information."""
    return {
        "version": APP_VERSION,
        "service": "ghostwire-proxy-api",
    }


# Include API routes
app.include_router(api_router, prefix="/api")

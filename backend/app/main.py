from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import json
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
from app.core.version import APP_VERSION
from app.api import router as api_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ADMIN_PROXY_TAG = "ghostwire-admin-ui"


async def _auto_provision_admin_proxy():
    """
    If NEXTAUTH_URL contains an FQDN (not an IP / localhost), automatically
    create a proxy host that routes that domain to the admin UI container
    and request a Let's Encrypt certificate for it.

    This makes the admin panel accessible via https://fqdn instead of
    requiring direct IP:port access.
    """
    from urllib.parse import urlparse
    import ipaddress
    from app.core.database import AsyncSessionLocal
    from app.models.proxy_host import ProxyHost
    from app.models.certificate import Certificate
    from app.services.openresty_service import generate_all_configs, reload_nginx
    from app.services.certificate_service import request_letsencrypt_certificate
    from sqlalchemy import select

    nextauth_url = os.environ.get("NEXTAUTH_URL", "")
    if not nextauth_url:
        return

    parsed = urlparse(nextauth_url)
    hostname = parsed.hostname or ""

    if not hostname:
        return

    # Skip if it's an IP address or localhost
    try:
        ipaddress.ip_address(hostname)
        logger.debug("NEXTAUTH_URL is an IP address — skipping admin proxy auto-provision")
        return
    except ValueError:
        pass  # Not an IP — good, it's probably an FQDN

    if hostname in ("localhost", "127.0.0.1", "::1"):
        return

    logger.info(f"NEXTAUTH_URL has FQDN '{hostname}' — checking admin proxy auto-provision...")

    async with AsyncSessionLocal() as db:
        try:
            # Check if a proxy host already exists for this domain
            result = await db.execute(select(ProxyHost))
            all_hosts = result.scalars().all()

            for host in all_hosts:
                domains = host.domain_names or []
                if hostname in domains:
                    logger.info(f"Proxy host already exists for '{hostname}' (id={host.id}) — skipping")
                    return

            # Create Let's Encrypt certificate
            le_email = os.environ.get("LETSENCRYPT_EMAIL", "")
            if not le_email:
                logger.warning("No LETSENCRYPT_EMAIL set — cannot auto-provision SSL cert for admin UI")
                logger.info(f"Creating admin proxy host for '{hostname}' without SSL")
                # Create HTTP-only proxy host
                host = ProxyHost(
                    domain_names=[hostname],
                    forward_scheme="http",
                    forward_host="ghostwire-proxy-ui",
                    forward_port=3000,
                    ssl_enabled=False,
                    websockets_support=True,
                    block_exploits=True,
                    enabled=True,
                    advanced_config=f"# Auto-provisioned admin UI proxy ({ADMIN_PROXY_TAG})",
                )
                db.add(host)
                await db.commit()
                await generate_all_configs(db)
                reload_nginx()
                logger.info(f"Auto-provisioned HTTP proxy host for admin UI at http://{hostname}")
                return

            # Create certificate record first
            cert = Certificate(
                name=f"Admin UI - {hostname}",
                domain_names=[hostname],
                is_letsencrypt=True,
                letsencrypt_email=le_email,
                auto_renew=True,
                status="pending",
            )
            db.add(cert)
            await db.commit()
            await db.refresh(cert)

            # Create proxy host (initially HTTP-only so ACME challenge works)
            host = ProxyHost(
                domain_names=[hostname],
                forward_scheme="http",
                forward_host="ghostwire-proxy-ui",
                forward_port=3000,
                ssl_enabled=False,
                websockets_support=True,
                block_exploits=True,
                enabled=True,
                advanced_config=f"# Auto-provisioned admin UI proxy ({ADMIN_PROXY_TAG})",
            )
            db.add(host)
            await db.commit()
            await db.refresh(host)

            # Generate HTTP config so nginx can serve ACME challenge
            await generate_all_configs(db)
            reload_nginx()
            logger.info(f"Created HTTP proxy host for '{hostname}' — requesting Let's Encrypt cert...")

            # Request Let's Encrypt certificate
            success, message = await request_letsencrypt_certificate(db, cert.id)

            if success:
                await db.refresh(cert)
                # Enable SSL on the proxy host
                host.ssl_enabled = True
                host.ssl_force = True
                host.http2_support = True
                host.hsts_enabled = True
                host.certificate_id = cert.id
                await db.commit()

                # Regenerate with SSL
                await generate_all_configs(db)
                reload_nginx()
                logger.info(f"Auto-provisioned HTTPS proxy host for admin UI at https://{hostname}")
            else:
                logger.warning(f"Let's Encrypt cert request failed: {message}")
                logger.info(f"Admin UI accessible via HTTP at http://{hostname} — retry cert via UI later")

        except Exception as e:
            logger.error(f"Admin proxy auto-provision failed: {e}")
            # Non-fatal — admin UI still accessible via IP:88


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
                # Add honeypot_enabled to proxy_hosts
                if "proxy_hosts" in inspector.get_table_names():
                    columns = [c["name"] for c in inspector.get_columns("proxy_hosts")]
                    if "honeypot_enabled" not in columns:
                        connection.execute(text('ALTER TABLE proxy_hosts ADD COLUMN honeypot_enabled BOOLEAN DEFAULT false'))
                        logger.info("Added honeypot_enabled column to proxy_hosts")
                # Add proxy_host_id to honeypot_traps
                if "honeypot_traps" in inspector.get_table_names():
                    columns = [c["name"] for c in inspector.get_columns("honeypot_traps")]
                    if "proxy_host_id" not in columns:
                        connection.execute(text('ALTER TABLE honeypot_traps ADD COLUMN proxy_host_id VARCHAR(36) REFERENCES proxy_hosts(id) ON DELETE CASCADE'))
                        logger.info("Added proxy_host_id column to honeypot_traps")
                    # Remove unique constraint on path (now unique per host)
                    try:
                        connection.execute(text('ALTER TABLE honeypot_traps DROP CONSTRAINT IF EXISTS honeypot_traps_path_key'))
                    except Exception:
                        pass  # Constraint may not exist
                # Add proxy_host_id to waf_rules
                if "waf_rules" in inspector.get_table_names():
                    columns = [c["name"] for c in inspector.get_columns("waf_rules")]
                    if "proxy_host_id" not in columns:
                        connection.execute(text('ALTER TABLE waf_rules ADD COLUMN proxy_host_id VARCHAR(36) REFERENCES proxy_hosts(id) ON DELETE CASCADE'))
                        logger.info("Added proxy_host_id column to waf_rules")

                # Add FK constraints on rate_limit_rules.proxy_host_id and geoip_rules.proxy_host_id
                for table in ["rate_limit_rules", "geoip_rules"]:
                    if table in inspector.get_table_names():
                        fks = inspector.get_foreign_keys(table)
                        has_host_fk = any(
                            fk.get("referred_table") == "proxy_hosts" and "proxy_host_id" in fk.get("constrained_columns", [])
                            for fk in fks
                        )
                        if not has_host_fk:
                            # Clean orphan rows referencing deleted proxy hosts
                            connection.execute(text(
                                f'DELETE FROM {table} WHERE proxy_host_id IS NOT NULL '
                                f'AND proxy_host_id NOT IN (SELECT id FROM proxy_hosts)'
                            ))
                            fk_name = f"fk_{table}_proxy_host_id"
                            connection.execute(text(
                                f'ALTER TABLE {table} ADD CONSTRAINT {fk_name} '
                                f'FOREIGN KEY (proxy_host_id) REFERENCES proxy_hosts(id) ON DELETE CASCADE'
                            ))
                            logger.info(f"Added FK constraint on {table}.proxy_host_id")

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

    # Auto-provision admin UI proxy host + SSL cert if NEXTAUTH_URL is an FQDN
    await _auto_provision_admin_proxy()

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

    # GeoIP database auto-update (checks monthly)
    async def geoip_update_loop():
        """Check and update GeoIP database on the 2nd of each month."""
        from app.services.geoip_service import get_db_info, update_database
        while True:
            try:
                # Check every 24 hours
                await asyncio.sleep(86400)
                now = datetime.now(timezone.utc)
                # Update on the 2nd of each month (DB-IP publishes on the 1st)
                info = get_db_info()
                if not info["installed"]:
                    logger.info("GeoIP database not found, downloading...")
                    result = await update_database()
                    logger.info(f"GeoIP auto-update: {result['status']} - {result['message']}")
                elif info["last_modified"]:
                    last_mod = datetime.fromisoformat(info["last_modified"])
                    # If DB is older than 35 days, update it
                    if (now - last_mod).days > 35:
                        logger.info("GeoIP database is outdated, updating...")
                        result = await update_database()
                        logger.info(f"GeoIP auto-update: {result['status']} - {result['message']}")
            except asyncio.CancelledError:
                logger.info("GeoIP update task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in GeoIP updater: {e}")

    geoip_task = asyncio.create_task(geoip_update_loop())
    logger.info("Started GeoIP auto-update task")

    # Update check loop — checks GitHub releases + Docker Hub digests
    from app.services.update_service import update_service
    from app.core.redis import get_redis as _get_redis

    async def update_check_loop():
        """Periodically check for app and base image updates."""
        # Wait 2 minutes on startup before first check
        await asyncio.sleep(120)
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    update_settings = await update_service.get_settings(session)
                    if not update_settings.auto_check_enabled:
                        await asyncio.sleep(3600)
                        continue

                    # Check if enough time has elapsed since last check
                    now = datetime.now(timezone.utc)
                    if (update_settings.last_check and
                            (now - update_settings.last_check).total_seconds() <
                            update_settings.check_interval_hours * 3600):
                        await asyncio.sleep(600)  # Re-check eligibility in 10 min
                        continue

                    logger.info("Running scheduled update check...")

                    # Check app updates
                    app_result = await update_service.check_for_app_updates(session)

                    # Check base image updates
                    base_results = await update_service.check_for_base_image_updates(session)
                    base_updates = [r for r in base_results if r.get("update_available")]

                    # Cache results in Redis for fast frontend polling
                    try:
                        redis = await _get_redis()
                        cache = {
                            "checked_at": now.isoformat(),
                            "app_update_available": str(app_result.get("update_available", False)),
                            "app_latest_version": app_result.get("latest_version") or "",
                            "app_current_version": app_result.get("current_version", APP_VERSION),
                            "base_image_updates": str(len(base_updates)),
                            "base_image_details": json.dumps([
                                {"container": r["container"], "image": r["image"]}
                                for r in base_updates
                            ]),
                        }
                        await redis.hset("ghostwire:update_check", mapping=cache)
                        # Expire after 2x check interval
                        await redis.expire(
                            "ghostwire:update_check",
                            update_settings.check_interval_hours * 7200
                        )
                    except Exception as e:
                        logger.debug(f"Failed to cache update check results: {e}")

                    # Update last_check timestamp
                    update_settings.last_check = now
                    await session.commit()

                    # Auto-update base images if enabled and updates found
                    if update_settings.auto_update_security and base_updates:
                        logger.info(
                            f"Auto-updating {len(base_updates)} base image(s): "
                            f"{', '.join(r['container'] for r in base_updates)}"
                        )
                        for img in base_updates:
                            try:
                                await update_service.request_base_image_update(
                                    db=session,
                                    container_name=img["container"],
                                    user_id="system-auto-update",
                                )
                                # Wait for each update to complete before next
                                await asyncio.sleep(120)
                            except ValueError as e:
                                logger.warning(f"Auto-update skipped for {img['container']}: {e}")

                    if app_result.get("update_available"):
                        logger.info(
                            f"App update available: "
                            f"v{APP_VERSION} → v{app_result['latest_version']}"
                        )
                    if base_updates:
                        logger.info(
                            f"Base image updates available: "
                            f"{', '.join(r['container'] for r in base_updates)}"
                        )

                # Sleep for the configured interval
                await asyncio.sleep(update_settings.check_interval_hours * 3600)

            except asyncio.CancelledError:
                logger.info("Update check task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in update checker: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour on error

    update_check_task = asyncio.create_task(update_check_loop())
    logger.info("Started update check task")

    # IP enrichment backfill — enrich traffic IPs that haven't been looked up yet
    from app.services.enrichment_service import backfill_enrichment, cleanup_stale_enrichments

    async def enrichment_backfill_loop():
        """Periodically backfill IP enrichment for traffic log IPs."""
        # Wait 30 seconds on startup before first batch
        await asyncio.sleep(30)
        cleanup_counter = 0
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    result = await backfill_enrichment(session)
                    if result["enriched"] > 0:
                        logger.info(
                            "IP enrichment backfill: enriched %d IPs, %d remaining",
                            result["enriched"], result["remaining"],
                        )

                    # Run stale record cleanup every ~6 hours (72 iterations * 300s)
                    cleanup_counter += 1
                    if cleanup_counter >= 72:
                        cleanup_counter = 0
                        async with AsyncSessionLocal() as cleanup_session:
                            await cleanup_stale_enrichments(cleanup_session)

                    if result["status"] == "complete":
                        # All caught up — check again in 5 minutes
                        await asyncio.sleep(300)
                    else:
                        # More to do — short pause then next batch
                        await asyncio.sleep(10)
            except asyncio.CancelledError:
                logger.info("IP enrichment backfill task cancelled")
                break
            except Exception as e:
                logger.error("Error in enrichment backfill: %s", e)
                await asyncio.sleep(60)

    enrichment_backfill_task = asyncio.create_task(enrichment_backfill_loop())
    logger.info("Started IP enrichment backfill task")

    yield

    # Cancel background tasks
    metrics_task.cancel()
    backup_task.cancel()
    geoip_task.cancel()
    update_check_task.cancel()
    enrichment_backfill_task.cancel()
    try:
        await metrics_task
    except asyncio.CancelledError:
        pass
    try:
        await backup_task
    except asyncio.CancelledError:
        pass
    try:
        await geoip_task
    except asyncio.CancelledError:
        pass
    try:
        await update_check_task
    except asyncio.CancelledError:
        pass
    try:
        await enrichment_backfill_task
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

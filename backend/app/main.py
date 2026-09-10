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

    # Database migrations are handled by Alembic in entrypoint.sh
    # (alembic upgrade head runs before the app starts)
    logger.info("Database migrations handled by Alembic via entrypoint")

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
        """Check and run scheduled backups based on cron settings.

        `last_fired_slot` records which cron occurrence has already been served.
        Without it the same slot fired twice: the loop ticks every 60s and the
        window test used abs(), so a 02:00 backup matched at 01:59:47 (13s
        before the slot) and again at 02:00:56 (56s after it) — two full
        backups a minute apart, which also burned through the retention count
        at twice the intended rate. Observed on 2026-09-10 at 01:59:47 and
        02:00:56.
        """
        last_fired_slot: datetime | None = None

        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                async with AsyncSessionLocal() as session:
                    settings_obj = await backup_service.get_settings(session)
                    if not settings_obj.auto_backup_enabled:
                        continue

                    # Work from the most recent scheduled occurrence at or
                    # before now, rather than the next one. Seeding croniter
                    # from `now - 1 minute` and taking get_next() only works
                    # while a tick lands inside that minute — the loop sleeps
                    # 60s *plus* however long the previous backup took, so
                    # drift eventually pushes every tick past the window and
                    # the backup is skipped for the day. get_prev() has no such
                    # edge.
                    now = datetime.now(timezone.utc)
                    try:
                        slot = croniter(settings_obj.schedule_cron, now).get_prev(datetime)
                    except (ValueError, KeyError):
                        logger.error(f"Invalid cron expression: {settings_obj.schedule_cron}")
                        continue

                    # Fire once per occurrence, only after it has arrived, and
                    # only if it is still recent (so a restart does not replay
                    # an occurrence from hours ago).
                    age = (now - slot).total_seconds()
                    if 0 <= age < 600 and slot != last_fired_slot:
                        last_fired_slot = slot
                        logger.info("Running scheduled backup...")
                        try:
                            created_backup = await backup_service.create_backup(
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
                            try:
                                from app.services.push_service import push_service
                                await push_service.notify_backup_completed(
                                    backup_id=created_backup.id,
                                    size_mb=round((created_backup.file_size or 0) / 1048576, 1),
                                    db=session,
                                )
                            except Exception as notify_err:
                                logger.debug(f"Backup success notification skipped: {notify_err}")
                        except Exception as e:
                            logger.error(f"Scheduled backup failed: {e}")
                            # A silent backup failure is how the August purge became
                            # unrecoverable. Make it loud on every channel.
                            try:
                                from app.services.push_service import push_service
                                from app.services.alert_service import dispatch_alert
                                await push_service.notify_backup_failed(error=str(e), db=session)
                                await dispatch_alert(
                                    db=session,
                                    alert_type="backup_failed",
                                    severity="critical",
                                    title="Backup Failed",
                                    message=f"The scheduled backup did not complete: {e}",
                                    data={"error": str(e)},
                                    skip_push=True,
                                )
                            except Exception as notify_err:
                                logger.error(f"Could not raise backup-failure alert: {notify_err}")
            except asyncio.CancelledError:
                logger.info("Scheduled backup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in backup scheduler: {e}")

    backup_task = asyncio.create_task(scheduled_backup_loop())
    logger.info("Started scheduled backup task")

    # Upstream health monitoring — notifies when a proxy host goes down or recovers
    from app.services.health_service import run_health_checks

    async def health_check_loop():
        """Probe every enabled host's upstream and alert on state changes."""
        # Let nginx and the upstreams settle after a restart before the first
        # probe, so a slow-starting backend isn't reported as an outage.
        await asyncio.sleep(90)
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    await run_health_checks(session)
            except asyncio.CancelledError:
                logger.info("Health check task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                logger.info("Health check task cancelled")
                break

    health_task = asyncio.create_task(health_check_loop())
    logger.info("Started upstream health monitoring task")

    # Refresh the CDN edge ranges nginx trusts for real-client-IP headers
    from app.services.trusted_proxy_service import refresh_ranges

    async def trusted_proxy_refresh_loop():
        """Keep Cloudflare/Imperva edge ranges current (checked daily).

        A stale list means either the CDN's own address gets logged and blocked
        as if it were the visitor, or a range we should no longer trust still is.
        """
        await asyncio.sleep(30)
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    await refresh_ranges(session)
            except asyncio.CancelledError:
                logger.info("Trusted proxy refresh task cancelled")
                break
            except Exception as e:
                logger.error(f"Error refreshing trusted proxy ranges: {e}")
            try:
                await asyncio.sleep(86400)
            except asyncio.CancelledError:
                logger.info("Trusted proxy refresh task cancelled")
                break

    trusted_proxy_task = asyncio.create_task(trusted_proxy_refresh_loop())
    logger.info("Started trusted proxy range refresh task")

    # GeoIP database auto-update (checks monthly)
    async def geoip_update_loop():
        """Check and update GeoIP database. Runs an immediate check on startup
        (so fresh installs get a database without waiting 24 hours), then checks
        every 24 hours afterwards."""
        from app.services.geoip_service import get_db_info, update_database

        async def check_and_update():
            now = datetime.now(timezone.utc)
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

        # Run an initial check immediately on startup so that fresh deployments
        # don't have to wait 24h for the first download (which causes nginx to
        # log "GeoIP database not found" warnings until then).
        try:
            await check_and_update()
        except Exception as e:
            logger.error(f"Error in initial GeoIP check: {e}")

        while True:
            try:
                # Check every 24 hours
                await asyncio.sleep(86400)
                await check_and_update()
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
        """Periodically backfill IP enrichment for traffic log IPs.

        Off by default. It walked every distinct client_ip in traffic_logs in
        batches of 40 every 5 minutes — around 480 AbuseIPDB /check calls an
        hour against a free tier of roughly 1,000 a day, which is why 641
        lookups in one day came back HTTP 429 and enrichment stopped working
        at all. Enrichment still happens on demand when an IP is actually
        looked at, which is the traffic that matters.

        Set the `enrichment_backfill_enabled` setting to "true" to turn the
        sweep back on — worth doing only with a paid AbuseIPDB plan, or with no
        AbuseIPDB key at all (ip-api.com is free and separately rate-limited).
        """
        await asyncio.sleep(30)
        cleanup_counter = 0
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    from app.models.setting import Setting as _Setting
                    from sqlalchemy import select as _select

                    _row = (await session.execute(
                        _select(_Setting).where(_Setting.key == "enrichment_backfill_enabled")
                    )).scalar_one_or_none()
                    _enabled = bool(_row and str(_row.value).strip().lower() in ("true", "1", "yes", "on"))

                    if not _enabled:
                        # Still run the stale-record cleanup; it costs no API calls.
                        cleanup_counter += 1
                        if cleanup_counter >= 72:
                            cleanup_counter = 0
                            await cleanup_stale_enrichments(session)
                        await asyncio.sleep(300)
                        continue

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

    # AbuseIPDB blacklist sync — pulls the confidenceMinimum=75 blacklist into a
    # local table so per-IP enrichment can check known-bad IPs for free instead
    # of spending a metered /check call on every honeypot hit. sync_abuseipdb_blacklist()
    # itself no-ops if synced within BLACKLIST_SYNC_MIN_INTERVAL, so it's safe to
    # just check every hour and let it decide - that endpoint's own rate limit
    # is far tighter than /check (as low as 5 req/day on some plans).
    from app.services.enrichment_service import sync_abuseipdb_blacklist

    async def abuseipdb_blacklist_sync_loop():
        """Periodically refresh the local AbuseIPDB blacklist cache."""
        await asyncio.sleep(45)
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    from app.models.setting import Setting
                    setting_result = await session.execute(
                        select(Setting).where(Setting.key == "abuseipdb_api_key")
                    )
                    setting = setting_result.scalar_one_or_none()
                    if setting and setting.value:
                        result = await sync_abuseipdb_blacklist(session, setting.value)
                        if result["status"] == "synced":
                            logger.info(
                                "AbuseIPDB blacklist sync: cached %d known-bad IPs",
                                result["count"],
                            )
            except asyncio.CancelledError:
                logger.info("AbuseIPDB blacklist sync task cancelled")
                break
            except Exception as e:
                logger.error("Error in AbuseIPDB blacklist sync: %s", e)
            await asyncio.sleep(3600)  # check hourly; sync itself is rate-limited internally

    abuseipdb_blacklist_task = asyncio.create_task(abuseipdb_blacklist_sync_loop())
    logger.info("Started AbuseIPDB blacklist sync task")

    # AbuseIPDB reporting — submits confirmed attackers (ThreatActor rows that
    # escalated to temp_blocked+) back to AbuseIPDB via /bulk-report. Opt-in:
    # gated on the `abuseipdb_auto_report_enabled` setting (default off,
    # toggle lives in Settings next to the API key). Trusted IPs are always
    # excluded so testing from an admin's own IP never gets reported.
    from app.services.abuseipdb_report_service import submit_bulk_reports

    async def abuseipdb_report_loop():
        """Periodically report newly-escalated threat actors to AbuseIPDB."""
        await asyncio.sleep(60)
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    from app.models.setting import Setting
                    key_result = await session.execute(
                        select(Setting).where(Setting.key == "abuseipdb_api_key")
                    )
                    key_setting = key_result.scalar_one_or_none()
                    enabled_result = await session.execute(
                        select(Setting).where(Setting.key == "abuseipdb_auto_report_enabled")
                    )
                    enabled_setting = enabled_result.scalar_one_or_none()

                    if (
                        key_setting and key_setting.value
                        and enabled_setting and enabled_setting.value == "true"
                    ):
                        result = await submit_bulk_reports(session, key_setting.value)
                        if result["status"] == "reported":
                            logger.info(
                                "AbuseIPDB report: submitted %d IPs (%d accepted, %d rejected, %d skipped as trusted)",
                                result["submitted"], result["accepted"], result["rejected"], result["skipped_trusted"],
                            )
            except asyncio.CancelledError:
                logger.info("AbuseIPDB report task cancelled")
                break
            except Exception as e:
                logger.error("Error in AbuseIPDB report loop: %s", e)
            await asyncio.sleep(3600)  # check hourly; sync itself is rate-limited internally

    abuseipdb_report_task = asyncio.create_task(abuseipdb_report_loop())
    logger.info("Started AbuseIPDB report task")

    # Data retention cleanup — prune old traffic_logs, threat_events, audit_logs daily
    from app.services.retention_service import run_retention_cleanup
    from app.services.analytics_service import (
        aggregate_hourly, aggregate_daily, aggregate_geo,
    )

    async def roll_up_analytics(hours_back: int = 3, days_back: int = 2) -> None:
        """Summarise traffic_logs into the analytics_* tables.

        Deliberately called from inside the retention loop, immediately before the
        prune: rolling up has to happen before rows are deleted, and making that
        ordering structural is safer than running two loops that merely happen to
        be scheduled apart.
        """
        async with AsyncSessionLocal() as session:
            h = await aggregate_hourly(session, hours_back=hours_back)
            d = await aggregate_daily(session, days_back=days_back)
            g = await aggregate_geo(session, days_back=days_back)
        logger.info(f"Analytics rollup: {h} hourly, {d} daily, {g} geo rows")

    async def data_retention_loop():
        """Roll traffic up into analytics, then prune, once per hour."""
        # Wait 5 minutes on startup before first run
        await asyncio.sleep(300)

        # One-time backfill so traffic already sitting in the table is summarised
        # before the first prune ever removes it.
        try:
            await roll_up_analytics(hours_back=72, days_back=90)
        except Exception as e:
            logger.error(f"Initial analytics backfill failed: {e}")

        while True:
            try:
                # Summarise first — anything pruned below is gone for good.
                await roll_up_analytics()
            except asyncio.CancelledError:
                logger.info("Data retention task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in analytics rollup: {e}")
            try:
                summary = await run_retention_cleanup()
                total_deleted = sum(v.get("deleted", 0) for v in summary.values() if isinstance(v, dict))
                if total_deleted > 0:
                    logger.info(f"Data retention cleanup: removed {total_deleted} total rows")
                else:
                    logger.debug("Data retention cleanup: nothing to prune")
            except asyncio.CancelledError:
                logger.info("Data retention task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in data retention cleanup: {e}")
            # Run every hour
            await asyncio.sleep(3600)

    retention_task = asyncio.create_task(data_retention_loop())
    logger.info("Started data retention cleanup task")

    # Scheduled report emails — per-host traffic reports on a daily/weekly/monthly
    # cadence. Checked hourly; each schedule tracks its own last_sent_at, so a
    # restart or a missed tick doesn't skip a report.
    from app.services.report_scheduler import run_due_schedules

    async def report_schedule_loop():
        # Let the app settle before the first check; reports are never urgent.
        await asyncio.sleep(180)
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    sent = await run_due_schedules(session)
                if sent:
                    logger.info("Scheduled reports: sent %d", sent)
            except asyncio.CancelledError:
                logger.info("Report schedule task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in report scheduler: {e}")
            await asyncio.sleep(3600)

    report_task = asyncio.create_task(report_schedule_loop())
    logger.info("Started scheduled report task")

    # Backup watchdog — a backup loop that dies is otherwise invisible: the
    # per-run failure alert only fires if a run actually happens. This notices
    # the absence of runs, which is how the August purge became unrecoverable.
    from app.models.backup import Backup

    async def backup_watchdog_loop():
        await asyncio.sleep(600)
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    from sqlalchemy import select as _select, func as _func

                    last = (await session.execute(
                        _select(_func.max(Backup.created_at)).where(Backup.status == "completed")
                    )).scalar()

                    now = datetime.now(timezone.utc)
                    if last is not None:
                        if last.tzinfo is None:
                            last = last.replace(tzinfo=timezone.utc)
                        age_hours = (now - last).total_seconds() / 3600
                    else:
                        age_hours = None

                    # 26h rather than 24h so a daily backup running slightly late
                    # doesn't cry wolf every morning.
                    if age_hours is None or age_hours > 26:
                        from app.services.alert_service import dispatch_alert

                        detail = (
                            "No successful backup has ever completed."
                            if age_hours is None
                            else f"The last successful backup was {age_hours:.0f} hours ago."
                        )
                        await dispatch_alert(
                            db=session,
                            alert_type="backup_stale",
                            severity="critical",
                            title="Backups Have Stopped",
                            message=f"{detail} The scheduled backup may have stopped running.",
                            data={"last_successful_backup_hours_ago": round(age_hours, 1) if age_hours else None},
                        )
                        logger.error("Backup watchdog: %s", detail)
            except asyncio.CancelledError:
                logger.info("Backup watchdog cancelled")
                break
            except Exception as e:
                logger.error(f"Error in backup watchdog: {e}")
            # Once every 6 hours is enough to catch a stalled backup loop.
            await asyncio.sleep(21600)

    backup_watchdog_task = asyncio.create_task(backup_watchdog_loop())
    logger.info("Started backup watchdog task")

    # Certificate auto-renewal — checks for Let's Encrypt certs nearing expiry
    # and renews + deploys (writes cert files, regenerates nginx configs,
    # reloads nginx) them automatically. Previously renewal only happened if
    # someone clicked "Renew" in the UI, which is why certs were quietly
    # expiring despite "auto renew" being on.
    from app.services.certificate_service import check_expiring_certificates, renew_and_deploy_certificate

    async def certificate_renewal_loop():
        """Periodically renew Let's Encrypt certificates approaching expiry."""
        # Wait 2 minutes on startup before first check
        await asyncio.sleep(120)
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    due = await check_expiring_certificates(
                        session, days_before_expiry=30, send_notifications=True,
                    )

                if due:
                    logger.info(
                        "Certificate auto-renewal: %d certificate(s) due for renewal",
                        len(due),
                    )
                    for cert in due:
                        domain = cert.domain_names[0] if cert.domain_names else cert.id
                        try:
                            success, message = await renew_and_deploy_certificate(cert.id)
                            if success:
                                logger.info("Certificate auto-renewal: renewed %s", domain)
                            else:
                                logger.warning(
                                    "Certificate auto-renewal: failed to renew %s: %s",
                                    domain, message,
                                )
                        except Exception as e:
                            logger.error("Certificate auto-renewal: error renewing %s: %s", domain, e)
                else:
                    logger.debug("Certificate auto-renewal: nothing due")
            except asyncio.CancelledError:
                logger.info("Certificate auto-renewal task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in certificate auto-renewal: {e}")
            # Re-check every 12 hours
            await asyncio.sleep(43200)

    certificate_renewal_task = asyncio.create_task(certificate_renewal_loop())
    logger.info("Started certificate auto-renewal task")

    yield

    # Cancel background tasks
    metrics_task.cancel()
    backup_task.cancel()
    geoip_task.cancel()
    update_check_task.cancel()
    enrichment_backfill_task.cancel()
    abuseipdb_blacklist_task.cancel()
    abuseipdb_report_task.cancel()
    retention_task.cancel()
    certificate_renewal_task.cancel()
    health_task.cancel()
    trusted_proxy_task.cancel()
    report_task.cancel()
    backup_watchdog_task.cancel()
    for _task in (report_task, backup_watchdog_task):
        try:
            await _task
        except asyncio.CancelledError:
            pass
    try:
        await trusted_proxy_task
    except asyncio.CancelledError:
        pass
    try:
        await health_task
    except asyncio.CancelledError:
        pass
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
    try:
        await abuseipdb_blacklist_task
    except asyncio.CancelledError:
        pass
    try:
        await abuseipdb_report_task
    except asyncio.CancelledError:
        pass
    try:
        await retention_task
    except asyncio.CancelledError:
        pass
    try:
        await certificate_renewal_task
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
    # Pagination totals travel in this header; without exposing it the browser
    # cannot read it on a genuinely cross-origin request.
    expose_headers=["X-Total-Count"],
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

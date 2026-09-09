# 02 — No log rotation → disk pressure → DB vacuum failures → slow stats

**Severity:** Critical
**Status:** **Partial** (2026-09-09) — logrotate shipped; prune schedule, vacuum-failure surfacing and low-disk guard still open. See [README](README.md#partial).
**Answers:** "statistics taking too long to load"

## TL;DR

`ghostwire-proxy-nginx`'s access/error logs have grown unbounded (2.3 GB / 155 MB, and
counting) because nothing rotates them. That, combined with ~50-120 GB of reclaimable Docker
build cache/images, has repeatedly driven the host disk to full. When the disk fills,
Postgres's nightly retention job can't run its `VACUUM ANALYZE` on `traffic_logs` — the table
the entire analytics dashboard queries — so it stays bloated and its query-planner statistics
go stale. That's the most likely explanation for continued dashboard slowness even though the
query code itself has already been optimized several times (see git log:
`8ad31ad`, `069cf40`, `1f81092`, `b83e2f5`, `92150cd`).

## Evidence

```
$ docker exec ghostwire-proxy-nginx sh -c 'ls -la /var/log/nginx/'
-rw-r--r-- 1 root root 2268799669 Aug 16 01:30 access.log   # 2.27 GB
-rw-r--r-- 1 root root  155194616 Aug 16 01:30 error.log    # 155 MB

$ docker exec ghostwire-proxy-nginx sh -c 'cat /etc/logrotate.d/*'
# only acpid.log has a logrotate stanza — nothing for /var/log/nginx/*
```

```
$ df -h /
/dev/loop4  327G  264G  51G  85% /

$ docker system df
Images          88.04GB   50.43GB reclaimable
Build Cache    121.9GB   120.3GB reclaimable
```

```
$ grep WARNING <api log>
app.services.retention_service - WARNING - Retention: VACUUM ANALYZE failed (non-fatal):
  (sqlalchemy.dialects.postgresql.asyncpg.Error) <class 'asyncpg.exceptions.DiskFullError'>:
  could not resize shared memory segment "/PostgreSQL.xxxxxxxxx" to 67145536 bytes:
  No space left on device
```
This exact warning repeats well over 100 times across the retained log window — i.e. the
nightly retention cleanup has been hitting disk-full and silently giving up on `VACUUM
ANALYZE traffic_logs` / `threat_events` / `audit_logs` / `system_metrics` on a recurring
basis (`backend/app/services/retention_service.py:102-116`).

## Root cause

1. **Nginx logs are never rotated.** The Alpine/OpenResty base image ships a logrotate config
   for `acpid.log` but nothing for `/var/log/nginx/*`, and `docker-compose.yml` doesn't mount
   an external logrotate or cap the container's log files another way (e.g. `access_log off`
   for high-volume paths, or piping through `logrotate`/an outer log driver). Every request
   through the proxy — including the ~360,000 `upstream timed out` entries from unrelated
   backend containers being down (see [04](04-rule-reload-resilience-and-visibility.md)) —
   appends to these two files forever.
2. **Docker build cache/images are never pruned.** 121 GB of build cache and 50 GB of
   reclaimable images sit on the same filesystem Postgres's data volume lives on
   (`docker exec ghostwire-proxy-postgres df -h` reports the *same* `/dev/loop4` device as the
   host), so anything that fills disk on the host starves Postgres too.
3. **`retention_service.run_retention_cleanup()` treats `VACUUM ANALYZE` failure as
   non-fatal** (`retention_service.py:114-116`, `except ... logger.warning(...)`) — a
   reasonable choice so a vacuum hiccup doesn't crash the whole cleanup job, but it means the
   failure is invisible unless someone goes looking in the container logs, exactly as
   happened here. There's no corresponding "vacuum health" indicator anywhere in the admin UI
   (Settings/System page).
4. **Effect on `traffic_logs` specifically:** this table is the one every analytics/dashboard
   query in `backend/app/api/routes/analytics.py` and `traffic.py` groups/counts/filters
   against. Repeated failed vacuums means dead tuples from the 30-day retention deletes
   (`retention_service.py:39` `_batch_delete`) are never reclaimed and `pg_stat_user_tables`
   statistics go stale, which degrades index selectivity estimates and can flip the planner
   from an index scan to a sequential scan on a table that's had months of traffic logged to
   it. This would present exactly as "queries used to be fast, now they're slow again" even
   though the query shapes haven't changed — matching the pattern of the existing perf commits
   not being a lasting fix.

## Impact

- Disk-full is a shared-fate failure: it doesn't just slow dashboards, it can (and did) block
  Postgres from doing routine maintenance, and at 85% used with the two culprits above
  accounting for the bulk of it, the system is one bad day away from repeating the same
  disk-full event.
- The 2.3 GB error log makes `grep`/`docker logs` against it slow and awkward for anyone
  troubleshooting live — a operational tax on top of the disk-space problem.

## Recommended fix

1. **Rotate nginx logs.** Simplest: add a `logrotate` config + cron (or `run-parts` entry) in
   the `proxy` image for `/var/log/nginx/access.log` and `/var/log/nginx/error.log` (e.g.
   daily, compress, keep 7, `copytruncate` since OpenResty doesn't need a `USR1`-based reopen
   if using `copytruncate`). Alternatively/additionally, reduce error-log volume by not
   logging expected proxy-target-down noise at `error` level (see
   [04](04-rule-reload-resilience-and-visibility.md) — a lot of this is backend services being
   down, which is not an nginx-proxy problem to log at `error`).
2. **Add a scheduled `docker system prune`** (or at minimum `docker builder prune
   --filter until=168h`) on the host, or reduce build-cache retention in CI so it doesn't
   accumulate 120 GB locally.
3. **Surface vacuum failures in the UI**, not just a log warning — e.g. a banner/health item
   on the System page when the last successful `VACUUM ANALYZE traffic_logs` is older than,
   say, 48h, sourced from `pg_stat_user_tables.last_autovacuum`/`last_vacuum` (already queried
   in spirit by `retention_service.get_table_sizes()` — extend it).
4. Consider a low disk-space guard: if free disk drops below a threshold, proactively disable
   verbose access logging or alert, rather than finding out via a Postgres `DiskFullError`.

# Enhancement Backlog — Ghostwire Proxy

Generated 2026-08-16 from a live review of the running container fleet: `docker logs` on
`ghostwire-proxy-api`, `ghostwire-proxy-nginx`, `ghostwire-proxy-certbot`; the nginx
`access.log`/`error.log` inside the container; the Let's Encrypt cert store on disk vs.
the certs nginx is actually serving; and the relevant backend/Lua source.

Every item below is backed by direct evidence (log lines, file paths, line numbers), not
speculation. Ordered by severity/impact.

| # | Title | Severity | Status | Explains |
|---|-------|----------|--------|----------|
| [01](01-certificate-renewal-not-deployed.md) | Renewed certs never reach nginx | **Critical** | **Done** | "certs say expired" |
| [02](02-disk-pressure-and-log-rotation.md) | No log rotation → disk pressure → DB vacuum failures | **Critical** | Partial | "stats slow to load" |
| [03](03-traffic-logger-connection-pool-corruption.md) | Traffic logger corrupts its own HTTP keepalive pool | **High** | **Done** | "can't see web traffic" |
| [04](04-rule-reload-resilience-and-visibility.md) | Silent WAF/rate-limit/GeoIP rule reload failures | **Medium** | Not started | "can't tell why things don't work" |
| [05](05-global-ip-blocking-not-per-host.md) | Automatic IP blocking is global, not per-host | **Medium** | Not started | "rules are global not per-host" |
| [06](06-location-dialog-missing-timeout-and-advanced-fields.md) | Location dialog has no timeout/advanced-config fields | **High** | **Done** | "ghostwire proxy timing out" / "UI not wired up properly" |
| [07](07-analytics-rollups-never-scheduled.md) | Analytics rollups never scheduled — retention destroys history | **High** | **Done** | "analytics slow" / "can't compare periods" |
| [08](08-no-visitor-identity-in-traffic-logs.md) | `auth_user` never written — no visitor identity | Medium | Partial | "track a unique user, not just the IP" |
| [09](09-analytics-has-no-per-host-drilldown.md) | Analytics has no per-host drill-down | Medium | **Done** | "click a host and see its traffic / popular pages" |
| [10](10-deploys-do-not-gate-on-ci.md) | Deploys don't gate on CI; `COPY . .` ships the working tree | Medium | Partial | "the UI broke right after a deploy" |
| [11](11-backup-failure-is-silent.md) | A failing scheduled backup is silent | Medium | **Done** | "how would we know if backups stopped?" |
| [12](12-test-suite-could-drop-the-production-database.md) | Test suite could drop the production database | **Critical** | Partial | "how did the database get purged?" |
| [13](13-fresh-install-cannot-run-migrations.md) | A fresh install cannot run its own migrations | **High** | Not started | "would a new deployment even come up?" |

## Quick summary

- **Certificates**: the standalone `ghostwire-proxy-certbot` container *does* renew Let's
  Encrypt certificates successfully in the background every 12h, but nothing ever copies
  the renewed PEM files into `data/certificates/*.crt` (what nginx actually serves) or
  reloads nginx. Result: 16 of 19 configured hosts are running certs that expired days-to-weeks
  ago, or are about to, while the real Let's Encrypt certs sitting one directory over are
  already renewed through October. See [01](01-certificate-renewal-not-deployed.md).
- **Disk**: the nginx container's `access.log`/`error.log` have never been rotated and are
  2.3 GB / 155 MB respectively. The host filesystem is at 85% (with 121 GB of reclaimable
  Docker build cache on top). This disk pressure previously caused Postgres to hit
  `DiskFullError` during the nightly retention job's `VACUUM ANALYZE`, which fails silently
  (logged as a non-fatal warning) — leaving `traffic_logs` bloated and un-analyzed, which is
  the most likely reason dashboard/stats queries are slow even after several rounds of query
  optimization already in the git history. See [02](02-disk-pressure-and-log-rotation.md).
- **Traffic view gaps**: `traffic_logger.lua` uses the low-level `resty.http` `request()` API
  and returns the connection to the keepalive pool without draining the response body. The
  next request pulled from that pooled connection reads the leftover body bytes as part of
  its status line, so logging silently fails (~5,500 occurrences in the current log). See
  [03](03-traffic-logger-connection-pool-corruption.md).
- **"Why isn't it working" visibility**: background rule reloads (WAF, blocked IPs, rate
  limits, GeoIP, trusted IPs, honeypot traps) failed ~29,000 times in the current log window,
  mostly transient DNS blips to `ghostwire-proxy-api`, but none of it is surfaced anywhere in
  the admin UI — an admin has no way to know enforcement briefly went stale. See
  [04](04-rule-reload-resilience-and-visibility.md).
- **Per-host rules**: WAF rules, rate limits and GeoIP rules *do* already support per-host
  scoping end-to-end (DB column, API, UI). The gap is automatic IP blocking/blocklisting
  (`ThreatActor`, driven by threat thresholds) — it has no host concept at all, so an IP that
  trips a threshold on one site gets blocked on *every* proxied host. See
  [05](05-global-ip-blocking-not-per-host.md).
- **Location tuning is invisible in the UI**: the `ProxyLocation` model, API, and nginx
  generator all correctly support per-location timeouts and a per-location advanced-config
  block, but the Add/Edit Location dialog never renders inputs for any of it — the only
  "Advanced" box on the page belongs to the *host* dialog and renders into the default `/`
  location instead. This directly caused `wingman.err403.com`'s `/api/chat` to keep timing
  out at 60s for weeks — a fix aimed at `/api` had nowhere to go but the wrong field. See
  [06](06-location-dialog-missing-timeout-and-advanced-fields.md).

## Suggested immediate remediation (no code changes)

These can be done today, independent of the code fixes below:

1. `docker exec ghostwire-proxy-nginx sh -c '> /var/log/nginx/access.log; > /var/log/nginx/error.log'`
   to reclaim the ~2.4 GB immediately (or `truncate`, not `rm`, since nginx holds the fd open).
2. `docker builder prune` / `docker image prune -a` to reclaim the 121 GB / 50 GB of
   reclaimable Docker build cache and unused images — this is almost half the used disk.
3. Manually trigger a certificate renewal from the UI for the near-term-expiring hosts (or
   run `process_certificate_renewal` for each) until [01](01-certificate-renewal-not-deployed.md)
   is fixed, so the site doesn't serve expired certs in the meantime.
4. For `wingman.err403.com` specifically: delete the dead nested-`location /api/` snippet
   from the host's Advanced tab, and `PUT` real `proxy_read_timeout`/`proxy_send_timeout`
   (300) + `advanced_config` (`client_max_body_size 25m;\nproxy_buffering off;`) onto its
   `/api` location via the API directly, then regenerate + reload nginx. See
   [06](06-location-dialog-missing-timeout-and-advanced-fields.md).


## Status (2026-09-09)

Verified against the code, not against the previous status note. "Done" means the
recommended fix in that file is present in the tree; "Partial" lists what is still
missing.

### Done

- **01 — Renewed certs never reach nginx.** `certificate_service.py` now deploys the
  renewed PEMs via `write_certificate_files()` + `reload_nginx()` and records real
  expiry dates (`c0325f3`).
- **03 — Traffic-logger keepalive corruption.** `traffic_logger.lua` drains the body
  with `res:read_body()` before `set_keepalive()`, and `close()`s the socket on any
  failure path rather than returning an unknown-state connection to the pool.
- **06 — Location dialog fields.** The Add/Edit Location dialog renders
  `proxy_connect_timeout` / `proxy_send_timeout` / `proxy_read_timeout` and a
  per-location `advanced_config` textarea, and round-trips them through
  `handleEditLocation` / `handleSaveLocation`.
- **07 — Analytics rollups never scheduled.** `main.py` runs a rollup loop calling
  `aggregate_hourly()` / `aggregate_daily()` / `aggregate_geo()`.
- **09 — Per-host analytics drill-down.** The Analytics page has a host selector that
  passes `proxy_host_id` to the dashboard and logs queries, with an "All hosts" reset
  and the host name in the heading. Now superseded in depth by the dedicated per-host
  report at `/dashboard/proxy-hosts/<id>/report`.
- **11 — Silent backup failure.** `notify_backup_completed()` on success and
  `notify_backup_failed()` + a critical `backup_failed` alert on failure, plus a
  watchdog loop in `main.py` that raises `backup_stale` when no successful backup has
  completed in 26 hours — which catches the scheduler dying entirely, not just an
  individual run failing. An offsite copy is still not implemented, and remains the
  one real gap: these backups protect against a logical purge, not loss of the host.

### Partial

- **02 — Log rotation / disk pressure.** Rotation is done: the proxy image installs
  `logrotate`, ships `/etc/logrotate.d/nginx` (daily, `maxsize`, keep 7, `copytruncate`)
  and runs it hourly from cron in `entrypoint.sh`.
  Still open: no scheduled `docker builder prune`; `VACUUM ANALYZE` failures are still
  only a log warning with nothing on the System page; no low-disk guard.
- **08 — Visitor identity.** Authenticated hosts are done: `auth_wall.lua` stashes
  `ngx.ctx.auth_user`, `traffic_logger.lua` sends it, and `internal.py` persists it.
  Bot classification landed too (`client_classifier.classify_bot`, `TrafficLog.is_bot`).
  Still open: the per-host `visitor_tracking_enabled` opt-in for public hosts.
- **10 — Deploys don't gate on CI.** Both `backend/.dockerignore` and
  `frontend/.dockerignore` now exclude host artefacts, so `COPY . .` can no longer ship
  `.env.local` / `.next` / `node_modules` / `.git`.
  Still open: `scripts/upgrade.sh` neither runs nor waits on CI, still builds from the
  working tree rather than `git archive HEAD`, refuses nothing on a dirty tree, stamps no
  commit SHA into the image, and does not verify the deployed UI by its baked
  `routes-manifest.json` rewrite target.
- **12 — Test suite could drop the production database.** The `conftest.py` guard is in
  place: `TEST_DATABASE_URL` only, a hard `RuntimeError` unless the database name ends in
  `_test`, and `DATABASE_URL` overwritten with the test URL.
  Still open: the real Postgres password is still a committed literal at
  `backend/tests/conftest.py:35`. Also note `.github/workflows/ci.yml` still passes
  `DATABASE_URL` to pytest — conftest ignores it, so CI falls back to the hardcoded
  `ghostwire-proxy-postgres` host and cannot reach its own Postgres service container.

### Not started

- **04 — Silent rule-reload failures.** `init.lua` still only `ngx.log(ngx.ERR, ...)` on
  each fetch failure: no per-rule-type `*_synced_at` timestamp in the shared dict, no
  consecutive-failure counter or escalation, no in-tick retry for the DNS blip, and
  nothing surfaced in the admin UI.
- **13 — A fresh install cannot run its own migrations.** `0001` builds the baseline with
  `Base.metadata.create_all()` against the live models, so on an empty database it creates
  columns that later migrations then fail to add (`0004` onwards). Existing deployments are
  unaffected; only new installs and clean-database restores hit it. Migrations 0011 and 0012
  are written with inspector guards so they survive both paths, but the underlying fault
  remains.
- **05 — Global-only automatic IP blocking.** `ThreatActor` still has no `proxy_host_id`
  (and there is no `ThreatActorHostStatus` table), and `waf.lua:is_ip_blocked(client_ip)`
  still takes no host argument, so a threshold tripped on one host still blocks the IP
  everywhere.

### Landed alongside (not in this backlog)

A spoofable-client-IP flaw found while working on 06 — every IP-based control trusted
request headers instead of nginx's validated `remote_addr`, so any visitor could choose
their own source address and, by naming a trusted IP, skip the WAF entirely. Plus
per-host CDN awareness (`cdn_provider`, Cloudflare/Imperva ranges refreshed daily),
upstream health monitoring with host-down/recovered alerts, `notify_under_attack` wiring,
a shared `Modal` for all 21 dialogs, PWA service-worker registration, WAF enforcement
fixes, mobile layout work, and the known-IPs feature.

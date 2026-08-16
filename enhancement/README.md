# Enhancement Backlog — Ghostwire Proxy

Generated 2026-08-16 from a live review of the running container fleet: `docker logs` on
`ghostwire-proxy-api`, `ghostwire-proxy-nginx`, `ghostwire-proxy-certbot`; the nginx
`access.log`/`error.log` inside the container; the Let's Encrypt cert store on disk vs.
the certs nginx is actually serving; and the relevant backend/Lua source.

Every item below is backed by direct evidence (log lines, file paths, line numbers), not
speculation. Ordered by severity/impact.

| # | Title | Severity | Explains |
|---|-------|----------|----------|
| [01](01-certificate-renewal-not-deployed.md) | Renewed certs never reach nginx | **Critical** | "certs say expired" |
| [02](02-disk-pressure-and-log-rotation.md) | No log rotation → disk pressure → DB vacuum failures | **Critical** | "stats slow to load" |
| [03](03-traffic-logger-connection-pool-corruption.md) | Traffic logger corrupts its own HTTP keepalive pool | **High** | "can't see web traffic" |
| [04](04-rule-reload-resilience-and-visibility.md) | Silent WAF/rate-limit/GeoIP rule reload failures | **Medium** | "can't tell why things don't work" |
| [05](05-global-ip-blocking-not-per-host.md) | Automatic IP blocking is global, not per-host | **Medium** | "rules are global not per-host" |

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

## Suggested immediate remediation (no code changes)

These can be done today, independent of the code fixes below:

1. `docker exec ghostwire-proxy-nginx sh -c '> /var/log/nginx/access.log; > /var/log/nginx/error.log'`
   to reclaim the ~2.4 GB immediately (or `truncate`, not `rm`, since nginx holds the fd open).
2. `docker builder prune` / `docker image prune -a` to reclaim the 121 GB / 50 GB of
   reclaimable Docker build cache and unused images — this is almost half the used disk.
3. Manually trigger a certificate renewal from the UI for the near-term-expiring hosts (or
   run `process_certificate_renewal` for each) until [01](01-certificate-renewal-not-deployed.md)
   is fixed, so the site doesn't serve expired certs in the meantime.

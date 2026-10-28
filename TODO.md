# Ghostwire Proxy — TODO

> Last reviewed: March 25, 2026

---

## Critical (broken / incomplete)

- [ ] **LDAP auth provider** — Model & routes exist, but the actual `ldap3` authentication logic is not implemented. LDAP login will not work until this is built.
- [ ] **Alembic migration files** — No migration files exist in `backend/alembic/versions/`. Schema is managed via `create_all()`. Need proper tracked migrations for safe upgrades.

---

## High Priority (planned features)

- [ ] **PDF/CSV report export** — Analytics data is collected but there is no export functionality. Need report generation service and API endpoint.
- [ ] **Slack alert channel** — Alert service supports multi-channel dispatch. Slack webhook connector needs to be implemented.
- [ ] **Telegram alert channel** — Same as Slack — Telegram Bot API connector needed.
- [ ] **Geographic visualizations** — GeoIP data is collected and aggregated. `geo-heatmap` component exists but needs data wiring to analytics API.
- [ ] **Per-host detailed analytics views** — Analytics service aggregates per-host data. Frontend needs dedicated detail pages per proxy host.
- [ ] **Load balancing (multiple upstreams)** — Support multiple upstream servers per proxy host with round-robin / weighted distribution.

---

## Security detection (added 2026-10-28, after the AKG Tech incident)

`www.akgtech.co.nz` (proxied to 192.168.0.109:3458) was exploited through React2Shell (CVE-2025-55182) and stayed compromised from May to October 2026. Every exploit request passed through this proxy, but the WAF couldn't see it: `check_db_rules()` in `proxy/lua/waf.lua` only matches the URI, query string and User-Agent, while the exploit is a POST with a `Next-Action` header and a crafted multipart body. Full report: `Desktop\AKGTech-Security-Incident-Report-2026-10-28.html`.

- [ ] **WAF: inspect headers and bodies.** Add rule targets `header:<name>`, `headers` (all) and `body` (first N KB, configurable, buffered with `ngx.req.read_body()`; skip large uploads and streaming), alongside the current `uri`/`request_data`/`user_agent`. Add a `target` column to `WafRule` rather than inferring it from `category`.
- [ ] **Preset rule set "Framework RCE"**: React2Shell (POST with a `Next-Action` header whose multipart body contains the known gadget patterns, such as `__proto__`/`constructor` chains and `$@`/`$B` references to `child_process`/`execSync`), plus the Next.js middleware bypass (`x-middleware-subrequest`, CVE-2025-29927). Log by default; block per host. Keep presets updatable from a signed feed, so new rules ship without a release.
- [ ] **Per-host "uses Server Actions" flag**: when off, any request carrying `Next-Action` is logged as high severity, or blocked.
- [ ] **Version exposure check**: read each host's Next.js/React version from its served JS (`/_next/static/chunks`, `version:"x.y.z"`) during the health check. Show it on the host page, flag vulnerable versions, and send them to Ghostwire Secure for CVE/KEV matching. The proxy already knows every site, so it's the natural inventory.
- [ ] **Outbound indicator block list**: share IP and domain indicators with Ghostwire Secure, and block or alert on proxy traffic to and from them.
- [ ] **Threat events to Ghostwire Secure**: push `ThreatEvent`s and threshold breaches through the API (or a Redis stream) so Secure can correlate across hosts. Include client IP, host, method, path, matched rule and a body excerpt.
- [ ] **Request log search for incidents**: filter by host + method + date range + header present (for example "POST to www.akgtech.co.nz with Next-Action, 20–21 May"). Keep raw request logs for at least 12 months, with a body excerpt for flagged requests. Needed now to find the AKG Tech attacker's source IP.
- [ ] **Watch Ghostwire Secure**: health-check `ghostwire.secure.err403.com` and alert when it's down (it was down 7 days, unnoticed).
- [ ] **Lock down the admin UI**: put `ghostwire.proxy.err403.com` behind an access list or the auth wall by default.

---

## Medium Priority (enhancements)

- [ ] **ModSecurity / OWASP CRS** — Optional integration alongside existing Lua WAF rules for deeper detection coverage.
- [ ] **Ghostwire user sync** — Optional cross-app authentication. Share users between Ghostwire and Ghostwire Proxy.
- [ ] **Custom WAF rule editor in UI** — WAF rules are managed via database. Need a visual editor in the admin dashboard.
- [ ] **API key authentication** — Programmatic access to the API without JWT. Useful for automation and CI/CD.
- [ ] **Uptime monitoring** — Health check pings for proxied services with status tracking and alerting.
- [ ] **Dark/light theme toggle** — Currently dark theme only. Add user-selectable theme preference.
- [ ] **HA / clustering support** — Future scaling: multi-node deployment with shared state.
- [ ] **PWA configuration** — Manifest and service worker for installable mobile app.

---

## Housekeeping

- [ ] **README: help/troubleshooting section** — Common issues, FAQ, debugging tips.
- [ ] **README: best practices section** — Security hardening, production deployment, backup strategy.

---

## Recently Completed

- [x] **Test coverage** — Expanded from 1 test file to 21 test files covering services, routes, models, and security.
- [x] **Update PLAN.md phase checklist** — All 12 phases updated to reflect current implementation state.
- [x] **In-app documentation** — 28 docs pages with server-side markdown rendering, callouts, steps, and image serving.
- [x] **Docker hardening** — Postgres/Redis containers configured with named volumes and proper networking.

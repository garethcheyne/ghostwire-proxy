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

# Ghostwire Proxy — TODO

> Last reviewed: March 22, 2026

---

## Critical (broken / incomplete)

- [ ] **LDAP auth provider** — Model & routes exist, but the actual `ldap3` authentication logic is not implemented. LDAP login will not work until this is built.
- [ ] **Alembic migration files** — No migration files exist in `backend/alembic/versions/`. Schema is managed via `create_all()`. Need proper tracked migrations for safe upgrades.
- [ ] **Test coverage** — Only 1 test file (`test_firewall_service.py`). No tests for: API routes, threat service, analytics, certificates, auth providers, WAF, or integration tests.

---

## High Priority (planned features)

- [ ] **PDF/CSV report export** — Analytics data is collected but there is no export functionality. Need report generation service and API endpoint.
- [ ] **Slack alert channel** — Alert service supports multi-channel dispatch. Slack webhook connector needs to be implemented.
- [ ] **Telegram alert channel** — Same as Slack — Telegram Bot API connector needed.
- [ ] **Geographic visualizations** — GeoIP data is collected and aggregated. Frontend needs map components to visualize request origins and attack maps.
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

---

## Housekeeping

- [ ] **README: help/troubleshooting section** — Common issues, FAQ, debugging tips.
- [ ] **README: best practices section** — Security hardening, production deployment, backup strategy.
- [ ] **Docker hardening commit + push** — Postgres/Redis container hardening changes need to be committed and pushed.
- [ ] **Update PLAN.md phase checklist** — Mark completed phases, update remaining items to reflect current state.

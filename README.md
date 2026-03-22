<p align="center">
  <img src="frontend/public/logo-teal.png" alt="Ghostwire Proxy" width="120" />
</p>

<h1 align="center">Ghostwire Proxy</h1>

<p align="center">
  A modern, self-hosted reverse proxy manager with built-in security — an alternative to Nginx Proxy Manager.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/OpenResty-Nginx%20%2B%20Lua-green" alt="OpenResty" />
  <img src="https://img.shields.io/badge/Frontend-Next.js%2016-blue" alt="Next.js" />
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Database-PostgreSQL-336791" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License" />
</p>

---

## What is Ghostwire Proxy?

Ghostwire Proxy is a full-featured reverse proxy management platform that combines the simplicity of Nginx Proxy Manager with enterprise-grade security features. It runs as a Docker stack and provides a clean web UI for managing proxy hosts, SSL certificates, authentication walls, firewall integrations, and more.

It is a standalone subproject within the [Ghostwire](https://github.com/garethcheyne/ghostwire) ecosystem — fully independent, but designed to integrate when needed.

---

## Features

### Reverse Proxy Management
- Create and manage proxy hosts with a clean dashboard
- Forward HTTP/HTTPS traffic to upstream services
- WebSocket support, HTTP/2, and HSTS
- Custom nginx advanced configuration per host
- Live config generation and OpenResty hot-reload (zero downtime)

### SSL / TLS Certificates
- **Let's Encrypt** automatic issuance and renewal via Certbot
- Manual certificate upload (custom CA, self-signed)
- DNS challenge support via Cloudflare
- Per-host SSL configuration (force HTTPS, HTTP/2)

### Authentication Wall
- Protect any proxied service with a login gate
- **Local auth** — username/password per auth wall
- **OAuth2 / SSO** — Google, GitHub, Azure AD, generic OIDC
- **LDAP** — bind to Active Directory or OpenLDAP
- **TOTP** — time-based one-time password (2FA)
- Customizable auth portal UI (Vite + React)

### Web Application Firewall (WAF)
- Lua-based request inspection at the proxy layer
- Detection rules for SQL injection, XSS, path traversal, RCE, and scanner fingerprints
- Configurable actions per rule: log, block, or blocklist
- Per-host WAF enable/disable

### Threat Response & Firewall Integration
- Tiered response system: warn → temp block → permanent block → firewall ban
- IP reputation tracking with cumulative threat scores
- Push IPs to external firewalls:
  - **MikroTik RouterOS** (address lists)
  - **UniFi** (firewall rules)
  - **pfSense** / **OPNsense** (aliases)

### GeoIP Blocking
- Country-level allow/deny lists per proxy host
- GeoIP database support (MaxMind GeoLite2)

### Rate Limiting
- Configurable per-host rate limits
- In-memory tracking via Lua shared dictionaries

### Access Lists
- IP whitelist / blacklist groups
- Assign access lists to proxy hosts

### Traffic & Analytics
- Per-request logging (optional per host)
- Dashboard with request counts, bandwidth, response times
- Traffic over time, status code breakdown
- Per-host analytics

### Alerts & Notifications
- Real-time alerts for security events
- Configurable alert channels (webhook, email)
- Alert severity levels and filtering

### System & Administration
- Multi-user admin with JWT authentication
- Audit logging for all admin actions
- Backup and restore
- System health monitoring
- DNS provider management (Cloudflare integration)

### Mobile Ready
- PWA support — installable on mobile devices
- Responsive, mobile-first dark UI
- Built with Tailwind CSS and shadcn/ui

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Proxy Engine** | OpenResty (Nginx + Lua) on Alpine |
| **Frontend** | Next.js 16+, TypeScript, Tailwind CSS, shadcn/ui |
| **Backend API** | Python 3.12, FastAPI, SQLAlchemy |
| **Database** | PostgreSQL 16 (via asyncpg) |
| **Auth** | JWT, OAuth2, LDAP, TOTP |
| **Containers** | Docker Compose |

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- A domain pointed to your server (for SSL)

### 1. Clone

```bash
git clone https://github.com/garethcheyne/ghostwire-proxy.git
cd ghostwire-proxy
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your settings (database password, domain, secrets)
```

### 3. Run

```bash
docker compose up -d
```

### 4. Access

| Service | URL |
|---------|-----|
| **Admin UI** | `http://your-server:88` |
| **API** | `http://your-server:8089` |
| **Proxy HTTP** | Port `80` |
| **Proxy HTTPS** | Port `443` |

On first launch, you'll be guided through initial setup to create your admin account.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Internet                          │
│                  :80 / :443                          │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   OpenResty     │   Lua: WAF, Auth Wall,
              │   (Nginx+Lua)   │   Rate Limit, GeoIP,
              │                 │   Access Control, Logging
              └───────┬─┬───────┘
                      │ │
          ┌───────────┘ └───────────┐
          ▼                         ▼
  ┌──────────────┐         ┌──────────────┐
  │  Upstream A  │         │  Upstream B  │   Your services
  └──────────────┘         └──────────────┘

              ┌─────────────────┐
              │  Admin UI (:88) │   Next.js
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  API (:8089)    │   FastAPI
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  PostgreSQL     │
              └─────────────────┘
```

---

## Project Status

Ghostwire Proxy is under active development. Here's what's done and what's in progress:

### ✅ Complete
- Core proxy host management (CRUD, config generation, hot-reload)
- SSL certificate management (Let's Encrypt + manual upload)
- Authentication wall (local, OAuth2, LDAP, TOTP)
- Auth portal UI (Vite + React)
- WAF with Lua-based detection rules
- Firewall integration (RouterOS, UniFi, pfSense, OPNsense)
- GeoIP blocking
- Rate limiting
- Access lists (IP allow/deny)
- Traffic logging and analytics
- Alert system
- User management with JWT auth
- Audit logging
- Backup and restore
- System health monitoring
- DNS / Cloudflare integration
- Admin dashboard
- Database migration from SQLite to PostgreSQL
- Docker Compose deployment

### 🚧 In Progress
- PDF/CSV report export
- Web Push notifications
- Geographic visualizations (request map, attack origin map)
- Per-host detailed analytics views
- ModSecurity / OWASP CRS integration (optional alongside Lua rules)
- Ghostwire user sync (optional cross-app auth)
- Slack / Telegram alert channels
- Load balancing with multiple upstream servers

### 📋 Planned
- HA / clustering support
- API key authentication for programmatic access
- Custom WAF rule editor in the UI
- Uptime monitoring with health checks
- Dark/light theme toggle

---

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Full Stack (Docker)

```bash
docker compose up --build
```

---

## License

MIT

---

<p align="center">
  Built by <a href="https://github.com/garethcheyne">Gareth Cheyne</a>
</p>

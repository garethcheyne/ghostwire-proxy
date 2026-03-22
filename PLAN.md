# Ghostwire Proxy - Implementation Plan

## Overview

A Nginx Proxy Manager alternative built as a sibling application to Ghostwire. Located in `ghostwire-proxy/` subdirectory for complete separation.

**Key Features:**
- OpenResty (nginx + Lua) reverse proxy engine
- Traffic inspection and logging (optional per-site)
- Request modification capabilities
- Built-in Auth Wall (Username/Password, OAuth2/SSO, LDAP)
- Let's Encrypt + manual SSL certificates
- Next.js admin UI (same design as Ghostwire)
- SQLite database (self-contained)
- Optional Ghostwire user sync

**Security Features (WAF + Threat Response):**
- Hybrid attack detection (Lua + optional ModSecurity/OWASP CRS)
- Configurable per-rule response (log, block, blocklist)
- Tiered response system (warn → temp block → perm block → firewall ban)
- Firewall integration (RouterOS, UniFi, pfSense, OPNsense)
- Geographic blocking (GeoIP via MaxMind or IP2Location)
- Rate limiting (in-memory, configurable per-host)

**Mobile & Alerts:**
- PWA support (installable on mobile)
- Web Push notifications for real-time security alerts
- Responsive mobile-first UI
- Configurable alert channels (push, email, webhook)

**Reporting & Analytics:**
- Dashboard overview (requests, blocks, bandwidth, uptime)
- Security dashboard (attacks, threat actors, severity breakdown)
- Traffic analytics (requests over time, response times, status codes)
- Geographic visualizations (request map, attack origins)
- Per-host analytics (traffic, errors, latency)
- Exportable reports (PDF, CSV)
- Searchable logs (requests, threats, auth, audit)

**Branding:**
- Same logo as Ghostwire (copy from `../frontend/public/`)
- Same dark theme and color scheme (slate, cyan, purple)

**Ports:**
- 80/443: Proxy traffic
- 88: Admin UI
- 8089: Internal API

---

## Directory Structure

```
ghostwire/
├── ... (existing ghostwire files)
└── ghostwire-proxy/                    # Completely separate
    ├── docker-compose.yml
    ├── docker-compose.override.yml
    ├── .env.example
    ├── CLAUDE.md
    ├── README.md
    │
    ├── frontend/                       # Next.js Admin UI (Port 88)
    │   ├── Dockerfile
    │   ├── package.json
    │   ├── next.config.ts
    │   ├── tailwind.config.ts
    │   ├── components.json
    │   └── src/
    │       ├── app/
    │       │   ├── (auth)/auth/login/page.tsx
    │       │   ├── (dashboard)/dashboard/
    │       │   │   ├── page.tsx                 # Dashboard
    │       │   │   ├── proxy-hosts/             # Proxy management
    │       │   │   ├── certificates/            # SSL certs
    │       │   │   ├── access-lists/            # IP whitelist/blacklist
    │       │   │   ├── auth-wall/               # Auth configuration
    │       │   │   ├── traffic/                 # Traffic logs
    │       │   │   └── settings/                # Admin settings
    │       │   └── api/
    │       ├── components/
    │       │   ├── ui/                          # shadcn/ui
    │       │   └── layout/
    │       ├── lib/
    │       └── stores/
    │
    ├── backend/                        # FastAPI Backend
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       ├── main.py
    │       ├── core/
    │       │   ├── config.py
    │       │   ├── database.py          # SQLite with aiosqlite
    │       │   ├── security.py
    │       │   └── openresty.py         # Config generator
    │       ├── api/routes/
    │       │   ├── auth.py
    │       │   ├── proxy_hosts.py
    │       │   ├── certificates.py
    │       │   ├── access_lists.py
    │       │   ├── auth_wall.py
    │       │   ├── traffic.py
    │       │   └── settings.py
    │       ├── models/
    │       ├── schemas/
    │       └── services/
    │           ├── certificate_service.py    # Let's Encrypt ACME
    │           ├── openresty_service.py      # Config gen & reload
    │           ├── ldap_service.py
    │           └── oauth_service.py
    │
    ├── proxy/                          # OpenResty Engine
    │   ├── Dockerfile
    │   ├── nginx.conf
    │   ├── conf.d/
    │   └── lua/
    │       ├── auth_wall.lua
    │       ├── access_control.lua
    │       └── traffic_logger.lua
    │
    └── data/                           # Persistent data (volumes)
        ├── sqlite/
        ├── certificates/
        └── nginx-configs/
```

---

## Database Schema (SQLite)

### Core Tables

| Table | Purpose |
|-------|---------|
| `users` | Admin users for proxy management UI |
| `proxy_hosts` | Proxy host configurations (domains, upstream, SSL) |
| `upstream_servers` | Load balancing targets per proxy host |
| `certificates` | SSL certificates (manual + Let's Encrypt) |
| `access_lists` | IP whitelist/blacklist groups |
| `access_list_entries` | Individual allow/deny rules |
| `auth_walls` | Authentication configurations |
| `auth_providers` | OAuth/SSO provider configs |
| `ldap_configs` | LDAP server configurations |
| `local_auth_users` | Basic auth users per auth wall |
| `traffic_logs` | Request/response logs |
| `audit_logs` | Admin action audit trail |
| `settings` | Global settings key-value |
| `ghostwire_sync` | Sync configuration with main Ghostwire |
| `waf_rules` | WAF detection rules (SQLi, XSS, etc.) |
| `waf_rule_sets` | Rule set groupings (OWASP CRS, custom) |
| `threat_events` | Detected attack events log |
| `threat_actors` | IP reputation tracking (attack count, score) |
| `threat_responses` | Response actions taken per IP |
| `firewall_connectors` | Firewall integrations (RouterOS, UniFi, pfSense, OPNsense) |
| `rate_limit_rules` | Rate limiting configurations per host |
| `geoip_rules` | Geographic blocking rules (country allow/deny) |
| `geoip_settings` | GeoIP database configuration (MaxMind/IP2Location) |
| `firewall_blocklist` | IPs pushed to external firewalls |

### Key Table Schemas

```sql
-- Proxy hosts (virtual servers)
CREATE TABLE proxy_hosts (
    id TEXT PRIMARY KEY,
    domain_names TEXT NOT NULL,           -- JSON array of domains
    forward_scheme TEXT DEFAULT 'http',
    forward_host TEXT NOT NULL,
    forward_port INTEGER NOT NULL,
    ssl_enabled INTEGER DEFAULT 0,
    ssl_force INTEGER DEFAULT 0,
    certificate_id TEXT,
    http2_support INTEGER DEFAULT 1,
    hsts_enabled INTEGER DEFAULT 0,
    websockets_support INTEGER DEFAULT 1,
    block_exploits INTEGER DEFAULT 1,
    access_list_id TEXT,
    auth_wall_id TEXT,
    advanced_config TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- SSL Certificates
CREATE TABLE certificates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain_names TEXT NOT NULL,
    certificate TEXT,
    certificate_key TEXT,                  -- Encrypted
    is_letsencrypt INTEGER DEFAULT 0,
    letsencrypt_email TEXT,
    expires_at TEXT,
    auto_renew INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Auth Wall
CREATE TABLE auth_walls (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    auth_type TEXT NOT NULL,              -- 'basic', 'oauth', 'ldap', 'multi'
    session_timeout INTEGER DEFAULT 3600,
    created_at TEXT DEFAULT (datetime('now'))
);

-- OAuth/SSO Providers
CREATE TABLE auth_providers (
    id TEXT PRIMARY KEY,
    auth_wall_id TEXT,
    name TEXT NOT NULL,
    provider_type TEXT NOT NULL,          -- 'google', 'github', 'azure_ad', 'oidc'
    client_id TEXT,
    client_secret TEXT,                   -- Encrypted
    authorization_url TEXT,
    token_url TEXT,
    userinfo_url TEXT,
    scopes TEXT,
    enabled INTEGER DEFAULT 1
);

-- LDAP Configuration
CREATE TABLE ldap_configs (
    id TEXT PRIMARY KEY,
    auth_wall_id TEXT,
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER DEFAULT 389,
    use_ssl INTEGER DEFAULT 0,
    bind_dn TEXT,
    bind_password TEXT,                   -- Encrypted
    base_dn TEXT NOT NULL,
    user_filter TEXT DEFAULT '(uid=%s)',
    enabled INTEGER DEFAULT 1
);

-- WAF Rules
CREATE TABLE waf_rules (
    id TEXT PRIMARY KEY,
    rule_set_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,               -- 'sqli', 'xss', 'path_traversal', 'rce', 'scanner'
    pattern TEXT NOT NULL,                -- Regex pattern
    severity TEXT DEFAULT 'medium',       -- 'low', 'medium', 'high', 'critical'
    action TEXT DEFAULT 'log',            -- 'log', 'block', 'blocklist'
    enabled INTEGER DEFAULT 1,
    is_lua INTEGER DEFAULT 1,             -- 1=Lua rule, 0=ModSecurity
    created_at TEXT DEFAULT (datetime('now'))
);

-- Threat Events (attack log)
CREATE TABLE threat_events (
    id TEXT PRIMARY KEY,
    proxy_host_id TEXT,
    client_ip TEXT NOT NULL,
    rule_id TEXT,
    rule_name TEXT,
    category TEXT,
    severity TEXT,
    action_taken TEXT,                    -- 'logged', 'blocked', 'blocklisted'
    request_method TEXT,
    request_uri TEXT,
    request_headers TEXT,
    matched_payload TEXT,                 -- What triggered the rule
    timestamp TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_threat_events_ip ON threat_events(client_ip);
CREATE INDEX idx_threat_events_timestamp ON threat_events(timestamp);

-- Threat Actors (IP reputation)
CREATE TABLE threat_actors (
    id TEXT PRIMARY KEY,
    ip_address TEXT UNIQUE NOT NULL,
    total_events INTEGER DEFAULT 0,
    threat_score INTEGER DEFAULT 0,       -- Cumulative score
    first_seen TEXT,
    last_seen TEXT,
    current_status TEXT DEFAULT 'monitored', -- 'monitored', 'warned', 'temp_blocked', 'perm_blocked', 'firewall_banned'
    temp_block_until TEXT,
    perm_blocked_at TEXT,
    firewall_banned_at TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Threat Response Thresholds
CREATE TABLE threat_thresholds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    events_count INTEGER,                 -- Trigger after X events
    time_window_minutes INTEGER,          -- Within X minutes
    threat_score INTEGER,                 -- Or when score reaches X
    response_action TEXT NOT NULL,        -- 'warn', 'temp_block', 'perm_block', 'firewall_ban'
    temp_block_duration_minutes INTEGER,
    enabled INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 0            -- Higher = checked first
);

-- Firewall Connectors
CREATE TABLE firewall_connectors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    connector_type TEXT NOT NULL,         -- 'routeros', 'unifi', 'pfsense', 'opnsense'
    host TEXT NOT NULL,
    port INTEGER,
    username TEXT,
    password TEXT,                        -- Encrypted
    api_key TEXT,                         -- Encrypted (for UniFi)
    site_id TEXT,                         -- UniFi site
    address_list_name TEXT,               -- RouterOS: address list name
    enabled INTEGER DEFAULT 1,
    last_sync_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Firewall Blocklist (IPs pushed to firewalls)
CREATE TABLE firewall_blocklist (
    id TEXT PRIMARY KEY,
    threat_actor_id TEXT,
    ip_address TEXT NOT NULL,
    connector_id TEXT,
    pushed_at TEXT,
    expires_at TEXT,                      -- NULL = permanent
    status TEXT DEFAULT 'pending',        -- 'pending', 'pushed', 'expired', 'removed'
    error_message TEXT
);

-- Push Subscriptions (Web Push)
CREATE TABLE push_subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    p256dh_key TEXT NOT NULL,
    auth_key TEXT NOT NULL,
    user_agent TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Alert Channels
CREATE TABLE alert_channels (
    id TEXT PRIMARY KEY,
    user_id TEXT,                         -- NULL = global
    channel_type TEXT NOT NULL,           -- 'push', 'email', 'webhook', 'slack', 'telegram'
    config TEXT,                          -- JSON config (webhook URL, email, etc.)
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Alert Preferences (per user)
CREATE TABLE alert_preferences (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,             -- 'threat_detected', 'ip_blocked', 'firewall_pushed', 'cert_expiring'
    min_severity TEXT DEFAULT 'medium',   -- Only alert for this severity or higher
    channels TEXT,                        -- JSON array of channel IDs
    enabled INTEGER DEFAULT 1
);

-- Rate Limit Rules
CREATE TABLE rate_limit_rules (
    id TEXT PRIMARY KEY,
    proxy_host_id TEXT,                   -- NULL = global
    name TEXT NOT NULL,
    requests_per_second INTEGER,
    requests_per_minute INTEGER,
    requests_per_hour INTEGER,
    burst_size INTEGER DEFAULT 10,
    action TEXT DEFAULT 'reject',         -- 'reject', 'delay', 'log'
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- GeoIP Settings
CREATE TABLE geoip_settings (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,               -- 'maxmind', 'ip2location'
    database_path TEXT,
    license_key TEXT,                     -- Encrypted (for MaxMind)
    auto_update INTEGER DEFAULT 1,
    last_updated_at TEXT,
    enabled INTEGER DEFAULT 1
);

-- GeoIP Rules (country blocking)
CREATE TABLE geoip_rules (
    id TEXT PRIMARY KEY,
    proxy_host_id TEXT,                   -- NULL = global
    name TEXT NOT NULL,
    mode TEXT DEFAULT 'blocklist',        -- 'blocklist' or 'allowlist'
    countries TEXT NOT NULL,              -- JSON array of country codes
    action TEXT DEFAULT 'block',          -- 'block', 'log', 'challenge'
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Analytics: Hourly Aggregates (for charts)
CREATE TABLE analytics_hourly (
    id TEXT PRIMARY KEY,
    proxy_host_id TEXT,                   -- NULL = global
    hour TEXT NOT NULL,                   -- '2024-01-15T14:00:00'
    total_requests INTEGER DEFAULT 0,
    blocked_requests INTEGER DEFAULT 0,
    bytes_sent INTEGER DEFAULT 0,
    bytes_received INTEGER DEFAULT 0,
    avg_response_time_ms INTEGER,
    status_2xx INTEGER DEFAULT 0,
    status_3xx INTEGER DEFAULT 0,
    status_4xx INTEGER DEFAULT 0,
    status_5xx INTEGER DEFAULT 0,
    unique_ips INTEGER DEFAULT 0,
    UNIQUE(proxy_host_id, hour)
);

-- Analytics: Daily Aggregates
CREATE TABLE analytics_daily (
    id TEXT PRIMARY KEY,
    proxy_host_id TEXT,
    date TEXT NOT NULL,                   -- '2024-01-15'
    total_requests INTEGER DEFAULT 0,
    blocked_requests INTEGER DEFAULT 0,
    total_threats INTEGER DEFAULT 0,
    bytes_sent INTEGER DEFAULT 0,
    bytes_received INTEGER DEFAULT 0,
    avg_response_time_ms INTEGER,
    unique_ips INTEGER DEFAULT 0,
    top_countries TEXT,                   -- JSON: {"US": 1000, "GB": 500}
    top_ips TEXT,                         -- JSON: [{"ip": "1.2.3.4", "count": 100}]
    UNIQUE(proxy_host_id, date)
);

-- Analytics: Geographic Stats
CREATE TABLE analytics_geo (
    id TEXT PRIMARY KEY,
    proxy_host_id TEXT,
    date TEXT NOT NULL,
    country_code TEXT NOT NULL,
    requests INTEGER DEFAULT 0,
    blocked INTEGER DEFAULT 0,
    threats INTEGER DEFAULT 0,
    bytes INTEGER DEFAULT 0,
    UNIQUE(proxy_host_id, date, country_code)
);
```

---

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/login | Admin login |
| POST | /api/auth/logout | Logout |
| POST | /api/auth/refresh | Refresh token |
| GET | /api/auth/me | Current user |

### Proxy Hosts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/proxy-hosts | List all |
| POST | /api/proxy-hosts | Create |
| GET | /api/proxy-hosts/{id} | Get one |
| PUT | /api/proxy-hosts/{id} | Update |
| DELETE | /api/proxy-hosts/{id} | Delete |
| POST | /api/proxy-hosts/{id}/enable | Enable |
| POST | /api/proxy-hosts/{id}/disable | Disable |

### Certificates
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/certificates | List all |
| POST | /api/certificates | Upload custom |
| POST | /api/certificates/letsencrypt | Request Let's Encrypt |
| DELETE | /api/certificates/{id} | Delete |
| POST | /api/certificates/{id}/renew | Renew |

### Access Lists
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/access-lists | List all |
| POST | /api/access-lists | Create |
| PUT | /api/access-lists/{id} | Update |
| DELETE | /api/access-lists/{id} | Delete |

### Auth Wall
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/auth-walls | List all |
| POST | /api/auth-walls | Create |
| PUT | /api/auth-walls/{id} | Update |
| DELETE | /api/auth-walls/{id} | Delete |
| GET | /api/auth-providers | List OAuth providers |
| POST | /api/auth-providers | Create provider |
| GET | /api/ldap-configs | List LDAP configs |
| POST | /api/ldap-configs | Create LDAP config |
| POST | /api/ldap-configs/{id}/test | Test connection |

### Traffic
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/traffic | List logs (paginated) |
| GET | /api/traffic/{id} | Request details |
| GET | /api/traffic/stats | Statistics |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/settings | Get settings |
| PUT | /api/settings | Update settings |
| POST | /api/settings/reload-nginx | Reload config |
| GET | /health | Health check |

### WAF & Threat Detection
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/waf/rules | List WAF rules |
| POST | /api/waf/rules | Create custom rule |
| PUT | /api/waf/rules/{id} | Update rule |
| DELETE | /api/waf/rules/{id} | Delete rule |
| GET | /api/threats/events | List threat events (paginated) |
| GET | /api/threats/actors | List threat actors (IPs) |
| GET | /api/threats/actors/{ip} | Get IP threat profile |
| POST | /api/threats/actors/{ip}/block | Manual block IP |
| POST | /api/threats/actors/{ip}/unblock | Unblock IP |
| GET | /api/threats/thresholds | Get response thresholds |
| PUT | /api/threats/thresholds | Update thresholds |

### Firewall Integration
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/firewalls | List connectors |
| POST | /api/firewalls | Add connector |
| PUT | /api/firewalls/{id} | Update connector |
| DELETE | /api/firewalls/{id} | Remove connector |
| POST | /api/firewalls/{id}/test | Test connection |
| POST | /api/firewalls/{id}/sync | Sync blocklist |
| GET | /api/firewalls/blocklist | View pushed IPs |

### Push Notifications & Alerts
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/push/subscribe | Subscribe to push |
| DELETE | /api/push/unsubscribe | Unsubscribe |
| GET | /api/alerts/channels | List alert channels |
| POST | /api/alerts/channels | Add channel |
| PUT | /api/alerts/channels/{id} | Update channel |
| DELETE | /api/alerts/channels/{id} | Remove channel |
| GET | /api/alerts/preferences | Get preferences |
| PUT | /api/alerts/preferences | Update preferences |
| POST | /api/alerts/test | Send test notification |

### Rate Limiting
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/rate-limits | List rate limit rules |
| POST | /api/rate-limits | Create rule |
| PUT | /api/rate-limits/{id} | Update rule |
| DELETE | /api/rate-limits/{id} | Delete rule |

### GeoIP & Geographic Blocking
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/geoip/settings | Get GeoIP config |
| PUT | /api/geoip/settings | Update GeoIP config |
| POST | /api/geoip/update | Trigger database update |
| GET | /api/geoip/rules | List geo rules |
| POST | /api/geoip/rules | Create geo rule |
| PUT | /api/geoip/rules/{id} | Update geo rule |
| DELETE | /api/geoip/rules/{id} | Delete geo rule |
| GET | /api/geoip/lookup/{ip} | Lookup IP location |

### Analytics & Reporting
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/analytics/overview | Dashboard summary stats |
| GET | /api/analytics/traffic | Traffic over time (hourly/daily) |
| GET | /api/analytics/threats | Threat stats over time |
| GET | /api/analytics/geo | Geographic breakdown |
| GET | /api/analytics/hosts/{id} | Per-host analytics |
| GET | /api/analytics/top-ips | Top requesting IPs |
| GET | /api/analytics/top-threats | Top threat actors |
| GET | /api/analytics/status-codes | Status code breakdown |
| GET | /api/reports/export | Export report (PDF/CSV) |

---

## Docker Compose

```yaml
version: '3.8'

services:
  ghostwire-proxy-nginx:
    build: ./proxy
    container_name: ghostwire-proxy-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./data/certificates:/etc/nginx/certs:ro
      - ./data/nginx-configs:/etc/nginx/conf.d/proxy-hosts:ro
    depends_on:
      - ghostwire-proxy-api
    networks:
      - ghostwire-proxy-network

  ghostwire-proxy-ui:
    build: ./frontend
    container_name: ghostwire-proxy-ui
    restart: unless-stopped
    ports:
      - "88:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8089
      - NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
    depends_on:
      - ghostwire-proxy-api
    networks:
      - ghostwire-proxy-network

  ghostwire-proxy-api:
    build: ./backend
    container_name: ghostwire-proxy-api
    restart: unless-stopped
    ports:
      - "8089:8000"
    environment:
      - DATABASE_PATH=/data/sqlite/ghostwire-proxy.db
      - JWT_SECRET=${JWT_SECRET}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
    volumes:
      - ./data/sqlite:/data/sqlite
      - ./data/certificates:/data/certificates
      - ./data/nginx-configs:/data/nginx-configs
    networks:
      - ghostwire-proxy-network

  ghostwire-proxy-certbot:
    build: ./certbot
    container_name: ghostwire-proxy-certbot
    volumes:
      - ./data/certificates:/etc/letsencrypt
    networks:
      - ghostwire-proxy-network

networks:
  ghostwire-proxy-network:
    name: ghostwire-proxy-network
```

---

## WAF & Threat Response Architecture

```
                            ┌─────────────────────────────────┐
                            │         Incoming Request         │
                            └─────────────────┬───────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OpenResty (nginx)                               │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         Lua WAF Module (Fast)                           │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │ │
│  │  │   SQLi   │ │   XSS    │ │  Path    │ │   RCE    │ │   Scanner    │ │ │
│  │  │ Patterns │ │ Patterns │ │ Traversal│ │ Patterns │ │  Detection   │ │ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘ │ │
│  │       └────────────┴────────────┴────────────┴──────────────┘         │ │
│  │                                  │                                     │ │
│  │                    ┌─────────────▼─────────────┐                       │ │
│  │                    │   Per-Rule Action Config   │                       │ │
│  │                    │   • log | block | blocklist │                      │ │
│  │                    └─────────────┬─────────────┘                       │ │
│  └──────────────────────────────────┼─────────────────────────────────────┘ │
│                                     │                                        │
│                                     ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    Threat Engine (Backend API)                          │ │
│  │                                                                         │ │
│  │   ┌─────────────┐    ┌─────────────────┐    ┌───────────────────┐      │ │
│  │   │ Event Log   │───▶│  IP Reputation  │───▶│ Tiered Response   │      │ │
│  │   │ (SQLite)    │    │  (threat_actors)│    │                   │      │ │
│  │   └─────────────┘    └─────────────────┘    │ 1. Log only       │      │ │
│  │                                              │ 2. Warn (429)     │      │ │
│  │                                              │ 3. Temp block     │      │ │
│  │                                              │ 4. Perm block     │      │ │
│  │                                              │ 5. Firewall ban   │      │ │
│  │                                              └─────────┬─────────┘      │ │
│  └──────────────────────────────────────────────────────────┼──────────────┘ │
└─────────────────────────────────────────────────────────────┼────────────────┘
                                                              │
                         ┌────────────────────────────────────┼─────────────┐
                         │                                    │             │
                         ▼                                    ▼             ▼
              ┌─────────────────┐               ┌───────────────┐  ┌──────────────┐
              │   Push Notify   │               │   RouterOS    │  │    UniFi     │
              │   (Real-time)   │               │   API Block   │  │  API Block   │
              └─────────────────┘               └───────────────┘  └──────────────┘
```

---

## Auth Wall Architecture

```
Request → OpenResty → auth_wall.lua
                           │
                           ├─ Check session cookie
                           │
                           ├─ No session? → Redirect to auth
                           │                     │
                           │     ┌───────────────┼───────────────┐
                           │     ▼               ▼               ▼
                           │   Basic          OAuth2           LDAP
                           │   (popup)      (redirect)       (popup)
                           │     │               │               │
                           │     └───────────────┴───────────────┘
                           │                     │
                           │              Backend validates
                           │                     │
                           └─────── Session created ◄────────────┘
                                         │
                                    Request proxied
```

---

## Implementation Phases

### Phase 1: Project Scaffold
- [ ] Create directory structure
- [ ] Set up Docker Compose
- [ ] Initialize Next.js frontend with shadcn/ui
- [ ] Initialize FastAPI backend with SQLite
- [ ] Create OpenResty container
- [ ] Implement admin auth (login/logout)

### Phase 2: Proxy Host Management
- [ ] Proxy host CRUD API
- [ ] Upstream server management
- [ ] OpenResty config generation
- [ ] Config reload mechanism
- [ ] Frontend: Proxy hosts pages

### Phase 3: SSL Certificates
- [ ] Manual certificate upload
- [ ] Let's Encrypt integration
- [ ] Auto-renewal worker
- [ ] Frontend: Certificate pages

### Phase 4: Access Control
- [ ] Access list CRUD API
- [ ] Lua access_control module
- [ ] Frontend: Access list pages

### Phase 5: Auth Wall
- [ ] Auth wall configuration API
- [ ] Basic auth (Lua + API)
- [ ] OAuth2 providers
- [ ] LDAP integration
- [ ] Session management
- [ ] Frontend: Auth wall pages

### Phase 6: Traffic Inspection
- [ ] Lua traffic logging (optional per-site)
- [ ] Traffic log API
- [ ] Frontend: Traffic viewer

### Phase 7: WAF & Threat Detection
- [ ] Lua WAF rules (SQLi, XSS, path traversal, RCE)
- [ ] Threat event logging
- [ ] Threat actor tracking (IP reputation)
- [ ] Tiered response engine
- [ ] WAF rules management API
- [ ] Frontend: Threat dashboard, events log, IP management

### Phase 8: Firewall Integration
- [ ] RouterOS API connector
- [ ] UniFi API connector
- [ ] Blocklist sync service
- [ ] Frontend: Firewall connector management

### Phase 9: Mobile & Push Notifications
- [ ] PWA configuration (manifest, service worker)
- [ ] Web Push subscription API
- [ ] Alert channels (push, email, webhook)
- [ ] Real-time threat alerts
- [ ] Frontend: Alert preferences, mobile optimization

### Phase 10: Rate Limiting & GeoIP
- [ ] Rate limit configuration API
- [ ] Lua rate limiting module (shared dict)
- [ ] GeoIP database integration (MaxMind + IP2Location)
- [ ] Country blocking rules API
- [ ] Frontend: Rate limit & GeoIP settings

### Phase 11: Analytics & Reporting
- [ ] Analytics aggregation service (hourly/daily rollups)
- [ ] Dashboard overview API
- [ ] Traffic analytics charts (Recharts)
- [ ] Security analytics charts
- [ ] Geographic map visualization
- [ ] Per-host analytics pages
- [ ] Report export (PDF/CSV)
- [ ] Searchable log viewers

### Phase 12: Polish & Integration
- [ ] Ghostwire sync (optional)
- [ ] Audit logging
- [ ] Settings management
- [ ] Documentation

---

## Reference Files from Ghostwire

| Pattern | Reference |
|---------|-----------|
| Docker Compose | `docker-compose.yml` |
| FastAPI setup | `backend/app/main.py` |
| SQLAlchemy models | `backend/app/models/` |
| Pydantic schemas | `backend/app/schemas/` |
| JWT auth | `backend/app/core/security.py` |
| Next.js layout | `frontend/src/app/(dashboard)/layout.tsx` |
| Sidebar nav | `frontend/src/components/layout/sidebar.tsx` |
| shadcn config | `frontend/components.json` |

---

## Tech Stack

### Proxy Layer
| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Proxy Engine | OpenResty | 1.25.x | nginx + Lua scripting |
| Base Image | Alpine Linux | 3.19 | Lightweight container |
| Lua Libraries | lua-resty-http | latest | HTTP client for API calls |
| | lua-resty-jwt | latest | JWT validation |
| | lua-resty-session | latest | Session management |
| | lua-resty-maxminddb | latest | GeoIP lookups |
| WAF (optional) | ModSecurity | 3.x | OWASP CRS rules |

### Backend API
| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Framework | FastAPI | 0.115.x | Async REST API |
| Python | Python | 3.12 | Runtime |
| ORM | SQLAlchemy | 2.0.x | Async database access |
| Database Driver | aiosqlite | 0.20.x | Async SQLite |
| Validation | Pydantic | 2.10.x | Request/response models |
| Auth | python-jose | 3.3.x | JWT tokens |
| Password | bcrypt | 4.2.x | Password hashing |
| Encryption | cryptography | 43.x | Fernet for secrets |
| HTTP Client | httpx | 0.27.x | Async HTTP (firewall APIs) |
| LDAP | ldap3 | 2.9.x | LDAP authentication |
| OAuth | authlib | 1.3.x | OAuth2/OIDC client |
| ACME | acme | 2.x | Let's Encrypt client |
| GeoIP | geoip2 | 4.8.x | MaxMind database reader |
| Push | pywebpush | 1.14.x | Web Push notifications |
| PDF Export | weasyprint | 62.x | PDF report generation |

### Frontend UI
| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Framework | Next.js | 16.x | React framework |
| Language | TypeScript | 5.x | Type safety |
| UI Components | shadcn/ui | latest | Pre-built components |
| Styling | Tailwind CSS | 3.4.x | Utility-first CSS |
| Icons | Lucide React | latest | Icon library |
| Charts | Recharts | 2.x | Analytics visualizations |
| Maps | react-simple-maps | 3.x | Geographic visualizations |
| State | Zustand | 4.x | Client state management |
| Auth | NextAuth.js | 5.x | Session management |
| PWA | next-pwa | latest | Progressive Web App |
| Tables | TanStack Table | 8.x | Data grids |

### Infrastructure
| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Containers | Docker | 24.x | Containerization |
| Orchestration | Docker Compose | 2.x | Multi-container setup |
| SSL Certs | Certbot | 2.x | Let's Encrypt automation |
| GeoIP DB | MaxMind GeoLite2 | monthly | IP geolocation (free) |
| GeoIP DB | IP2Location LITE | monthly | Alternative geolocation |

### Firewall Integrations
| Firewall | Protocol | Library/Method |
|----------|----------|----------------|
| RouterOS (MikroTik) | REST API | httpx + custom client |
| UniFi | REST API | httpx + custom client |
| pfSense | REST API (pkg) | httpx + custom client |
| OPNsense | REST API | httpx + custom client |

### Ports
| Service | External | Internal | Purpose |
|---------|----------|----------|---------|
| Proxy HTTP | 80 | 80 | HTTP traffic |
| Proxy HTTPS | 443 | 443 | HTTPS traffic |
| Admin UI | 88 | 3000 | Next.js dashboard |
| Backend API | 8089 | 8000 | FastAPI |

### Data Storage
| Data Type | Storage | Retention |
|-----------|---------|-----------|
| Configuration | SQLite | Permanent |
| Traffic logs | SQLite | Configurable (7-90 days) |
| Threat events | SQLite | Configurable (30-365 days) |
| Analytics | SQLite (aggregated) | Permanent |
| GeoIP database | File (.mmdb) | Monthly update |
| SSL certificates | Files (encrypted) | Until expiry |
| Nginx configs | Generated files | Regenerated on change |

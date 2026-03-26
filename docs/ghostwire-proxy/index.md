---
title: Ghostwire Proxy
excerpt: A modern, self-hosted reverse proxy manager with built-in security — an alternative to Nginx Proxy Manager
---

## Overview

Ghostwire Proxy is a self-hosted reverse proxy management system built on OpenResty (Nginx + Lua) with a modern admin interface. It provides comprehensive proxy management alongside an integrated security stack including a Web Application Firewall, threat intelligence, GeoIP blocking, honeypot traps, and authentication walls.

![Dashboard](./_img/dashboard.png)

## Key Features

- **Reverse Proxy Management** — Create and manage proxy hosts with SSL termination, load balancing, WebSocket support, and custom locations
- **Let's Encrypt Integration** — Automated SSL certificate provisioning and renewal with DNS challenge support via Cloudflare
- **Web Application Firewall** — Rule-based request filtering for SQLi, XSS, path traversal, RCE, and scanner detection
- **Threat Intelligence** — Automated IP scoring with tiered escalation from monitoring to firewall banning
- **Firewall Integration** — Push blocked IPs to UniFi or MikroTik network firewalls for edge blocking
- **GeoIP Blocking** — Country-level allow/deny lists powered by MaxMind GeoLite2
- **Honeypot Traps** — Detect attackers probing common paths like `/wp-admin` or `/phpmyadmin`
- **Rate Limiting** — Per-host request throttling with burst support and custom thresholds
- **Authentication Walls** — Protect services behind login gates with local, LDAP, or OAuth2 authentication
- **Traffic Analytics** — Real-time dashboards with geographic heatmaps, performance metrics, and traffic breakdowns
- **Access Lists** — IP-based whitelists and blacklists for fine-grained access control
- **Security Presets** — One-click application of best-practice WAF, GeoIP, and rate limit configurations

## Architecture

| Layer | Technology |
|-------|------------|
| Proxy | OpenResty (Nginx + Lua) on Alpine |
| Frontend | Next.js 16+, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.12, FastAPI, SQLAlchemy |
| Database | PostgreSQL 16 |
| Auth | JWT + TOTP |

## Ports

| Port | Service |
|------|---------|
| 80 | Proxy HTTP |
| 443 | Proxy HTTPS |
| 88 | Admin UI |
| 8089 | API |

## Next Steps

- [Getting Started](./getting-started/) — Installation, requirements, and first login
- [Proxy Management](./proxy-management/) — Managing proxy hosts, certificates, and DNS
- [Security](./security/) — WAF, threat response, firewalls, and more
- [Monitoring](./monitoring/) — Analytics, traffic logs, and system health
- [Administration](./administration/) — Users, settings, alerts, and backups

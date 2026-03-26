---
title: Requirements
excerpt: System requirements and prerequisites for running Ghostwire Proxy
---

## System Requirements

| Requirement | Minimum |
|-------------|---------|
| CPU | 1 core |
| RAM | 1 GB |
| Disk | 5 GB free |
| OS | Any Docker-compatible Linux, Windows, or macOS |

## Software Prerequisites

- **Docker** 20.10+ with Docker Compose v2
- **Ports** 80, 443, 88, and 8089 available on the host

> [!TIP]
> Ports 80 and 443 are used by the reverse proxy itself. Port 88 serves the admin UI and port 8089 serves the API. You can remap ports 88 and 8089 via `docker-compose.override.yml` if needed.

## Network Requirements

- The host must be reachable on ports 80/443 from the internet (for proxying and Let's Encrypt HTTP challenges)
- If using DNS challenge for certificates (recommended), outbound HTTPS to the Cloudflare API is required
- The host must be able to reach your upstream services on their configured ports

## Optional: GeoIP Database

GeoIP blocking requires a MaxMind GeoLite2 Country database. A copy is included by default at `data/geoip/GeoLite2-Country.mmdb`. To enable automatic updates, configure a MaxMind license key in Settings.

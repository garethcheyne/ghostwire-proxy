---
title: Installation
excerpt: Deploy Ghostwire Proxy using Docker Compose
---

## Quick Start

:::steps
### Clone the repository

```bash
git clone https://github.com/garethcheyne/ghostwire-proxy.git
cd ghostwire-proxy
```

### Configure environment variables

Copy the example environment file and edit it with your settings:

```bash
cp .env.example .env
```

At minimum, set:

```bash
# Strong random secret for JWT tokens
JWT_SECRET=your-secure-random-string

# PostgreSQL credentials
POSTGRES_PASSWORD=your-secure-db-password

# Encryption key for stored secrets (OAuth, API keys, etc.)
ENCRYPTION_KEY=your-64-char-hex-key
```

### Start the services

```bash
docker compose up -d
```

This starts all containers:
- **ghostwire-proxy-nginx** — OpenResty reverse proxy (ports 80, 443, 88)
- **ghostwire-proxy-api** — FastAPI backend (port 8089)
- **ghostwire-proxy-ui** — Next.js admin interface
- **ghostwire-proxy-postgres** — PostgreSQL 16 database
- **ghostwire-proxy-certbot** — Certificate renewal service

### Access the admin panel

Open your browser and navigate to:

```
http://your-server-ip:88
```
:::

## Docker Compose Override

To customize ports or add volumes, create a `docker-compose.override.yml`:

```yaml
services:
  ghostwire-proxy-nginx:
    ports:
      - "8080:80"    # Change HTTP port
      - "8443:443"   # Change HTTPS port
      - "9088:88"    # Change admin UI port
```

## Building from Source

To rebuild all containers from source:

```bash
docker compose up -d --build
```

To rebuild only the admin UI after frontend changes:

```bash
docker compose up -d --build ghostwire-proxy-ui
```

> [!WARNING]
> Never use `docker compose down -v` — the `-v` flag destroys named volumes including the database. Use `docker compose restart` to restart services without data loss.

## Verify Installation

After starting, check that all services are healthy:

```bash
docker compose ps
```

All containers should show `Up` status. The admin UI should be accessible at `http://your-server-ip:88`.

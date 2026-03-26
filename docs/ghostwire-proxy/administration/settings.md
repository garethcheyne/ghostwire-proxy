---
title: Settings
excerpt: Global system configuration for WAF, rate limiting, SSL, logging, and more
---

The settings page provides global configuration for all Ghostwire Proxy features.

![Settings](../_img/settings.png)

## Security Settings

| Setting | Description |
|---------|-------------|
| **Enable WAF** | Global on/off switch for the Web Application Firewall |
| **Enable Rate Limiting** | Global on/off switch for rate limiting |

## SSL Settings

| Setting | Description |
|---------|-------------|
| **Default SSL Provider** | Let's Encrypt or manual certificates |
| **Auto-Renew Certificates** | Automatically renew certificates before expiry |

## Path Configuration

| Setting | Description |
|---------|-------------|
| **Nginx Config Path** | Where generated nginx configs are written |
| **Certificate Path** | Where SSL certificates are stored |

## Traffic Logging

| Setting | Description |
|---------|-------------|
| **Enable Logging** | Global on/off for per-request traffic logging |
| **Retention Days** | How many days to keep traffic logs before auto-purge |

## Default Site Behavior

Configure what happens when a request doesn't match any proxy host:

| Option | Description |
|--------|-------------|
| **Congratulations Page** | Show a default Ghostwire Proxy landing page |
| **Custom Redirect** | Redirect to a specific URL |
| **Custom Response** | Return a custom HTTP response |

## Trusted IPs

Add IP addresses that should bypass rate limiting and threat scoring. Common uses:

- Internal monitoring and health check systems
- CDN origin IP ranges
- Load balancer health probes

## IP Intelligence — AbuseIPDB

Optionally configure an AbuseIPDB API key to enrich threat actor data with community abuse scores and report history. See the full setup guide at [AbuseIPDB Integration](../security/abuseipdb.md).

| Setting | Description |
|---------|-------------|
| **API Key** | Your AbuseIPDB API key (free tier: 1,000 lookups/day) |

When configured, IP intelligence popups across the dashboard show the AbuseIPDB abuse confidence score, total reports, and Tor exit status.

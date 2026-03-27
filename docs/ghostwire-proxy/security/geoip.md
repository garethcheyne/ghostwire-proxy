---
title: GeoIP Blocking
excerpt: Block or allow traffic by country using MaxMind GeoLite2 geolocation
---

> Navigate to **Security → Rules** and select the **GeoIP** tab.

GeoIP blocking lets you restrict access to your services based on the geographic origin of requests. Use blocklists to deny specific countries or allowlists to permit only certain countries.

![GeoIP Blocking](../_img/rules-geoip.png)

## How It Works

On each request, the proxy looks up the client IP in the MaxMind GeoLite2 Country database to determine the country of origin. The request is then checked against your configured rules:

- **Blocklist mode** — Deny requests from listed countries, allow all others
- **Allowlist mode** — Allow only requests from listed countries, deny all others

## Creating a GeoIP Rule

| Field | Description |
|-------|-------------|
| **Name** | Descriptive rule name |
| **Description** | What this rule does |
| **Mode** | `blocklist` or `allowlist` |
| **Countries** | Select countries from the full ISO 3166-1 list (249 countries) |
| **Scope** | Global or per-proxy-host |
| **Enabled** | Toggle rule on/off |

> [!TIP]
> Use the search filter in the country selector to quickly find countries by name or code.

## Global Settings

| Setting | Description |
|---------|-------------|
| **Database Provider** | MaxMind GeoLite2 (default) or IP2Location |
| **Database Path** | File path to the MMDB database |
| **Auto-Update** | Automatically update the GeoIP database |
| **Enable GeoIP** | Global on/off switch |

## Common Use Cases

### Block high-risk countries

Create a blocklist rule with countries known for high volumes of attack traffic. Apply it globally or to specific public-facing hosts.

### Allow domestic traffic only

Create an allowlist rule with only your country. Apply it to services that should only be accessed domestically.

### Per-service restrictions

Different proxy hosts can have different GeoIP rules. For example, your public website might allow all countries while your admin panel only allows your home country.

## GeoIP Database

A MaxMind GeoLite2 Country database is included at `data/geoip/GeoLite2-Country.mmdb`. To enable automatic updates, configure a MaxMind license key in [Settings](../administration/settings.md).

---
title: AbuseIPDB Integration
excerpt: Enrich threat intelligence with abuse confidence scores and report history from AbuseIPDB
---

AbuseIPDB is a free community-driven IP reputation database. When configured, Ghostwire Proxy queries AbuseIPDB for every attacker IP to display abuse confidence scores, total reports, and whether the IP is a known Tor exit node.

## What You Get

With AbuseIPDB enabled, the following data appears in threat actor intelligence popups, the honeypot page, and IP address tooltips:

| Data | Description |
|------|-------------|
| **Abuse Confidence Score** | 0–100% score indicating how likely the IP is malicious |
| **Total Reports** | Number of abuse reports filed by the community |
| **Last Reported** | When the IP was last reported |
| **Is Tor Exit** | Whether the IP is a known Tor exit node |

Without an API key, these fields show "AbuseIPDB unavailable" and threat scoring relies solely on local WAF/honeypot events and ip-api.com geolocation data.

## Setting Up AbuseIPDB

:::steps

### Create a free account

Go to [abuseipdb.com/register](https://www.abuseipdb.com/register) and sign up. You only need a valid email address.

### Verify your email

Check your inbox and click the verification link sent by AbuseIPDB.

### Create an API key

Navigate to **User Settings → API** ([abuseipdb.com/account/api](https://www.abuseipdb.com/account/api)) and click **Create Key**. Give it a name like "Ghostwire Proxy".

### Add the key to Ghostwire Proxy

In the Ghostwire admin panel, go to **Settings** and scroll to the **IP Intelligence — AbuseIPDB** section. Paste your API key and click **Save**.

:::

## Rate Limits

| Plan | Daily Lookups | Cost |
|------|--------------|------|
| **Free** | 1,000/day | Free |
| **Basic** | 10,000/day | $19.99/mo |
| **Premium** | 100,000/day | $99.99/mo |

The free plan is sufficient for most installations. Ghostwire queries AbuseIPDB once per unique IP and caches the result for 24 hours, so 1,000 lookups/day covers a large volume of unique attackers.

> [!TIP]
> You do **not** need to subscribe to any blocklist or download any database. Ghostwire automatically queries individual IPs on demand using the AbuseIPDB check endpoint.

## How It Works

1. When a new attacker IP is detected (via WAF, honeypot, or traffic analysis), Ghostwire triggers an enrichment lookup
2. If an AbuseIPDB API key is configured, it queries the `/api/v2/check` endpoint for that IP
3. The response (abuse score, report count, Tor flag) is stored alongside the IP's geolocation and reverse DNS data
4. Enrichment is cached for 24 hours before re-fetching
5. The enrichment data appears in the IP intelligence popup across all pages

## Removing the API Key

To disable AbuseIPDB lookups, go to **Settings → IP Intelligence — AbuseIPDB** and click the **Remove** button. Existing enrichment data remains cached until it expires naturally (24 hours) or until the enrichment cleanup runs (7 days).

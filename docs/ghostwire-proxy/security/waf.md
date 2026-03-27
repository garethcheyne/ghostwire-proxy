---
title: Web Application Firewall
excerpt: Regex-based request filtering to block SQL injection, XSS, path traversal, and more
---

> Navigate to **Security → Rules** and select the **WAF Rules** tab.

The Web Application Firewall (WAF) inspects every incoming request at the proxy layer using pattern-matching rules. Malicious requests are blocked before they reach your upstream services.

![WAF Rules](../_img/rules-waf.png)

## How It Works

The WAF runs in OpenResty's `access_by_lua` phase. For each request, it:

1. Checks if the client IP is already blocked
2. Matches the request URI, query string, and headers against enabled WAF rules
3. If a rule matches, performs the configured action (log, block, or blocklist)
4. Records the event for analytics and threat scoring

## Rule Categories

| Category | Description |
|----------|-------------|
| **SQLi** | SQL injection patterns (`UNION SELECT`, `OR 1=1`, etc.) |
| **XSS** | Cross-site scripting payloads (`<script>`, event handlers) |
| **Path Traversal** | Directory traversal attempts (`../`, `/etc/passwd`) |
| **RCE** | Remote code execution indicators (command injection patterns) |
| **Scanner** | Known vulnerability scanner User-Agent fingerprints |
| **Custom** | Your own regex-based detection patterns |

## Creating a WAF Rule

Each rule has the following configuration:

| Field | Description |
|-------|-------------|
| **Name** | Descriptive rule name |
| **Description** | What this rule detects |
| **Pattern** | Regex pattern to match against requests |
| **Category** | Rule category (SQLi, XSS, etc.) |
| **Severity** | `critical`, `high`, `medium`, or `low` |
| **Action** | What to do when the rule matches |
| **Scope** | Global (all hosts) or per-proxy-host |
| **Enabled** | Toggle rule on/off |

## Actions

| Action | Behavior |
|--------|----------|
| **Log** | Record the event but allow the request through |
| **Block** | Return HTTP 403 Forbidden |
| **Blocklist** | Block the request and add the IP to the [threat tracking](./threats.md) system |

> [!TIP]
> Start with **Log** mode for new rules to verify they match correctly without blocking legitimate traffic. Switch to **Block** or **Blocklist** once you're confident in the pattern.

## Rule Scope

- **Global rules** apply to all proxy hosts
- **Per-host rules** only apply to a specific proxy host

This allows you to create strict rules for public-facing services while keeping internal services more permissive.

## WAF Rule Sets

Rule sets group related rules into named collections. Use [Security Presets](./presets.md) to quickly apply recommended rule sets like the OWASP Core Rule Set.

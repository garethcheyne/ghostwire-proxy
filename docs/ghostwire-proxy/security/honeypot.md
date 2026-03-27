---
title: Honeypot Traps
excerpt: Detect attackers scanning for common vulnerable paths like /wp-admin or /phpmyadmin
---

> Navigate to **Security → Threats** and select the **Honeypot** tab.

Honeypot traps create fake endpoints that mimic commonly-targeted paths. When an attacker probes these paths, the event is logged and the IP can be automatically added to the threat tracking system.

![Honeypot](../_img/threats-honeypot.png)

## How It Works

Attackers routinely scan web servers for known vulnerable paths like `/wp-admin`, `/phpmyadmin`, or `/.env`. By creating honeypot traps on these paths, you can detect and respond to this reconnaissance activity.

When a request hits a honeypot path:

1. The trap is triggered and the event is logged
2. Client details are recorded (IP, User-Agent, headers, request body)
3. GeoIP country is looked up
4. If auto-block is enabled, the IP is added to the [threat tracking](./threats.md) system
5. A configurable response is returned to the attacker

## Creating a Honeypot Trap

| Field | Description |
|-------|-------------|
| **Path** | URI path to trap (e.g., `/wp-admin`, `/phpmyadmin`) |
| **Name** | Descriptive trap name |
| **Description** | Notes about what this trap detects |
| **Type** | `standard` (log hit), `redirect`, or `custom response` |
| **Response Code** | HTTP status code to return (usually 200 to appear legitimate) |
| **Response Body** | Optional custom response content |
| **Severity** | `critical`, `high`, `medium`, or `low` |
| **Auto-Block** | Automatically add the IP to threat tracking |
| **Scope** | Global or per-proxy-host |

## Honeypot Hit Log

The hit log shows every access to your trap paths:

| Column | Description |
|--------|-------------|
| **Timestamp** | When the trap was triggered |
| **IP Address** | Client IP |
| **Method** | HTTP method (GET, POST, etc.) |
| **URI** | Full request URI |
| **User-Agent** | Client User-Agent string |
| **Country** | GeoIP country of origin |
| **Action Taken** | logged, blocked, or temp blocked |

## Common Trap Paths

| Path | Targets |
|------|---------|
| `/wp-admin` | WordPress admin scanners |
| `/wp-login.php` | WordPress login brute force |
| `/phpmyadmin` | phpMyAdmin scanners |
| `/.env` | Environment file disclosure |
| `/admin` | Generic admin panel scanners |
| `/xmlrpc.php` | WordPress XML-RPC attacks |
| `/api/v1/admin` | API enumeration |
| `/.git/config` | Git repository disclosure |

> [!TIP]
> Set the response code to `200` for standard traps. This makes the honeypot appear legitimate to attackers, encouraging them to continue and reveal more about their techniques.

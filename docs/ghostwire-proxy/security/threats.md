---
title: Threat Response
excerpt: Automated IP threat scoring with tiered escalation from monitoring to firewall banning
---

The threat response system tracks malicious IP addresses, accumulates threat scores based on security events, and automatically escalates responses from monitoring through to permanent firewall bans.

![Threats](../_img/threats.png)

## How It Works

When the WAF, honeypot, or other security features detect malicious activity, the source IP receives threat score points. As the cumulative score crosses configurable thresholds, the response automatically escalates.

## Escalation Levels

| Level | Description |
|-------|-------------|
| :badge[Monitored]{info} | IP is being tracked, no action taken |
| :badge[Warned]{warning} | Score crossed warning threshold, logged as alert |
| :badge[Temp Blocked]{warning} | Requests rejected for a configurable duration |
| :badge[Perm Blocked]{error} | All requests permanently rejected |
| :badge[Firewall Banned]{error} | IP pushed to network firewall for edge blocking |

## Threat Events Tab

The events tab shows a real-time feed of all security events:

| Column | Description |
|--------|-------------|
| **Timestamp** | When the event occurred |
| **IP Address** | Source IP of the attacker |
| **Category** | Attack type (SQLi, XSS, scanner, etc.) |
| **Severity** | critical, high, medium, or low |
| **Matched Rule** | The WAF or honeypot rule that triggered |
| **Matched Content** | The payload or pattern that was detected |
| **Action** | What action was taken |
| **Country** | GeoIP country of origin |

Use the filters to narrow down events by IP address, severity, or attack category.

## Threat Actors Tab

The threat actors tab shows unique IP addresses that have triggered security events:

| Column | Description |
|--------|-------------|
| **IP Address** | The tracked IP |
| **Threat Score** | Cumulative threat score |
| **Status** | Current escalation level |
| **Total Events** | Number of events from this IP |
| **Country** | GeoIP country of origin |
| **Last Seen** | When this IP was last active |

### Manual Escalation

Administrators can manually promote an IP's status (e.g., from monitored to permanently blocked) or remove an IP from tracking entirely.

### IP Intelligence

Click on a threat actor to view detailed intelligence:

- Reverse DNS lookup
- Abuse report history
- ISP / organization
- Event history for this IP

## Configuring Thresholds

Threat score thresholds are configurable in Settings. Each severity level contributes different points:

| Severity | Default Points |
|----------|---------------|
| Critical | 25 |
| High | 15 |
| Medium | 5 |
| Low | 1 |

When an IP's cumulative score crosses a threshold, the next escalation level is triggered automatically.

## Integration with Firewalls

At the highest escalation level, blocked IPs can be automatically pushed to your network firewalls for edge-level blocking. See [Firewall Integration](./firewalls.md) for configuration details.

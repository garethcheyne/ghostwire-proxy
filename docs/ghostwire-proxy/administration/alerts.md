---
title: Alert Channels
excerpt: Configure notification delivery via webhook, email, Slack, or web push
---

Alert channels define how security notifications are delivered outside the admin panel.

![Alerts](../_img/alerts.png)

## Supported Channels

| Channel | Delivery |
|---------|----------|
| **Webhook** | HTTP POST to a custom URL |
| **Email** | SMTP email delivery |
| **Slack** | Message via Slack webhook |
| **Web Push** | Browser push notifications |

## Creating a Channel

| Field | Description |
|-------|-------------|
| **Name** | Channel name |
| **Type** | Webhook, email, Slack, or web push |
| **Endpoint** | URL or email address for delivery |
| **Enabled** | Toggle channel on/off |

### Webhook Configuration

Provide a URL that accepts HTTP POST requests. The request body contains a JSON payload with event details (type, summary, severity, timestamp, IP, and host).

Webhook and Slack URLs must be `http://` or `https://` and must not point at an internal address
(loopback, private ranges, link-local including cloud metadata, carrier-grade NAT). The check runs
when the channel is saved and again before each delivery. To send to a receiver on your own
network, set the `alerts_allow_internal_webhooks` setting to `true`.

Creating, editing and testing channels needs an admin account.

### Email Configuration

Configure SMTP settings for email delivery:

- SMTP server hostname and port
- Authentication credentials
- TLS/SSL toggle
- Sender and recipient addresses

### Slack Configuration

Provide a Slack incoming webhook URL. Notifications are formatted as Slack message blocks with severity color coding.

### Web Push

Web push requires VAPID keys to be configured in your environment variables. Users can subscribe to push notifications directly in their browser.

## Alert Types

Choose what each user is told about on **Notifications → Subscriptions**: a switch and a minimum
severity per type.

| Type | Key | Sent when |
|------|-----|-----------|
| Threat Detected | `threat_detected` | WAF blocks, honeypot hits and suspicious activity |
| IP Blocked | `ip_blocked` | An IP is blocked automatically |
| Firewall Rule Pushed | `firewall_pushed` | Firewall rules are synced to a provider |
| Certificate Expiring | `cert_expiring` | A certificate is close to expiry |
| Host Down | `host_down` | Every backend of a proxy host stops answering (and `host_recovered` when it answers again) |
| Backend Server Down | `upstream_server_down` | One server of a load-balanced host stops answering while the host stays up (severity high) |
| Backend Server Recovered | `upstream_server_recovered` | That server answers again (severity medium) |

Host Down alerts go to every push device whatever the subscriptions say, plus the channels of
your Host Down subscription. The two backend server types are **on by default** and follow your
Host Down subscription (its channels and minimum severity) until you change them; switching one
off also stops its push notifications. See
[Load balancing](../proxy-management/load-balancing.md#alerts-for-a-single-backend) for when they
fire, flap protection and how they combine with Host Down.

The webhook payload for a backend alert carries `data` with `host_id`, `domain`, `domains`,
`server_id`, `server`, `lb_method`, `lb_method_label`, `error`, `latency_ms`, `healthy`, `total`,
`backends` (e.g. "2 of 4 backends healthy"), `auto_down` and, for a recovery, `downtime`.

## Testing Channels

Click the **Test** button on any channel to send a test notification and verify delivery.

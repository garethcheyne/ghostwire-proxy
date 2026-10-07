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

## Testing Channels

Click the **Test** button on any channel to send a test notification and verify delivery.

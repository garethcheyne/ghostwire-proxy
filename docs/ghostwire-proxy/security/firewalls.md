---
title: Firewall Integration
excerpt: Push blocked IPs to UniFi or MikroTik network firewalls for edge-level blocking
---

Firewall integration allows Ghostwire Proxy to push permanently blocked IPs to your network firewalls, blocking malicious traffic at the network edge before it reaches the proxy.

![Firewalls](../_img/firewalls.png)

## Supported Firewalls

| Firewall | Method | Status |
|----------|--------|--------|
| **Ubiquiti UniFi** | Controller API | :badge[Supported]{success} |
| **MikroTik RouterOS** | REST API | :badge[Supported]{success} |
| **pfSense / OPNsense** | — | :badge[Planned]{info} |

## Adding a Firewall Connector

### UniFi Configuration

| Field | Description |
|-------|-------------|
| **Name** | Descriptive connector name |
| **Host** | UniFi Controller hostname or IP |
| **Port** | Controller port (default: 443) |
| **Username** | Controller admin username |
| **Password** | Controller admin password |
| **Site ID** | Site name for multi-site installations (default: `default`) |

### MikroTik Configuration

| Field | Description |
|-------|-------------|
| **Name** | Descriptive connector name |
| **Host** | RouterOS hostname or IP |
| **Port** | REST API port (default: 443) |
| **Username** | RouterOS admin username |
| **Password** | RouterOS admin password |
| **Address List** | Name of the address list for blocked IPs (e.g., `ghostwire-blocklist`) |

> [!IMPORTANT]
> Credentials are encrypted at rest using the `ENCRYPTION_KEY` from your environment configuration.

## Test Connectivity

After configuring a connector, click the **Test** button to verify:
- Network reachability
- Authentication credentials
- API permissions

## Blocklist Management

The firewall blocklist tab shows all IPs currently blocked at the firewall level:

| Column | Description |
|--------|-------------|
| **IP Address** | The blocked IP |
| **Added** | When the IP was pushed to the firewall |
| **Expiry** | When the block expires (if temporary) |
| **Status** | Sync status (synced, pending, failed) |

### Manual Management

- **Remove** — Delete an IP from the firewall blocklist
- **Expire** — Set an expiration time on an existing block
- **Sync Status** — View last push time and any errors per connector

## How It Works

When the [threat response system](./threats.md) escalates an IP to the **firewall_banned** level:

1. The IP is queued for firewall push
2. For each enabled connector, Ghostwire Proxy calls the firewall API
3. The IP is added to a firewall rule (UniFi) or address list (MikroTik)
4. Traffic from the IP is dropped at the network edge

This means the proxy never even sees the traffic, reducing load and improving security.

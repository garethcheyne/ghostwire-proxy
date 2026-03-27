---
title: Rate Limiting
excerpt: Per-host request throttling with burst support and custom thresholds
---

> Navigate to **Security → Rules** and select the **Rate Limits** tab.

Rate limiting protects your upstream services from excessive traffic by throttling requests per client IP.

![Rate Limits](../_img/rules-rate-limits.png)

## How It Works

Rate limiting runs in OpenResty using an in-memory shared dictionary for tracking. Each client IP is tracked per-host with a sliding window counter. When the limit is exceeded, requests are rejected with HTTP 429 (Too Many Requests) or delayed, depending on the configured action.

## Creating a Rate Limit Rule

| Field | Description |
|-------|-------------|
| **Name** | Descriptive rule name |
| **Description** | Notes about this rule |
| **Requests per Second** | Short-window rate limit |
| **Requests per Minute** | Sliding window rate limit |
| **Burst Size** | Number of requests allowed to exceed the limit momentarily |
| **Action** | `reject` (return 429) or `delay` (slow down responses) |
| **Scope** | Global or per-proxy-host |
| **Enabled** | Toggle rule on/off |

## Response Headers

When rate limiting is active, the following headers are added to responses:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Remaining` | Number of requests remaining in the current window |
| `X-RateLimit-Reset` | Seconds until the window resets |

## Trusted IPs

IPs listed as trusted in [Settings](../administration/settings.md) bypass rate limiting entirely. Use this for internal monitoring tools, health checks, or CDN origin IPs.

> [!WARNING]
> Rate limit state is stored in memory and resets if the proxy restarts. This is by design for performance — persistent rate limiting with disk-backed storage would add latency to every request.

## Common Configurations

| Use Case | Requests/min | Burst | Action |
|----------|-------------|-------|--------|
| Public API | 60 | 10 | Reject |
| Login page | 10 | 3 | Reject |
| Static assets | 300 | 50 | Delay |
| Aggressive protection | 20 | 5 | Reject |

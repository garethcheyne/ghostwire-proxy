---
title: System Monitoring
excerpt: Real-time CPU, memory, disk, network, and service health monitoring
---

The system monitoring page provides real-time visibility into server resources and service health.

![System Monitoring](../_img/system.png)

## Resource Metrics

| Metric | Details |
|--------|---------|
| **CPU** | Usage percentage and core count |
| **Memory** | Used, total, available, and percentage |
| **Disk** | Used, total, free, and percentage |
| **Network** | Bytes sent/received (total and rate) |

## Service Health

Live health checks for core services:

| Service | Check |
|---------|-------|
| **Nginx** | Proxy server responding correctly |
| **API** | Backend service reachable |
| **Database** | PostgreSQL connection active |

## Container Metrics

When running in Docker, per-container metrics are displayed:

- CPU usage percentage
- Memory usage
- Network I/O
- Uptime and status

## Database Statistics

| Stat | Description |
|------|-------------|
| **Database Size** | Current PostgreSQL database size |
| **Active Connections** | Number of active database connections |
| **Table Counts** | Row counts for key tables |

## Metrics History

A time-series graph tracks resource usage over time, allowing you to identify trends and capacity issues before they become critical.

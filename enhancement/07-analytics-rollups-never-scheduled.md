# 07 — Analytics rollups are never scheduled, so retention destroys history

**Severity:** High
**Answers:** "analytics are slow" / "why can't I compare this month to last quarter"

## TL;DR

`backend/app/services/analytics_service.py` implements three working aggregators —
`aggregate_hourly()`, `aggregate_daily()`, `aggregate_geo()` — and
`backend/app/models/analytics.py` defines the three tables they write to. **Nothing
ever calls them.** All three tables are empty.

Two consequences, one of which is irreversible:

1. Every analytics query is computed live against `traffic_logs` (626k rows and
   growing), instead of against pre-aggregated rows.
2. The nightly retention job prunes `traffic_logs` — and because nothing rolled
   those rows up first, **the history is destroyed rather than summarised**. Every
   day this stays unscheduled, another day of history becomes permanently
   unanswerable.

## Evidence

```
$ psql -c "SELECT (SELECT count(*) FROM analytics_hourly) hourly,
                  (SELECT count(*) FROM analytics_daily)  daily,
                  (SELECT count(*) FROM analytics_geo)    geo;"
 hourly | daily | geo
      0 |     0 |   0
```

The aggregators exist and are complete:

```
$ grep -n "^async def" backend/app/services/analytics_service.py
18:async def aggregate_hourly(db: AsyncSession, hours_back: int = 2) -> int:
92:async def aggregate_daily(db: AsyncSession, days_back: int = 2) -> int:
185:async def aggregate_geo(db: AsyncSession, days_back: int = 2) -> int:
```

Nothing references them outside the module and `models/__init__.py`:

```
$ grep -rn "analytics_service\|aggregate_hourly\|aggregate_daily" backend/app/main.py backend/app/api/routes/
(no matches)
```

Meanwhile `main.py` runs a daily retention cleanup that deletes from
`traffic_logs`, `threat_events` and `audit_logs`.

## Root cause

Same pattern as [06](06-location-dialog-missing-timeout-and-advanced-fields.md):
the capability was built end-to-end but the final wiring step — a background task,
in this case — was never added. There is no test or check that would notice a
service with no callers.

## Impact

- Analytics latency grows linearly with retained traffic, and the existing
  optimisation work (`92150cd perf: reduce dashboard/system page load times`)
  fights a problem that the rollups were designed to eliminate.
- Long-range reporting is impossible and becomes *more* impossible daily. This is
  the only item in this backlog that causes irreversible data loss while it sits
  open.
- `AnalyticsDaily.unique_ips` / `top_countries` / `top_ips` — already modelled —
  are unavailable, so there is no unique-visitor metric at all.

## Recommended fix

Add a background loop in `main.py` alongside the existing metrics/backup/retention
tasks: run `aggregate_hourly()` hourly and `aggregate_daily()` + `aggregate_geo()`
daily, **before** the retention cleanup runs, so rows are summarised before they
are pruned. Backfill once on startup so existing retained traffic is captured
before the next prune.

Verify by confirming the three tables populate and that a daily row's
`total_requests` matches a `count(*)` over `traffic_logs` for the same date.

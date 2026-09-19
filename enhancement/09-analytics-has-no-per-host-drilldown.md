# 09 — Analytics has no per-host drill-down, though the backend already supports it

**Severity:** Medium
**Status:** **Done** (2026-09-09) — see [README](README.md#done).
**Answers:** "I want to click on a host and view all its traffic, popular pages etc"

## TL;DR

`GET /api/analytics/dashboard` already accepts `proxy_host_id` and already
computes top hosts, top pages and top referrers. The UI never passes the
parameter, and the "Top Hosts" rows it renders are not clickable — so every
number in Analytics is fleet-wide and there is no way to ask "what is happening
on *this* host".

## Evidence

Backend supports it (`backend/app/api/routes/analytics.py`):

```python
@router.get("/dashboard", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(
    period: str = Query("7d", pattern="^(24h|7d|30d|90d)$"),
    proxy_host_id: Optional[str] = None,     # <- accepted, and applied to base_filter
```

and already aggregates the interesting dimensions:

```python
top_pages_query = (
    select(TrafficLog.request_uri, func.count(...), func.avg(TrafficLog.response_time))
    .group_by(TrafficLog.request_uri).order_by(...).limit(10)
)
top_referrers_query = ...
```

Frontend renders them but never filters:

```
$ grep -rn "proxy_host_id" frontend/src/components/analytics/ \
      frontend/src/app/\(dashboard\)/dashboard/analytics/
(no matches)
```

`traffic-tab.tsx` maps over `data.top_hosts` as plain rows — no link, no click
handler.

## Root cause

Frontend/backend drift, the same shape as
[06](06-location-dialog-missing-timeout-and-advanced-fields.md): the API grew a
filter the UI was never taught to use.

## Impact

- With 17 proxied hosts, fleet-wide averages hide per-site problems entirely. A
  single host serving 5xx or slow responses is invisible against the aggregate.
- The Traffic page can filter by host; Analytics cannot, so the two views
  disagree about what question they answer.

## Recommended fix

- Add a host selector to the Analytics page, passed through as `proxy_host_id`
  to the dashboard query.
- Make each "Top Hosts" row clickable, selecting that host.
- Show the selected host in the heading and offer a clear "All hosts" reset.

Purely a frontend change — no API work required.

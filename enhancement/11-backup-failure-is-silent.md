# 11 — A failing scheduled backup is silent

**Severity:** Medium
**Status:** **Done** (2026-09-09) — per-run alerts plus a 26h stale-backup watchdog. Offsite copy still not implemented. See [README](README.md#done).
**Answers:** "how would we know if backups stopped working?"

## TL;DR

Scheduled backups run daily at 02:00 UTC via `scheduled_backup_loop` in
`backend/app/main.py` and are known-good (proven end-to-end after the August
purge). But a failure is only ever written to the container log:

```python
except Exception as e:
    logger.error(f"Scheduled backup failed: {e}")
```

Nobody reads container logs daily. The failure mode is therefore identical to the
one that made the August purge unrecoverable: believing backups exist while they
silently do not.

## Evidence

- `backup_settings.auto_backup_enabled = True`, retention 30d / 14 backups.
- The only failure handling in the loop is `logger.error`.
- There is now a working alert pipeline (`dispatch_alert`, push, webhook, Slack,
  Telegram, email) that nothing in the backup path uses.

## Root cause

Backups were made real after the purge, but the monitoring of the backups was not
— and at the time there was no alert pipeline to hook into. There is now.

## Impact

- A backup that starts failing (disk full is the obvious candidate — the host sits
  at 84%, see [02](02-disk-pressure-and-log-rotation.md)) goes unnoticed until it
  is needed.
- Backups live on the same disk as everything else, so the scenario where they are
  needed and the scenario where they fail are correlated.

## Recommended fix

- Dispatch a `backup_failed` alert (critical) when `create_backup` raises, and a
  `backup_completed` alert (low) on success — both push methods already exist and
  have zero call sites.
- Alert if no successful backup has completed in more than ~26 hours, which
  catches the loop dying entirely rather than individual runs failing.
- Longer term, an offsite copy: current backups protect against a logical purge,
  not against loss of the host.

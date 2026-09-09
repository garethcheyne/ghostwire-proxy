# 13 — A fresh install cannot run its own migrations

**Severity:** High
**Status:** **Open** (2026-09-09) — found while adding migrations 0011/0012; those two are written defensively so they survive it, but the underlying fault is untouched.
**Answers:** "would a brand-new deployment even come up?"

## TL;DR

`alembic upgrade head` fails on an empty database. Migration `0001` builds the
baseline by calling `Base.metadata.create_all()` against the **live** models, so
it creates every column the models currently have — including columns that later
migrations are supposed to add. Those later migrations then fail with
`DuplicateColumn`.

Existing deployments are fine: they ran `0001` back when the models were smaller,
so each additive migration had real work to do at the time. Only a *new* install
hits this, which is exactly the case nobody exercises.

## Evidence

```
$ alembic upgrade head        # against an empty database
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, baseline schema
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, seed default WAF rules
INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, add abuseipdb blacklist cache
INFO  [alembic.runtime.migration] Running upgrade 0003 -> 0004, add abuseipdb_reported_at

sqlalchemy.exc.ProgrammingError: (psycopg2.errors.DuplicateColumn)
  column "abuseipdb_reported_at" of relation "threat_actors" already exists
[SQL: ALTER TABLE threat_actors ADD COLUMN abuseipdb_reported_at TIMESTAMP WITH TIME ZONE]
```

`0004` is only the first casualty — `0005` through `0010` are all additive against
tables `create_all()` has already built in full, so each would fail the same way.

## Root cause

`backend/alembic/versions/0001_baseline_schema.py`:

```python
def upgrade() -> None:
    # Import all models so Base.metadata is fully populated
    ...
    Base.metadata.create_all(bind=bind, checkfirst=True)
```

A baseline built from live models is not a snapshot of a point in history — it is
always "whatever the code looks like today". That makes the migration chain
self-contradictory: `0001` and `0004` both claim to create
`threat_actors.abuseipdb_reported_at`.

`checkfirst=True` only guards whole tables, not individual columns, so it does not
help here.

## Impact

- A new deployment cannot start: `entrypoint.sh` runs `alembic upgrade head`
  before the app, and a non-zero exit there stops the container.
- Disaster recovery is affected too — restoring onto a clean database is the same
  code path as a fresh install.
- Every future additive migration inherits the problem, so each one has to be
  written defensively (as 0011 and 0012 now are) or it breaks new installs.

## Recommended fix

Pick one:

1. **Freeze the baseline.** Replace the `create_all()` call in `0001` with the
   explicit `op.create_table(...)` statements for the schema *as it stood when
   0001 was written*, then let 0002-0012 apply on top. This is the correct fix:
   the chain becomes a real history and every migration has exactly one author.
2. **Stamp instead of migrating on a fresh database.** Have `entrypoint.sh`
   detect an empty database, run `create_all()` once, and `alembic stamp head` —
   never replaying the chain. Simpler, but it means the migrations are never
   exercised, so a bug in one is only discovered on an upgrade.

Option 1 is worth the hour. Until then, keep writing additive migrations with an
inspector guard, the way `0011_add_admin_mfa.py` does:

```python
def _existing_columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
```

## Verification

Both paths were tested for 0011/0012 and pass:

- fresh database (`create_all()` already made the columns) — migrations no-op cleanly;
- pre-0011 database (columns genuinely absent) — migrations add all 5 columns,
  the `report_schedules` table and its index.

The same two-path test should be the acceptance criterion for whichever fix is chosen.

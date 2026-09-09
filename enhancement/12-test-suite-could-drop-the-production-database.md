# 12 — The test suite could drop the production database

**Severity:** Critical
**Status:** **Partial** (2026-09-09) — conftest guard done; committed password and the CI `DATABASE_URL` mismatch still open. See [README](README.md#partial).
**Answers:** "how did the database get purged?"

## TL;DR

`backend/tests/conftest.py` ran `Base.metadata.drop_all()` after **every test**,
against whatever `DATABASE_URL` pointed at. It tried to protect itself with:

```python
os.environ.setdefault("DATABASE_URL", "...@ghostwire-proxy-postgres:5432/ghostwire_proxy_test")
...
TEST_DATABASE_URL = os.environ["DATABASE_URL"]
```

`setdefault` only applies when the variable is **unset**. In every environment
where `DATABASE_URL` was already set — most importantly inside the API container,
where it points at production — the safe default was silently skipped and the
suite dropped the live schema.

The protection was therefore absent precisely where it was needed, and looked
present on reading.

## Evidence

**2026-09-08**: running `pytest` inside `ghostwire-proxy-api` left the production
database with 2 of 45 tables:

```
$ psql -c "\dt"
 public | abuseipdb_blacklist | table
 public | alembic_version     | table
(2 rows)
```

Recovered from a verified `pg_dump` taken earlier the same day — 17 hosts, 7
locations, 17 certificates, 1 user, 33 WAF rules all restored intact, then
migrations 0005–0007 reapplied.

**2026-08-16**: the original purge left the same fingerprint — "all app tables
gone except `alembic_version`". No cause was ever established at the time. This
is almost certainly it.

## Root cause

A safety default that depends on the environment *not* already being configured.
The one environment with production credentials to hand is also the most
convenient place to run the suite, so the guard was bypassed by the normal way of
working rather than by an unusual mistake.

## Impact

- Total loss of all application data, recoverable only from backup.
- Silent: pytest reports ordinary failures, not "I have just deleted your
  database".
- Reproducible by anyone running the suite in the wrong shell.

## Fix (applied)

`conftest.py` no longer reads `DATABASE_URL` at all. The target comes from a
dedicated `TEST_DATABASE_URL`, and the suite refuses to start unless the database
name ends in `_test`:

```python
_target_db = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
if not _target_db.endswith("_test"):
    raise RuntimeError(f"Refusing to run the test suite against database {_target_db!r}. ...")
```

`DATABASE_URL` is then *overwritten* with the test URL so nothing under test can
reach the real database.

Verified: a production URL is refused, a `_test` URL is allowed.

## Still worth doing

- `conftest.py` contains the real Postgres password as a literal default, in a
  committed file. It should come from the environment.
- CI should run the suite against a disposable service container, so the only
  reachable database is a throwaway one.

# 01 — Renewed certificates never get deployed to nginx

**Severity:** Critical
**Status:** **Done** (2026-09-09) — see [README](README.md#done).
**Answers:** "on the certificate pages, many of them say expired, did they not self renew?"

## TL;DR

They *did* self-renew — but only on disk, inside the `ghostwire-proxy-certbot` container.
Nothing ever copies the renewed certificate into the location nginx actually reads from, so
nginx keeps serving the certificate from the original issuance ~90 days ago until it expires,
even though a fresh one has been sitting one directory over the whole time.

## Evidence

Comparing the certificate nginx serves (`data/certificates/<uuid>.crt`) against the
certificate certbot actually renewed (`data/letsencrypt/live/<domain>/cert.pem`) for the same
domain, as of 2026-08-16:

| Domain | Served by nginx expires | Actual Let's Encrypt cert expires |
|---|---|---|
| ghostwireproxy.err403.com | Aug 18 2026 (2 days) | **Oct 17 2026** |
| route-x.err403.com | Aug 18 2026 (2 days) | **Oct 17 2026** |
| homeassistant.err403.com | Aug 19 2026 (3 days) | **Oct 19 2026** |
| plex.err403.com | Aug 17 2026 (tomorrow) | **Oct 16 2026** |
| docs.err403.com | Aug 17 2026 (tomorrow) | **Oct 16 2026** |
| err403.com | Aug 17 2026 (tomorrow) | **Oct 16 2026** |
| wingman.err403.com | **Aug 14 2026 — already expired** | Oct 13 2026 |
| scooby.err403.com | **Jul 20 2026 — already expired** | Sep 18 2026 |
| dev.docs.err403.com | **Aug 1 2026 — already expired** | Aug 1 2026 (genuinely failing, see below) |
| pass.err403.com | **Jun 18 2026 — already expired** | Oct 15 2026 |
| ghostwire.proxy.err403.com | **Jun 18 2026 — already expired** | Jun 18 2026 (genuinely failing, see below) |

16 of 19 configured hosts are in this state — expired or expiring within days on the serving
side, while the underlying Let's Encrypt certificate is already renewed and valid through
September/October. Only `default.crt` (self-signed fallback) and `ai-reporting.err403.com`
(renewed Oct 13, close enough to its issuance date that it hasn't drifted noticeably yet) are
unaffected.

Two domains — `dev.docs.err403.com` and `ghostwire.proxy.err403.com` — are a separate,
genuine failure: `docker logs ghostwire-proxy-certbot` shows repeated
`Failed to renew certificate ... with error: Some challenges have failed.` for these two,
consistently, across every 12h renewal cycle. `ghostwire.proxy.err403.com` in particular looks
like a typo'd/orphaned host (the documented production domain is
`proxy.ghostwire.err403.com` — note the swapped label order) that no longer resolves or
routes correctly for HTTP-01 validation.

## Root cause

Two independent renewal paths exist and only one of them is wired up to the application:

1. **`ghostwire-proxy-certbot` container** (`docker-compose.yml:168-185`, `certbot/Dockerfile`)
   runs a bare loop:
   ```
   while :; do certbot renew --webroot -w /var/www/certbot --quiet; sleep 12h & wait $!; done
   ```
   This renews the PEM files under `data/letsencrypt/live/<domain>/` directly on the shared
   volume. It does **not** call any deploy hook — `data/letsencrypt/renewal-hooks/deploy/`
   is empty — so nothing downstream is notified. It also never touches the API, the database,
   or `data/certificates/`.

2. **The API's own renewal path** — `backend/app/services/certificate_service.py:117
   renew_certificate()` and `backend/app/api/routes/certificates.py:210
   process_certificate_renewal()` — is the *only* code that reads the renewed PEM, writes it
   into `data/certificates/<cert.id>.crt`/`.key` via `write_certificate_files()`,
   regenerates nginx vhost configs, and reloads nginx. This path is correct, but it is only
   ever invoked from the manual "Renew" button in the certificate UI
   (`certificates.py:217`). Confirmed by searching the whole backend: `renew_certificate` has
   exactly one caller, and it's a `POST` route handler — there is no scheduled job anywhere in
   `main.py` calling `check_expiring_certificates()` + `process_certificate_renewal()`
   automatically. (Compare to backups and update-checks, which do have their own
   `asyncio.sleep(...)` polling loops in `main.py`.)

So the two containers renew the same Let's Encrypt account/certs redundantly (the standalone
certbot loop makes the API's own `certbot renew --cert-name` call in `renew_certificate()`
mostly redundant too), and the one that actually deploys to nginx never runs on its own.

## Impact

- Sites intermittently serve expired TLS certificates to real visitors (browsers show hard
  interstitial warnings), for a project explicitly meant to be a reverse-proxy/TLS
  management tool.
- The admin UI's "auto renew" toggle on a certificate is misleading — it has no effect,
  because nothing schedules the renewal it's supposed to control.
- Every cert drifts out of sync a little more each 90-day cycle since the certbot container's
  clock and the (nonexistent) API renewal clock are unrelated.

## Recommended fix

Pick one of the two paths as authoritative — don't run both:

**Option A (minimal, recommended):** Keep the standalone certbot container for the actual
ACME renewal (it works fine and needs no code changes), but add a real deploy hook so it
finishes the job:
- Drop a script into `data/letsencrypt/renewal-hooks/deploy/` (certbot runs everything in
  that directory after a successful renewal, with `$RENEWED_LINEAGE`/`$RENEWED_DOMAINS` env
  vars set) that either:
  - calls a new small internal API endpoint (e.g. `POST /api/internal/certificates/deployed`)
    with the domain, so the API can copy the PEM into `data/certificates/`, update the DB
    row, regenerate configs, and reload nginx — reusing the existing
    `write_certificate_files()` / `generate_all_configs()` / `reload_nginx()` helpers already
    in `certificates.py:210-224`; or
  - directly `cp`s the renewed `fullchain.pem`/`privkey.pem` to
    `data/certificates/<uuid>.crt`/`.key` (the uuid would need to be looked up from the DB by
    domain) and touches a "reload requested" signal file the API/nginx watches.
- Fix the `ghostwire.proxy.err403.com` host (check whether it's an orphaned/misconfigured
  entry — the domain looks transposed relative to the real `proxy.ghostwire.err403.com`) and
  `dev.docs.err403.com`'s DNS/routing so HTTP-01 challenges stop failing outright.

**Option B:** Remove the standalone certbot container's independent renewal loop entirely and
add the missing scheduler loop to `main.py` (same pattern as the existing backup/update
loops) that periodically calls `check_expiring_certificates()` then
`process_certificate_renewal()` for anything due. This keeps a single source of truth but
means the certbot container becomes purely a `certbot`-binary-provider, invoked by the API via
subprocess as `renew_certificate()` already assumes.

Either way, also surface the drift as a health check: compare
`data/certificates/<id>.crt`'s actual `notAfter` against what the DB thinks `expires_at` is,
and flag a mismatch in the UI — that would have caught this immediately instead of it being
discovered by inspecting the container logs.

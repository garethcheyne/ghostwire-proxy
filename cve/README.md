# CVE advisories

Each file here records one vulnerability that can affect a Ghostwire Proxy install: which component and
versions, what configuration makes an install exposed, and which mitigation (if any) the app can apply
until a fixed version ships. The upgrade script checks every install against them on every run.

Files are data only. A manifest never contains commands: mitigations are named actions implemented in
code (below), so adding an advisory can't make the upgrader run something new.

## What the upgrader does with them

`upgradeGhostwireProxy.sh` reads the advisories **from the version it's upgrading to** (so a release that
adds an advisory is checked before it's installed), measures the running install, and evaluates them with
`scripts/ghostwire_cve.py`:

| Run | What happens |
|-----|--------------|
| `--check` | Reports each advisory's status, and what an upgrade would fix or apply. Changes nothing. |
| a normal run, already up to date | Reports, then applies or reverts mitigations (asks first; `--yes` doesn't). |
| a normal run that upgrades | Reports in Plan (including the status after the upgrade), then after the health check scans the new install and applies or reverts mitigations. |

Measured facts, from the running proxy container:

- `nginx` version: `openresty -v` (OpenResty `1.25.3.1` is nginx `1.25.3`); with the container down,
  the `FROM` line of `proxy/Dockerfile`. The target version comes from the target commit's Dockerfile.
- `nginx_config` text: `openresty -T`, the full effective config, every include and custom snippet.
- active mitigations: `GET /api/internal/cve/mitigations` on the API.

Anything that can't be measured makes the status `unknown`. It is never read as safe, and a mitigation is
never reverted on an unknown.

### Statuses

| Status | Meaning |
|--------|---------|
| `EXPOSED` | An affected version, and every exposure condition holds. |
| `unknown` | A fact the advisory needs couldn't be measured. |
| `mitigated` | An affected version, kept unexposed by a mitigation that's on. |
| `not exposed` | An affected version, but this install doesn't use the affected feature. Still upgrade. |
| `fixed` | The running version is outside the affected range. |

A mitigation is turned **on** when an advisory that lists it is exposed and the planned upgrade doesn't
fix it, and turned **off** once nothing it covers is affected any more (a fixed version is running).
An exposed advisory with no mitigation is reported (and sent to Telegram when notifications are on).

## Mitigations this app implements

| Name | Effect | Where |
|------|--------|-------|
| `disable_http2` | Every generated server block leaves out `http2 on;`, so HTTPS is HTTP/1.1. Hosts keep their HTTP/2 setting and get it back when it's turned off. Applied through the API's usual write, `nginx -t`, reload (or roll back) path. | `backend/app/services/cve_mitigation_service.py` |

To add one: give it a name in `MITIGATIONS` in that service, make config generation honour it, and add
the name to `CVE_MITIGATIONS` in the "This app" part of `upgradeGhostwireProxy.sh`.

## Adding an advisory

1. Copy the closest existing file to `cve/<CVE-ID>.json` (the file name must match `id`).
2. Fill it in from the vendor's advisory: `affects.fixed` is the first fixed version **on each branch**
   (`["1.30.7", "1.31.9"]`): a version is fixed when it's at or past the fix on its own branch, or newer
   than every fix. Leave `introduced` null if unsure: it only narrows the range.
3. Write `exposure` conditions narrowly enough that an install that doesn't use the feature reads
   `not exposed`, and broadly enough to catch custom snippets (they're in `openresty -T` too). When the
   preconditions aren't known, leave `exposure` empty: every affected install then reads `EXPOSED`.
4. List a mitigation only if it really removes an exposure condition, naming that condition in `removes`.
5. Check it:

   ```bash
   python3 scripts/ghostwire_cve.py validate cve
   ./upgradeGhostwireProxy.sh --check      # on an install: what it says about this one
   ```

   CI runs the validation (`backend/tests/test_cve_registry.py`), so an invalid file can't be merged.

When a fixed version ships, the release that bumps `proxy/Dockerfile` (and `BASE_IMAGES` in
`backend/app/services/update_service.py`) needs no change here: the advisory reads `fixed` from then on,
and the upgrader turns its mitigation off.

## Recorded

| Advisory | Component | Exposed when | Mitigation |
|----------|-----------|--------------|------------|
| CVE-2026-123007 (NGINX2Root) | nginx 1.9.5 → 1.30.6, 1.31.0 → 1.31.8 | HTTP/2 on | `disable_http2` |
| CVE-2026-123633 (NGINX2Root) | nginx, same | HTTP/2 on and proxying | `disable_http2` |
| CVE-2026-121810 (NGINX2Root) | nginx 1.25.0 on, same fixes | HTTP/3 on and proxying | none (Ghostwire has no HTTP/3) |
| CVE-2026-123634 (NGINX2Root) | nginx, same fixes | resolver and a variable `proxy_pass` | none: HTTP/2 off doesn't stop it |
| CVE-2026-113425 (NGINX2Root) | nginx, same fixes | mail proxy with `auth_http` | none (Ghostwire has no mail proxy) |

The NGINX2Root files were written on 19 Nov 2026 from secondary reporting (Tenable, Equixly, The Hacker
News, Astra); nginx.org's advisory wasn't reachable then. Check the affected ranges and severities against
nginx.org and F5 (K000163925, K000163931) and correct the files if they differ.

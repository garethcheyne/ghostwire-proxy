---
title: API Keys
excerpt: Scoped keys for scripts and AI agents
---

> Navigate to **Administration → Settings → API keys**.

API keys let scripts and AI agents call the Ghostwire Proxy API without a browser session. Each
key carries **scopes** that limit what it can do, and acts as the admin who created it.

## Creating a key

1. Turn on two-factor authentication for your account (Settings → Two-Factor Authentication).
   Creating a key requires a current code.
2. Click **New key**, give it a name you will recognise in the audit log, tick the scopes it needs,
   choose an expiry and enter your two-factor code.
3. Copy the key. **It is shown once.** Only a hash is stored, so a lost key cannot be recovered —
   revoke it and create another.

Keys look like `gwp_<prefix>_<secret>`. The prefix is shown in the key list so you can tell keys
apart; the secret never leaves the response that created it.

## Using a key

Send it as a Bearer token:

```bash
curl -H "Authorization: Bearer gwp_xxxxxxxxxx_..." https://proxy.example.com/api/proxy-hosts
```

## Scopes

| Scope | Allows |
|-------|--------|
| `read` | Reading proxy hosts, upstreams, certificates, access lists, auth walls, security rules, traffic, analytics, health and the audit log; dry-run config previews. **Every key has it.** |
| `write:proxy-hosts` | Creating, changing, enabling, disabling and deleting proxy hosts and their locations, including the load-balancing method and replacing the whole upstream list. |
| `write:upstreams` | Adding, changing, removing and health-checking individual upstream servers. |
| `write:certificates` | Requesting, uploading, renewing and deleting TLS certificates. |
| `write:access` | Changing access lists and auth walls. |
| `write:security` | Changing WAF rules and thresholds, threat-actor blocks, rate limits, GeoIP rules, known IPs, honeypot traps and security presets. |
| `write:nginx` | Running `nginx -t`, and regenerating/reloading the OpenResty config. |
| `admin` | Everything above plus settings, DNS providers, firewall connectors, alerts, reports, backups (list/create), system maintenance, and reading update/container status. |

### Never available to keys

Whatever its scopes, a key is refused on routes that could hand over the instance. These need a
signed-in admin in the UI:

- users and roles
- API keys themselves (a key cannot list, create or revoke keys)
- two-factor settings
- applying updates, rollbacks and update settings
- container auto-update actions
- backup restore, upload and download
- the kill switch

Any API route not explicitly mapped to a scope is also refused to keys (default deny).

## Security notes

- The key acts as the admin who created it. If that account is disabled or loses the admin role,
  the key stops working.
- Keys are compared in constant time; repeated invalid keys from one client are throttled
  (HTTP 429 for a few minutes).
- Every change made with a key is written to the audit log as `api_key_used`, naming the key,
  method and path, even if the change itself fails. Creating and revoking keys are audited too.
- **Last used** (time and client IP) is shown for each key.
- Revoking is immediate. Revoked keys stay in the list (greyed out) so the audit trail can still
  name them.
- Give keys an expiry and the narrowest scopes the job needs.

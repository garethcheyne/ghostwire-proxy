# 10 — Deploys don't gate on CI, and `COPY . .` ships the working tree

**Severity:** Medium
**Status:** **Partial** (2026-09-09) — `.dockerignore` done; CI gating, SHA stamping and deploy verification still open. See [README](README.md#partial).
**Answers:** "the admin UI filled with 'Server error' after a deploy"

## TL;DR

`.github/workflows/ci.yml` runs the right things — pytest, eslint, `tsc --noEmit`,
`npm run build`, and a Docker build per service. Nothing consults it before a
deploy. Deploys happen by running `docker compose build && up -d` on the host,
and both Dockerfiles use `COPY . .`, which ignores git status entirely.

So what reaches production is *the working tree of whoever ran the build*, not a
reviewed, tested commit.

## Evidence

Two incidents caused by exactly this:

**2026-08-16** — an unrelated rebuild shipped an uncommitted certificate-renewal
fix by accident. It happened to be a good change, and it renewed 16 certs on
container start. Nobody decided to deploy it.

**2026-09-08** — a `npm run build` run on the host (as a pre-deploy check) wrote
`frontend/.next/routes-manifest.json`, and there was no `.dockerignore`, so
`COPY . .` copied both that and a local `.env.local` into the build context. Next
resolves `next.config.ts` rewrites at *build* time for `output: 'standalone'`, so
`BACKEND_URL=http://localhost:8089` was baked into the image. Inside the
container that address is the container itself:

```
Failed to proxy http://localhost:8089/api/certificates/?limit=50
AggregateError: { code: 'ECONNREFUSED' }
```

Every `/api/*` call returned 500 and the admin UI filled with error toasts. The
container's own `BACKEND_URL` env was correct and never consulted.

## Root cause

There is no boundary between "my working copy" and "what runs in production". The
build context is the developer's directory, so any local artefact — a dev env
file, a stale `.next`, an experiment — is a potential production change.

## Impact

- Untested and unreviewed code can reach production without anyone intending it.
- Local-only configuration can silently override container configuration, in a
  way that no amount of checking the container's environment will reveal.
- CI's value is advisory only; a red build blocks nothing.

## Recommended fix

Partly done: `frontend/.dockerignore` now excludes `.env.local`, `.env.*.local`,
`.next`, `node_modules` and `.git`, so host artefacts can no longer enter the
image. `backend/.dockerignore` should get the same treatment.

Still open:

- Refuse to build from a dirty tree, or stamp the image with the commit SHA and
  surface it in the UI, so "what is running" is answerable.
- Make the deploy path run the CI checks first, or build from a clean checkout
  (`git archive HEAD`) rather than the working directory.
- Verify a UI deploy by the baked rewrite target, not the container env:
  `docker exec ghostwire-proxy-ui grep -o "http://[a-z0-9.:-]*" /app/.next/routes-manifest.json`
  must be `http://ghostwire-proxy-api:8000`.

# Contributing to Ghostwire Proxy

## Git Workflow

### Branching

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready code. Every commit should be deployable. |
| `develop` | Integration branch for features. Merges to `main` for releases. |
| `feat/*` | New features — branch from `develop` |
| `fix/*` | Bug fixes — branch from `develop` (or `main` for hotfixes) |
| `chore/*` | Maintenance, deps, CI — branch from `develop` |

```
main ─────●──────────●──────────●── releases (tagged)
           \        /            \
develop ────●──●──●──────●──●──●──── integration
              \    /       \  /
feat/xyz ──────●──●     fix/abc ──●
```

### Commit Messages

Plain English, like the rest of the history: a short summary line that says what changed for
someone running or reading the app, a blank line, then a body explaining why.

```
Auth-wall sign-in is limited per client address

Neither the password nor the TOTP step had a rate limit, so ...
```

### Pull Requests

1. Create a feature branch from `develop`
2. Make your changes with conventional commits
3. Push and open a PR against `develop`
4. CI runs automatically (tests, lint, build)
5. Get review, then merge (squash or merge commit)
6. For releases, `develop` is merged to `main` and tagged

### Hotfixes

For critical production fixes:
1. Branch from `main`: `git checkout -b fix/critical-bug main`
2. Fix, test, PR against `main`
3. After merge, cherry-pick or merge `main` back into `develop`

---

## Development Setup

```bash
# Clone
git clone https://github.com/garethcheyne/ghostwire-proxy.git
cd ghostwire-proxy

# Copy environment
cp .env.example .env
# Edit .env with your values

# Start everything
make up

# Check status
make status

# View logs
make logs
```

## Common Tasks

```bash
make help          # Show all available commands
make build         # Build all images
make deploy        # Build + restart app containers
make test          # Run backend tests
make lint          # Run frontend linting
make migrate       # Run database migrations
make backup        # Create a backup
make version       # Show current version
```

## Releasing

Releases are dated, like every Ghostwire app (`ghostwire-suite/CONVENTIONS.md`): `VERSION` holds
`YYYY.MM.DD.HHMM`. To release, change it and push to `main`; when every CI job passes, CI tags
`v<VERSION>` and publishes the GitHub release. Don't tag by hand.

```bash
make release        # writes the dated VERSION and commits it
git push origin main
```

## Upgrading a Running Instance

### Automatic (via Admin UI)
The updater sidecar handles updates triggered from the System page. It:
- Creates a backup
- Pulls the new version tag
- Rebuilds images
- Runs migrations
- Restarts containers in order
- Rolls back automatically on failure

### From the server
```bash
scripts/upgrade.sh                    # upgrade to the latest release
scripts/upgrade.sh v2026.10.01.1000   # go to a specific version
scripts/upgrade.sh --rollback         # back to what ran before
```
See "Upgrading" in the README.

---

## Project Structure

```
ghostwire-proxy/
├── backend/          Python FastAPI API server
├── frontend/         Next.js admin dashboard
├── frontend-authwall/  Auth wall login portal (Vite)
├── proxy/            OpenResty (nginx + Lua) reverse proxy
├── updater/          Self-update sidecar service
├── certbot/          Let's Encrypt certificate renewal
├── scripts/          Utility scripts
├── data/             Runtime data (gitignored)
├── .github/          CI/CD workflows
├── Makefile          Developer commands
├── VERSION           Current version number
└── docker-compose.yml
```

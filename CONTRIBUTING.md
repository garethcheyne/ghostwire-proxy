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

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

**Types:**
- `feat` — New feature
- `fix` — Bug fix
- `refactor` — Code change that neither fixes a bug nor adds a feature
- `perf` — Performance improvement
- `docs` — Documentation only
- `chore` — Build, CI, deps, tooling
- `test` — Adding or fixing tests

**Scopes:** `api`, `ui`, `proxy`, `lua`, `db`, `docker`, `ci`

**Examples:**
```
feat(api): add rate limiting per proxy host
fix(lua): wrap WAF regex in pcall to prevent crashes
chore(docker): pin postgres to 16.2-alpine
refactor(ui): split analytics page into tab components
docs: update README with upgrade instructions
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

```bash
# 1. Merge develop into main
git checkout main
git merge develop

# 2. Cut the release (updates VERSION, tags)
make release V=1.2.0

# 3. Push (triggers CI + GitHub Release)
git push origin main --tags

# 4. Merge main back to develop
git checkout develop
git merge main
git push origin develop
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

### Manual
```bash
./scripts/upgrade.sh           # Upgrade to latest tag
./scripts/upgrade.sh v1.2.0    # Upgrade to specific version
```

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

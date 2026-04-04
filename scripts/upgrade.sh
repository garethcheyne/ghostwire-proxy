#!/bin/bash
set -euo pipefail

# ─────────────────────────────────────────────
# Ghostwire Proxy - Manual Upgrade Script
#
# Usage:
#   ./scripts/upgrade.sh              # upgrade to latest
#   ./scripts/upgrade.sh v1.2.0       # upgrade to specific version
# ─────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/data/backups"
COMPOSE="docker compose"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${CYAN}[upgrade]${NC} $*"; }
ok()    { echo -e "${GREEN}[  ok  ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ warn ]${NC} $*"; }
err()   { echo -e "${RED}[error ]${NC} $*" >&2; }

CURRENT_VERSION=$(cat "$PROJECT_DIR/VERSION" 2>/dev/null || echo "unknown")
TARGET_VERSION="${1:-}"

# ─────────────────────────────────────────────
# 1. Determine target version
# ─────────────────────────────────────────────
cd "$PROJECT_DIR"

log "Current version: v$CURRENT_VERSION"

git fetch --tags --force --quiet

if [ -z "$TARGET_VERSION" ]; then
    TARGET_VERSION=$(git tag --sort=-v:refname | head -1)
    if [ -z "$TARGET_VERSION" ]; then
        err "No release tags found. Nothing to upgrade to."
        exit 1
    fi
fi

# Normalize tag format
[[ "$TARGET_VERSION" != v* ]] && TARGET_VERSION="v$TARGET_VERSION"
TARGET_SEMVER="${TARGET_VERSION#v}"

if [ "$TARGET_SEMVER" = "$CURRENT_VERSION" ]; then
    ok "Already on version $TARGET_VERSION. Nothing to do."
    exit 0
fi

log "Upgrading to: $TARGET_VERSION"
echo ""

# ─────────────────────────────────────────────
# 2. Pre-flight checks
# ─────────────────────────────────────────────
log "Running pre-flight checks..."

# Check all containers are running
RUNNING=$($COMPOSE ps --format '{{.Name}} {{.Status}}' 2>/dev/null | grep -c "Up" || true)
if [ "$RUNNING" -lt 4 ]; then
    warn "Not all containers are running ($RUNNING up). Continuing anyway..."
fi

# Check docker compose is available
if ! command -v docker &>/dev/null; then
    err "Docker is not installed."
    exit 1
fi

# Check git status
if [ -n "$(git status --porcelain)" ]; then
    warn "Working directory has uncommitted changes. They will be stashed."
fi

ok "Pre-flight checks passed"

# ─────────────────────────────────────────────
# 3. Create backup
# ─────────────────────────────────────────────
log "Creating pre-upgrade backup..."

mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/pre-upgrade-${CURRENT_VERSION}-$(date +%Y%m%d-%H%M%S).sql"

# Database backup via pg_dump in the postgres container
if docker exec ghostwire-proxy-postgres pg_dump -U "${POSTGRES_USER:-ghostwire}" "${POSTGRES_DB:-ghostwire_proxy}" > "$BACKUP_FILE" 2>/dev/null; then
    ok "Database backed up to: $BACKUP_FILE"
else
    warn "Database backup failed. Continuing without backup..."
    BACKUP_FILE=""
fi

# ─────────────────────────────────────────────
# 4. Pull new version
# ─────────────────────────────────────────────
log "Pulling version $TARGET_VERSION..."

git stash --quiet 2>/dev/null || true
git checkout "$TARGET_VERSION" --quiet

ok "Checked out $TARGET_VERSION"

# ─────────────────────────────────────────────
# 5. Build new images
# ─────────────────────────────────────────────
log "Building new container images..."

$COMPOSE build --parallel 2>&1 | tail -5

ok "Images built"

# ─────────────────────────────────────────────
# 6. Apply database migrations & restart services
# ─────────────────────────────────────────────
# Alembic migrations run automatically on container start via entrypoint.sh.
# Rebuilding and restarting handles everything: new code + new schema.
log "Restarting services (migrations run automatically on start)..."

$COMPOSE up -d --build ghostwire-proxy-api ghostwire-proxy-ui ghostwire-proxy-nginx ghostwire-proxy-updater

ok "Services restarted"

# ─────────────────────────────────────────────
# 7. Health check
# ─────────────────────────────────────────────
log "Waiting for services to become healthy..."

HEALTHY=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:8089/health >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 2
done

if [ "$HEALTHY" = true ]; then
    ok "All services healthy"
else
    err "Health check failed after 60 seconds!"
    echo ""
    warn "To rollback:"
    warn "  git checkout v$CURRENT_VERSION"
    warn "  $COMPOSE up -d --build"
    if [ -n "${BACKUP_FILE:-}" ]; then
        warn "  Restore DB: cat $BACKUP_FILE | docker exec -i ghostwire-proxy-postgres psql -U ghostwire ghostwire_proxy"
    fi
    exit 1
fi

# ─────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Upgrade complete: v$CURRENT_VERSION → $TARGET_VERSION  ${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  Dashboard: http://localhost:88"
echo "  API:       http://localhost:8089"
echo ""

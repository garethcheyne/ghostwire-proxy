#!/bin/bash
set -euo pipefail

# ─────────────────────────────────────────────
# Ghostwire Proxy - Manual Upgrade Script
#
# Usage:
#   ./scripts/upgrade.sh              # upgrade to latest
#   ./scripts/upgrade.sh v1.2.0       # upgrade to specific version
#   ./scripts/upgrade.sh --force      # rebuild current version (if containers are stale)
# ─────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/data/backups"
COMPOSE="docker compose"
FORCE=false
TARGET_VERSION=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force|-f) FORCE=true ;;
        *) TARGET_VERSION="$1" ;;
    esac
    shift
done

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

# ─────────────────────────────────────────────
# 1. Determine target version
# ─────────────────────────────────────────────
cd "$PROJECT_DIR"

log "Current version: v$CURRENT_VERSION"

# Ensure we're on the main branch (may be detached HEAD from old tag-based upgrades)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ "$CURRENT_BRANCH" != "main" ]; then
    warn "Not on main branch (currently: ${CURRENT_BRANCH:-detached HEAD}). Switching..."
    git checkout main --quiet 2>/dev/null || {
        err "Failed to checkout main branch"
        exit 1
    }
fi

if ! git fetch origin main 2>&1 | tail -5; then
    err "git fetch failed — check network or credentials"
    exit 1
fi

USE_CURRENT_BRANCH=false
if [ -z "$TARGET_VERSION" ]; then
    # Check the VERSION file on the remote main branch to determine latest release
    REMOTE_VERSION=$(git show origin/main:VERSION 2>/dev/null | tr -d '[:space:]')
    if [ -z "$REMOTE_VERSION" ]; then
        warn "Could not read VERSION from remote; using current branch"
        USE_CURRENT_BRANCH=true
    elif [ "$REMOTE_VERSION" = "$CURRENT_VERSION" ] && [ "$FORCE" = false ]; then
        ok "Already on version v$CURRENT_VERSION. Nothing to do."
        echo "  Use --force to rebuild containers without changing version."
        exit 0
    elif [ "$REMOTE_VERSION" = "$CURRENT_VERSION" ] && [ "$FORCE" = true ]; then
        TARGET_VERSION="v$CURRENT_VERSION"
    else
        TARGET_VERSION="v$REMOTE_VERSION"
    fi
fi

if [ "$USE_CURRENT_BRANCH" = false ]; then
    # Normalize tag format
    [[ "$TARGET_VERSION" != v* ]] && TARGET_VERSION="v$TARGET_VERSION"
    TARGET_SEMVER="${TARGET_VERSION#v}"

    if [ "$TARGET_SEMVER" = "$CURRENT_VERSION" ] && [ "$FORCE" = true ]; then
        log "Force-rebuilding version $TARGET_VERSION..."
    else
        log "Upgrading to: $TARGET_VERSION (current: v$CURRENT_VERSION)"
    fi
else
    TARGET_SEMVER="$CURRENT_VERSION"
    if [ "$FORCE" = true ]; then
        log "Force-rebuilding current branch at v$CURRENT_VERSION..."
    else
        log "Building current branch at v$CURRENT_VERSION..."
    fi
fi
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

# Read .env safely without shell-expanding values (passwords may contain $ characters)
if [ -f "$PROJECT_DIR/.env" ]; then
    while IFS='=' read -r key value; do
        # Skip comments and blank lines
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        # Strip quotes from value
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "$key=$value"
    done < "$PROJECT_DIR/.env"
fi

PG_USER="${POSTGRES_USER:-ghostwire}"
PG_DB="${POSTGRES_DB:-ghostwire_proxy}"
PG_PASS="${POSTGRES_PASSWORD:-}"

if [ -z "$PG_PASS" ]; then
    warn "POSTGRES_PASSWORD not found in .env — cannot create automated backup"
fi

log "Backing up database ($PG_DB as $PG_USER)..."
if docker exec -e PGPASSWORD="$PG_PASS" ghostwire-proxy-postgres pg_dump -U "$PG_USER" "$PG_DB" > "$BACKUP_FILE" 2>&1; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    ok "Database backed up to: $BACKUP_FILE ($BACKUP_SIZE)"
else
    err "Database backup failed:"
    cat "$BACKUP_FILE" 2>/dev/null  # show the error
    rm -f "$BACKUP_FILE"
    echo ""
    read -p "Continue upgrade WITHOUT backup? [y/N] " CONTINUE
    if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
        err "Upgrade aborted."
        exit 1
    fi
    BACKUP_FILE=""
fi

# ─────────────────────────────────────────────
# 4. Pull new version
# ─────────────────────────────────────────────
if [ "$USE_CURRENT_BRANCH" = false ]; then
    log "Pulling version $TARGET_VERSION..."

    git stash --quiet 2>/dev/null || true
    git pull --ff-only --quiet

    ok "Pulled latest (VERSION: $TARGET_SEMVER)"
else
    log "Using current branch commit"
fi

# ─────────────────────────────────────────────
# 5. Build new images
# ─────────────────────────────────────────────
log "Building new container images..."

# Export BUILD_VERSION so docker compose passes it as a build arg to the UI Dockerfile.
# This ensures each deployment gets a unique Next.js build ID, preventing stale
# server action errors when clients load cached JS from a previous build.
export BUILD_VERSION="$TARGET_SEMVER"

$COMPOSE build --parallel 2>&1 | tail -5

ok "Images built (BUILD_VERSION=$BUILD_VERSION)"

# ─────────────────────────────────────────────
# 6. Apply database migrations & restart services
# ─────────────────────────────────────────────
# Alembic migrations run automatically on container start via entrypoint.sh.
# Services are restarted in dependency order to avoid "Failed to find Server Action"
# errors caused by the UI starting before the API is healthy (stale client requests
# hit the new server before it has registered its action IDs).
log "Restarting services in dependency order..."

# Phase 1: Backend API (runs migrations on start)
log "  Phase 1: Restarting API..."
$COMPOSE up -d --build ghostwire-proxy-api

# Wait for API to become healthy before restarting frontend
API_HEALTHY=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:8089/health >/dev/null 2>&1; then
        API_HEALTHY=true
        break
    fi
    sleep 2
done

if [ "$API_HEALTHY" = true ]; then
    ok "  API is healthy"
else
    warn "  API health check timed out (60s) — continuing with UI restart"
fi

# Phase 2: Frontend UI (depends on API) + nginx + updater
log "  Phase 2: Restarting UI, nginx, updater..."
$COMPOSE up -d --build ghostwire-proxy-ui ghostwire-proxy-nginx ghostwire-proxy-updater

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
# 8. Purge old backups
# ─────────────────────────────────────────────
if [ -x "$SCRIPT_DIR/purge-backups.sh" ]; then
    log "Purging old backups (keeping last 5, removing >30 days)..."
    "$SCRIPT_DIR/purge-backups.sh" --run --days 30 --keep 5 || true
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

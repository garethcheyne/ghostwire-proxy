#!/bin/bash
# SQLite to PostgreSQL Migration Script
# Run this script to migrate data from SQLite to PostgreSQL

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=============================================="
echo "Ghostwire Proxy - SQLite to PostgreSQL Migration"
echo "=============================================="
echo ""

# Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Check required environment variables
if [ -z "$POSTGRES_PASSWORD" ]; then
    echo "ERROR: POSTGRES_PASSWORD is not set in .env"
    exit 1
fi

# Set defaults
POSTGRES_DB="${POSTGRES_DB:-ghostwire_proxy}"
POSTGRES_USER="${POSTGRES_USER:-ghostwire}"
SQLITE_PATH="${PROJECT_DIR}/data/sqlite/ghostwire-proxy.db"

echo "Configuration:"
echo "  SQLite: $SQLITE_PATH"
echo "  PostgreSQL: $POSTGRES_DB"
echo ""

# Check SQLite database exists
if [ ! -f "$SQLITE_PATH" ]; then
    echo "ERROR: SQLite database not found at $SQLITE_PATH"
    echo "Nothing to migrate."
    exit 1
fi

# Create backup of SQLite database
echo "Step 1: Creating backup of SQLite database..."
cp "$SQLITE_PATH" "${SQLITE_PATH}.backup"
echo "  Backup created: ${SQLITE_PATH}.backup"
echo ""

# Stop API container if running
echo "Step 2: Stopping API container..."
docker compose -f "$PROJECT_DIR/docker-compose.yml" stop ghostwire-proxy-api 2>/dev/null || true
echo ""

# Start PostgreSQL container
echo "Step 3: Starting PostgreSQL container..."
docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d ghostwire-proxy-postgres
echo "  Waiting for PostgreSQL to be healthy..."
sleep 10

# Check PostgreSQL is ready
for i in {1..30}; do
    if docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T ghostwire-proxy-postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /dev/null 2>&1; then
        echo "  PostgreSQL is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: PostgreSQL failed to start"
        exit 1
    fi
    sleep 2
done
echo ""

# Run migration in a temporary container
echo "Step 4: Running data migration..."
docker compose -f "$PROJECT_DIR/docker-compose.yml" run --rm \
    -v "$PROJECT_DIR/data/sqlite:/data/sqlite:ro" \
    -e SQLITE_PATH=/data/sqlite/ghostwire-proxy.db \
    -e POSTGRES_HOST=ghostwire-proxy-postgres \
    -e POSTGRES_PORT=5432 \
    -e POSTGRES_DB="$POSTGRES_DB" \
    -e POSTGRES_USER="$POSTGRES_USER" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    ghostwire-proxy-api python scripts/migrate_sqlite_to_postgres.py
echo ""

# Start all services
echo "Step 5: Starting all services..."
docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d
echo ""

echo "=============================================="
echo "Migration Complete!"
echo "=============================================="
echo ""
echo "Your data has been migrated to PostgreSQL."
echo "The SQLite backup is saved at: ${SQLITE_PATH}.backup"
echo ""
echo "Please verify the migration by checking the UI."
echo "Once verified, you can remove the SQLite files:"
echo "  rm -rf ${PROJECT_DIR}/data/sqlite"
echo ""

#!/bin/sh
# Ensure data directories are writable by appuser
# On fresh deploys, host-mounted volumes may be owned by root

for dir in /data/backups /data/backups/nginx-configs /data/certificates /data/nginx-configs /data/sqlite /data/geoip \
           /var/www/certbot /etc/letsencrypt /var/log/letsencrypt /var/lib/letsencrypt; do
    mkdir -p "$dir" 2>/dev/null || true
    if [ -d "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || chmod -R 777 "$dir" 2>/dev/null || true
    fi
done

# Allow appuser to access the Docker socket (for nginx test/reload via API)
# The socket is mounted :ro so chmod won't work — instead add appuser to the socket's group
if [ -S /var/run/docker.sock ]; then
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
    if [ -n "$DOCKER_GID" ] && [ "$DOCKER_GID" != "0" ]; then
        groupadd -g "$DOCKER_GID" dockersock 2>/dev/null || true
        usermod -aG "$DOCKER_GID" appuser 2>/dev/null || true
    else
        # Socket owned by root group — appuser needs direct access
        usermod -aG root appuser 2>/dev/null || true
    fi
fi

# Wait for PostgreSQL to be reachable before starting the app
DB_HOST=""
DB_PORT="5432"

if [ -n "$DATABASE_URL" ]; then
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9][0-9]*\)/.*|\1|p' | tail -1)
fi

DB_HOST=${DB_HOST:-ghostwire-proxy-postgres}
DB_PORT=${DB_PORT:-5432}

echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
retries=0
max_retries=30
while [ $retries -lt $max_retries ]; do
    if pg_isready -h "$DB_HOST" -p "$DB_PORT" -q 2>/dev/null; then
        echo "PostgreSQL is ready."
        break
    fi
    retries=$((retries + 1))
    echo "  Attempt ${retries}/${max_retries} - waiting 2s..."
    sleep 2
done

if [ $retries -eq $max_retries ]; then
    echo "WARNING: PostgreSQL not reachable after ${max_retries} attempts, starting anyway..."
fi

# Run Alembic migrations
echo "Running database migrations..."
cd /app
# After a rollback the database can be at a migration this (older) code doesn't know. Migrations
# are additive, so the older version runs fine on it; start without migrating in that case.
DB_STATE=$(gosu appuser python - <<'PY' 2>/dev/null
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from app.core.config import settings

known = {rev.revision for rev in ScriptDirectory.from_config(Config("alembic.ini")).walk_revisions()}
engine = create_engine(settings.sync_database_url)
with engine.connect() as conn:
    current = MigrationContext.configure(conn).get_current_heads()
print("newer" if any(head not in known for head in current) else "ok")
PY
)
if [ "$DB_STATE" = "newer" ]; then
    echo "WARNING: The database has migrations newer than this version (rolled back?). Starting without migrating."
    ALEMBIC_EXIT=0
else
    gosu appuser alembic upgrade head 2>&1
    ALEMBIC_EXIT=$?
fi
if [ $ALEMBIC_EXIT -eq 0 ]; then
    echo "Database migrations complete."
else
    # Don't start on a half-migrated database: admin sign-in, for one, depends on the migrations.
    # The container restarts and retries; scripts/upgrade.sh reports it and how to roll back.
    echo "ERROR: Alembic migration failed (exit $ALEMBIC_EXIT). Not starting the API."
    exit 1
fi

# Drop to appuser and exec the main command
exec gosu appuser "$@"

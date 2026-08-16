FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (postgresql-client for pg_dump/psql backup/restore).
# Pinned to -16 to match the postgres:16-alpine server in docker-compose.yml —
# Debian's default "postgresql-client" metapackage tracks whatever major version
# is current for the base image's release (17 as of this writing), and a pg_dump
# from a newer major version writes an archive format the server's own pg_restore
# can't read. Pulled from the official PGDG apt repo since Debian's default repos
# only carry one (the newest) major version.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client-16 \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user and directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data/sqlite /data/certificates /data/nginx-configs /data/backups /data/backups/nginx-configs \
             /data/geoip /var/www/certbot /etc/letsencrypt /var/log/letsencrypt /var/lib/letsencrypt && \
    chown -R appuser:appuser /app /data /var/www/certbot /etc/letsencrypt /var/log/letsencrypt /var/lib/letsencrypt

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint fixes permissions then drops to appuser
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]

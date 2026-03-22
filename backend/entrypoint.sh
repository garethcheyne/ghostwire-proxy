#!/bin/sh
# Ensure data directories are writable by appuser
# On fresh deploys, host-mounted volumes may be owned by root

for dir in /data/backups /data/certificates /data/nginx-configs /data/sqlite \
           /var/www/certbot /etc/letsencrypt /var/log/letsencrypt /var/lib/letsencrypt; do
    if [ -d "$dir" ] && [ ! -w "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || chmod -R 777 "$dir" 2>/dev/null || true
    fi
done

# Drop to appuser and exec the main command
exec gosu appuser "$@"

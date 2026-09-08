#!/bin/sh
# Start the log-rotation cron alongside nginx.
#
# Without this the access/error logs grow without bound; they are inside the
# container (not a mounted volume), so nothing else rotates them and they only
# ever reset when the container is recreated.
set -e

# Run logrotate hourly so the maxsize rule is enforced promptly rather than
# only at the daily boundary.
echo '0 * * * * /usr/sbin/logrotate /etc/logrotate.d/nginx --state /var/lib/logrotate.status' > /etc/crontabs/root
crond -b -l 8

exec "$@"

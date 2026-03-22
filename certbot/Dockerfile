FROM certbot/certbot:latest

# Create directories for certificates
RUN mkdir -p /etc/letsencrypt /var/www/certbot

# Volume for certificates
VOLUME ["/etc/letsencrypt", "/var/www/certbot"]

# Override entrypoint and keep container running
# Renewals triggered by API or runs every 12 hours
ENTRYPOINT []
CMD ["/bin/sh", "-c", "while true; do sleep 12h; certbot renew --webroot -w /var/www/certbot --quiet || true; done"]

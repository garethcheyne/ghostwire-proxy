FROM openresty/openresty:1.25.3.1-alpine

# Install additional packages
RUN apk add --no-cache \
    curl \
    openssl \
    libmaxminddb \
    libmaxminddb-dev \
    perl

# Install OpenResty packages using opm
RUN opm get ledgetech/lua-resty-http \
    && opm get SkyLothar/lua-resty-jwt \
    && opm get bungle/lua-resty-session \
    && opm get anjia0532/lua-resty-maxminddb

# Create directories
RUN mkdir -p /etc/nginx/conf.d/proxy-hosts \
    && mkdir -p /etc/nginx/certs \
    && mkdir -p /var/cache/nginx \
    && mkdir -p /var/log/nginx \
    && mkdir -p /usr/local/openresty/nginx/lua \
    && mkdir -p /data/geoip \
    && mkdir -p /var/www/auth-portal/default

# Copy configuration files
COPY nginx.conf /usr/local/openresty/nginx/conf/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/
COPY lua/ /usr/local/openresty/nginx/lua/

# Copy built auth portal themes (if available)
# These are built separately and copied in via docker-compose volume or build arg
COPY auth-portal/ /var/www/auth-portal/

# Set permissions
RUN chown -R nobody:nobody /var/cache/nginx /var/log/nginx /var/www/auth-portal

# Expose ports
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Run OpenResty
CMD ["openresty", "-g", "daemon off;"]

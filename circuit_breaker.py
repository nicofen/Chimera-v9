# deploy/nginx/chimera.conf
# Nginx reverse proxy for Project Chimera.
#
# Handles:
#   - HTTPS termination (port 443)
#   - HTTP → HTTPS redirect (port 80)
#   - WebSocket upgrade for /ws/state
#   - Rate limiting on REST endpoints
#   - Basic auth on the reset/trip endpoints (optional — see below)
#
# Prerequisites:
#   1. Obtain TLS certificate (see deploy guide — certbot / Let's Encrypt)
#   2. Place cert at deploy/nginx/ssl/chimera.crt
#      and key  at deploy/nginx/ssl/chimera.key
#   3. Set CHIMERA_DOMAIN in .env and replace YOUR_DOMAIN below

# Rate limiting zone — 30 req/min per IP on REST endpoints
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/m;

# ── HTTP → HTTPS redirect ─────────────────────────────────────────────────────
server {
    listen 80;
    server_name YOUR_DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;   # for Let's Encrypt renewal
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# ── HTTPS server ──────────────────────────────────────────────────────────────
server {
    listen 443 ssl http2;
    server_name YOUR_DOMAIN;

    # TLS
    ssl_certificate     /etc/nginx/ssl/chimera.crt;
    ssl_certificate_key /etc/nginx/ssl/chimera.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;

    # HSTS (enable once TLS is confirmed working)
    # add_header Strict-Transport-Security "max-age=63072000" always;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy no-referrer;

    # ── WebSocket — /ws/state ─────────────────────────────────────────────────
    location /ws/ {
        proxy_pass         http://chimera:8765;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;   # keep WS alive for up to 1 hour idle
        proxy_send_timeout 3600s;
    }

    # ── REST API — rate limited ───────────────────────────────────────────────
    location /api/ {
        limit_req zone=api_limit burst=10 nodelay;

        proxy_pass       http://chimera:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    # ── Protect reset/trip endpoints (uncomment to enable basic auth) ─────────
    # location ~ ^/api/breaker/(reset|trip) {
    #     auth_basic           "Operator access required";
    #     auth_basic_user_file /etc/nginx/ssl/.htpasswd;
    #     limit_req zone=api_limit burst=3 nodelay;
    #     proxy_pass http://chimera:8765;
    # }

    # ── Swagger docs (disable in production if preferred) ────────────────────
    location /docs {
        proxy_pass http://chimera:8765;
    }

    # ── Dashboard static files (if serving separately) ───────────────────────
    # location / {
    #     root /var/www/chimera_dashboard;
    #     try_files $uri $uri/ /index.html;
    # }

    access_log  /var/log/nginx/chimera_access.log;
    error_log   /var/log/nginx/chimera_error.log warn;
}

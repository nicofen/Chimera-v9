#!/usr/bin/env bash
# deploy/setup.sh
# ─────────────────────────────────────────────────────────────────────────────
# Project Chimera — VPS setup script
# Tested on Ubuntu 24.04 LTS (also works on 22.04).
#
# What this script does:
#   1. System hardening (UFW, fail2ban, SSH key-only auth)
#   2. Installs Docker + Docker Compose v2
#   3. Installs certbot for Let's Encrypt TLS
#   4. Creates a dedicated 'chimera' system user
#   5. Clones the Chimera repo and sets up secrets directory
#   6. Pulls the Docker image and starts the stack
#
# Usage (as root on a fresh VPS):
#   curl -fsSL https://raw.githubusercontent.com/your-org/chimera/main/deploy/setup.sh | bash
#   -- OR --
#   chmod +x deploy/setup.sh && sudo ./deploy/setup.sh
#
# Required env vars before running:
#   CHIMERA_REPO   — git repo URL (default: current directory)
#   CHIMERA_DOMAIN — your domain name for TLS (e.g. chimera.yourdomain.com)
#   CHIMERA_EMAIL  — email for Let's Encrypt notifications
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; BLU='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GRN}[setup]${NC} $*"; }
warn() { echo -e "${YLW}[setup]${NC} $*"; }
fail() { echo -e "${RED}[setup] FATAL:${NC} $*" >&2; exit 1; }
step() { echo -e "\n${BLU}══ $* ══${NC}"; }

[[ $EUID -ne 0 ]] && fail "Run as root: sudo $0"

CHIMERA_DOMAIN="${CHIMERA_DOMAIN:-}"
CHIMERA_EMAIL="${CHIMERA_EMAIL:-}"
CHIMERA_USER="chimera"
CHIMERA_HOME="/opt/chimera"
CHIMERA_REPO="${CHIMERA_REPO:-}"

# ── 1. System update ──────────────────────────────────────────────────────────
step "System update"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip jq \
    ufw fail2ban \
    python3.12 python3.12-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    ca-certificates gnupg lsb-release

# ── 2. System hardening ───────────────────────────────────────────────────────
step "Firewall (UFW)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP (certbot + redirect)'
ufw allow 443/tcp comment 'HTTPS'
# Do NOT expose 8765 directly — all traffic through nginx
ufw --force enable
log "UFW enabled. Open ports: 22, 80, 443"

step "fail2ban"
cat > /etc/fail2ban/jail.local << 'EOF2'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
filter  = sshd
logpath = /var/log/auth.log
EOF2
systemctl enable fail2ban --quiet
systemctl restart fail2ban
log "fail2ban configured"

step "SSH hardening"
SSHD_CONF="/etc/ssh/sshd_config"
# Disable password auth — key-only
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/'  "$SSHD_CONF"
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' "$SSHD_CONF"
sed -i 's/^#*X11Forwarding.*/X11Forwarding no/'                   "$SSHD_CONF"
grep -q "^MaxAuthTries" "$SSHD_CONF" || echo "MaxAuthTries 3" >> "$SSHD_CONF"
systemctl restart sshd
warn "SSH password auth DISABLED. Ensure your SSH key is installed first!"

# ── 3. Docker ────────────────────────────────────────────────────────────────
step "Docker"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker --quiet
    systemctl start docker
    log "Docker $(docker --version) installed"
else
    log "Docker already installed: $(docker --version)"
fi

# ── 4. Chimera user ───────────────────────────────────────────────────────────
step "Chimera system user"
if ! id "$CHIMERA_USER" &>/dev/null; then
    useradd -r -m -d "$CHIMERA_HOME" -s /bin/bash "$CHIMERA_USER"
    usermod -aG docker "$CHIMERA_USER"
    log "Created user '$CHIMERA_USER' at $CHIMERA_HOME"
else
    log "User '$CHIMERA_USER' already exists"
fi

mkdir -p "$CHIMERA_HOME"/{data,logs,deploy/nginx/ssl}
chown -R "$CHIMERA_USER:$CHIMERA_USER" "$CHIMERA_HOME"

# ── 5. Secrets directory ──────────────────────────────────────────────────────
step "Secrets"
SECRETS_DIR="/etc/chimera"
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

if [ ! -f "$SECRETS_DIR/env" ]; then
    cp "$CHIMERA_HOME/.env.example" "$SECRETS_DIR/env" 2>/dev/null || \
        touch "$SECRETS_DIR/env"
    chmod 600 "$SECRETS_DIR/env"
    chown root:root "$SECRETS_DIR/env"
    warn "Created $SECRETS_DIR/env — FILL IN YOUR SECRETS NOW:"
    warn "  nano $SECRETS_DIR/env"
else
    log "Secrets file already exists at $SECRETS_DIR/env"
fi

# Create symlink so docker-compose can find .env
ln -sf "$SECRETS_DIR/env" "$CHIMERA_HOME/.env"

# ── 6. TLS certificate ────────────────────────────────────────────────────────
step "TLS (Let's Encrypt)"
if [ -n "$CHIMERA_DOMAIN" ] && [ -n "$CHIMERA_EMAIL" ]; then
    # Stop nginx temporarily if running
    systemctl stop nginx 2>/dev/null || true
    certbot certonly \
        --standalone \
        --non-interactive \
        --agree-tos \
        --email "$CHIMERA_EMAIL" \
        -d "$CHIMERA_DOMAIN"
    # Copy certs to nginx ssl dir
    cp "/etc/letsencrypt/live/$CHIMERA_DOMAIN/fullchain.pem" \
        "$CHIMERA_HOME/deploy/nginx/ssl/chimera.crt"
    cp "/etc/letsencrypt/live/$CHIMERA_DOMAIN/privkey.pem"   \
        "$CHIMERA_HOME/deploy/nginx/ssl/chimera.key"
    chmod 600 "$CHIMERA_HOME/deploy/nginx/ssl/"*
    chown -R "$CHIMERA_USER:$CHIMERA_USER" "$CHIMERA_HOME/deploy/nginx/ssl/"
    log "TLS certificate obtained for $CHIMERA_DOMAIN"

    # Certbot auto-renewal
    systemctl enable certbot.timer --quiet 2>/dev/null || true
    log "Certbot auto-renewal enabled"
else
    warn "CHIMERA_DOMAIN / CHIMERA_EMAIL not set — skipping TLS"
    warn "Generate a self-signed cert for testing:"
    warn "  openssl req -x509 -nodes -days 365 -newkey rsa:4096 \\"
    warn "    -keyout $CHIMERA_HOME/deploy/nginx/ssl/chimera.key \\"
    warn "    -out    $CHIMERA_HOME/deploy/nginx/ssl/chimera.crt \\"
    warn "    -subj '/CN=localhost'"
fi

# ── 7. Update nginx config with domain ───────────────────────────────────────
if [ -n "$CHIMERA_DOMAIN" ]; then
    NGINX_CONF="$CHIMERA_HOME/deploy/nginx/chimera.conf"
    if [ -f "$NGINX_CONF" ]; then
        sed -i "s/YOUR_DOMAIN/$CHIMERA_DOMAIN/g" "$NGINX_CONF"
        log "Nginx config updated for $CHIMERA_DOMAIN"
    fi
fi

# ── 8. Pull and start ─────────────────────────────────────────────────────────
step "Build and start Chimera"
cd "$CHIMERA_HOME"
if [ -f "docker-compose.yml" ]; then
    docker compose build --no-cache
    docker compose up -d
    log "Chimera stack started"
    docker compose ps
else
    warn "docker-compose.yml not found — build manually:"
    warn "  cd $CHIMERA_HOME && docker compose up -d"
fi

# ── 9. Log rotation ───────────────────────────────────────────────────────────
cat > /etc/logrotate.d/chimera << 'EOF3'
/opt/chimera/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 640 chimera chimera
}
EOF3

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GRN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GRN}║   Project Chimera — VPS setup complete               ║${NC}"
echo -e "${GRN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Next steps:"
echo "  1. Fill in secrets:   nano /etc/chimera/env"
echo "  2. Check health:      curl http://localhost:8765/api/health"
echo "  3. Follow logs:       docker compose -f $CHIMERA_HOME/docker-compose.yml logs -f chimera"
echo ""
if [ -n "$CHIMERA_DOMAIN" ]; then
    echo "  Dashboard WS:  wss://$CHIMERA_DOMAIN/ws/state"
    echo "  API docs:      https://$CHIMERA_DOMAIN/docs"
fi
echo ""
warn "REMINDER: Start in CHIMERA_MODE=paper and validate for 90+ days before going live."

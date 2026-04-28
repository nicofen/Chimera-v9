# Project Chimera — Deployment Guide

This guide covers three deployment paths, ordered from simplest to most robust.

---

## Path 1 — Local development (no Docker)

For building, testing, and paper-trading on your own machine.

```bash
# Clone / extract the project
cd chimera/

# Create virtualenv and install dependencies
python3.12 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy and fill in secrets
cp .env.example .env
nano .env                      # set ALPACA_KEY, ALPACA_SECRET, OPENAI_API_KEY

# Start the mainframe
python -m chimera.mainframe

# Or use make
make dev-install
make dev-run
```

The dashboard runs at `ws://localhost:8765/ws/state` and `http://localhost:8765/docs`.

---

## Path 2 — Docker (single machine)

For a more production-like setup on your own server or a cloud VM,
without a custom domain or TLS.

```bash
# Build the image
docker build -t chimera:latest .

# Run with env-file
cp .env.example .env
# Fill in .env ...

docker run -d \
  --name chimera \
  --restart unless-stopped \
  --env-file .env \
  -p 8765:8765 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  chimera:latest

# Check health
curl http://localhost:8765/api/health

# Follow logs
docker logs -f chimera
```

---

## Path 3 — Docker Compose + nginx + TLS (production VPS)

Recommended for any deployment where you access Chimera remotely.
The WebSocket must be protected by TLS — browsers block unencrypted `ws://`
connections from HTTPS pages.

### Requirements
- A VPS with Ubuntu 22.04 or 24.04 (DigitalOcean, Linode, Hetzner, AWS EC2)
- A domain name pointed at the server's IP (`A` record)
- Root SSH access

### Option A — Automated setup script

```bash
export CHIMERA_DOMAIN=chimera.yourdomain.com
export CHIMERA_EMAIL=you@yourdomain.com
export CHIMERA_REPO=https://github.com/your-org/chimera.git

curl -fsSL https://raw.githubusercontent.com/your-org/chimera/main/deploy/setup.sh \
  | sudo bash
```

The script:
1. Updates the system and installs Docker, nginx, certbot, fail2ban
2. Hardens SSH (key-only, no root password login)
3. Configures UFW firewall (22, 80, 443 only — 8765 not exposed)
4. Creates a `chimera` system user
5. Obtains a Let's Encrypt TLS certificate
6. Starts the full `docker compose` stack

### Option B — Manual step-by-step

```bash
# 1. Provision a fresh Ubuntu 24.04 VPS (2+ vCPU, 4 GB RAM recommended)

# 2. SSH in and run the setup script, or follow manually:
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx

# 3. Clone the repository
sudo mkdir -p /opt/chimera
cd /opt/chimera
git clone https://github.com/your-org/chimera.git .

# 4. Secrets
sudo mkdir -p /etc/chimera
sudo cp .env.example /etc/chimera/env
sudo chmod 600 /etc/chimera/env
sudo nano /etc/chimera/env       # fill in all required values
sudo ln -sf /etc/chimera/env .env

# 5. TLS certificate
sudo certbot certonly --nginx -d chimera.yourdomain.com --email you@domain.com

# Copy certs for nginx container
sudo cp /etc/letsencrypt/live/chimera.yourdomain.com/fullchain.pem \
    deploy/nginx/ssl/chimera.crt
sudo cp /etc/letsencrypt/live/chimera.yourdomain.com/privkey.pem \
    deploy/nginx/ssl/chimera.key
sudo chmod 600 deploy/nginx/ssl/*

# 6. Update nginx config with your domain
sed -i 's/YOUR_DOMAIN/chimera.yourdomain.com/g' deploy/nginx/chimera.conf

# 7. Build and start
docker compose build
docker compose up -d

# 8. Verify
curl https://chimera.yourdomain.com/api/health
```

---

## Secrets management

### Development
Use a `.env` file (never committed — already in `.gitignore`).

### Production — option 1: encrypted env file
```bash
# Store secrets in /etc/chimera/env (root-owned, chmod 600)
sudo chmod 600 /etc/chimera/env
sudo chown root:root /etc/chimera/env
```

### Production — option 2: Docker secrets
```yaml
# docker-compose.yml addition:
secrets:
  alpaca_key:
    external: true   # created with: docker secret create alpaca_key <(echo -n "KEY")

services:
  chimera:
    secrets:
      - alpaca_key
```

### Production — option 3: HashiCorp Vault / AWS Secrets Manager
Use the Vault agent sidecar or AWS SSM Parameter Store and inject secrets
at container startup. The entrypoint script reads standard env vars regardless
of how they were injected.

---

## Monitoring

### Log access
```bash
# Docker
docker compose logs -f chimera
docker compose logs -f nginx

# systemd (bare-metal)
journalctl -u chimera -f

# Log files
tail -f /opt/chimera/logs/*.log
```

### Useful `make` shortcuts
```bash
make health           # GET /api/health
make breaker-status   # GET /api/breaker
make db-trades        # last 20 closed trades
make db-breaker       # circuit breaker event history
make breaker-reset NOTE="investigated ok"
```

### API endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Liveness + WS client count |
| `/api/summary` | GET | Today's P&L summary |
| `/api/trades?limit=50` | GET | Recent closed trades |
| `/api/positions` | GET | Open positions snapshot |
| `/api/signals?limit=20` | GET | Recent strategy signals |
| `/api/breaker` | GET | Circuit breaker status |
| `/api/breaker/reset` | POST | Re-arm breaker after investigation |
| `/api/breaker/trip` | POST | Emergency flatten (manual trip) |
| `/ws/state` | WS | Live state stream (4 Hz diffs) |
| `/docs` | GET | Interactive Swagger UI |

---

## TLS certificate renewal

Certbot auto-renews certificates via a systemd timer. To verify:
```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

After renewal, restart nginx to pick up the new cert:
```bash
docker compose restart nginx
```

Or add a post-renewal hook:
```bash
# /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
#!/bin/sh
cp /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem /opt/chimera/deploy/nginx/ssl/chimera.crt
cp /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem   /opt/chimera/deploy/nginx/ssl/chimera.key
cd /opt/chimera && docker compose restart nginx
```

---

## Switching from paper to live

**Do not rush this.** The recommended minimum is 90 days of paper trading
with consistent positive results across multiple market conditions.

Checklist before going live:
- [ ] 90+ days paper trading, positive net P&L
- [ ] Circuit breaker tested manually (fire `make breaker-trip`, verify flatten)
- [ ] Backtest results reviewed for the current market regime
- [ ] All API keys rotated to live Alpaca keys (new keys — not the paper keys)
- [ ] `CB_DAILY_LOSS_PCT` and `CB_DRAWDOWN_PCT` confirmed conservative
- [ ] A second person has reviewed the risk parameters
- [ ] You have a plan for what to do if the server goes down mid-position

When ready:
```bash
# In /etc/chimera/env:
CHIMERA_MODE=live
CHIMERA_LIVE_CONFIRMED=yes
ALPACA_KEY=your_LIVE_alpaca_key
ALPACA_SECRET=your_LIVE_alpaca_secret

docker compose restart chimera
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Container exits immediately | `docker compose logs chimera` — look for missing env var |
| WS connection refused | Nginx not running: `docker compose ps nginx` |
| `WS ERR` badge in dashboard | Check domain/port: should be `wss://domain/ws/state` not `ws://` |
| Circuit breaker trips on start | Equity not synced yet — wait 30s for Alpaca account sync |
| Stocktwits rate limit errors | Reduce `STOCKTWITS_MAX_RPH` in `.env` to 120 |
| `OPENAI_API_KEY` error in logs | NewsAgent requires a valid OpenAI key — check billing |

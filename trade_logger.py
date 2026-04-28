# deploy/chimera.service
# systemd unit file for Project Chimera.
# Use this for bare-metal / non-Docker deployments.
#
# Installation:
#   sudo cp deploy/chimera.service /etc/systemd/system/chimera.service
#   sudo systemctl daemon-reload
#   sudo systemctl enable chimera
#   sudo systemctl start chimera
#   sudo journalctl -u chimera -f       # follow logs
#
# The service runs as the dedicated 'chimera' user (created by setup.sh).
# Secrets are loaded from /etc/chimera/env (root-readable only).

[Unit]
Description=Project Chimera — Institutional Trading Mainframe
Documentation=https://github.com/your-org/chimera
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
User=chimera
Group=chimera
WorkingDirectory=/opt/chimera

# Load secrets from a root-owned env file (chmod 600, owned by root)
EnvironmentFile=/etc/chimera/env

# Activate the virtualenv and run the mainframe
ExecStart=/opt/chimera/.venv/bin/python -m chimera.mainframe

# Restart policy — restart on failure, not on clean exit
Restart=on-failure
RestartSec=15s

# Logging — captured by journald; also redirect to file
StandardOutput=journal
StandardError=journal
SyslogIdentifier=chimera

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/chimera/data /opt/chimera/logs
CapabilityBoundingSet=
AmbientCapabilities=

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=2G
CPUQuota=200%           # allow up to 2 CPU cores

# Kill signal — give mainframe 30s to clean up open positions
TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM
FinalKillSignal=SIGKILL

[Install]
WantedBy=multi-user.target

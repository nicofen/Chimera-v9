#!/bin/sh
# deploy/entrypoint.sh
# Container entrypoint — validates required env vars, then starts Chimera.
# Fails fast with a clear message rather than a cryptic Python traceback.

set -e

RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[0;33m'
NC='\033[0m'

log()  { echo "${GRN}[chimera]${NC} $*"; }
warn() { echo "${YLW}[chimera]${NC} $*"; }
fail() { echo "${RED}[chimera] ERROR:${NC} $*" >&2; exit 1; }

log "Project Chimera — starting up"
log "Mode: ${CHIMERA_MODE:-paper}"
log "API : ${CHIMERA_API_HOST:-0.0.0.0}:${CHIMERA_API_PORT:-8765}"

# ── Required secrets ──────────────────────────────────────────────────────────
REQUIRED="ALPACA_KEY ALPACA_SECRET OPENAI_API_KEY"
for var in $REQUIRED; do
    eval val=\$$var
    if [ -z "$val" ]; then
        fail "Required environment variable $var is not set."
    fi
    log "  $var ... OK"
done

# ── Optional secrets (warn but don't fail) ────────────────────────────────────
OPTIONAL="WHALE_ALERT_KEY CMC_API_KEY DUNE_API_KEY"
for var in $OPTIONAL; do
    eval val=\$$var
    if [ -z "$val" ]; then
        warn "  $var not set — related features will be disabled"
    fi
done

# ── Live mode safety gate ─────────────────────────────────────────────────────
if [ "${CHIMERA_MODE}" = "live" ]; then
    warn "╔══════════════════════════════════════════════╗"
    warn "║  LIVE MODE — REAL CAPITAL AT RISK            ║"
    warn "║  Ensure paper trading validated for 90+ days ║"
    warn "╚══════════════════════════════════════════════╝"
    if [ -z "${CHIMERA_LIVE_CONFIRMED}" ]; then
        fail "Set CHIMERA_LIVE_CONFIRMED=yes to acknowledge live mode risk."
    fi
fi

# ── Data directory ────────────────────────────────────────────────────────────
export CHIMERA_DB_PATH="${CHIMERA_DB_PATH:-/app/data/chimera_trades.db}"
export CHIMERA_CACHE_DIR="${CHIMERA_CACHE_DIR:-/app/data/cache}"
mkdir -p "${CHIMERA_CACHE_DIR}"

log "DB  : ${CHIMERA_DB_PATH}"
log "Logs: /app/logs"

# ── Start mainframe ───────────────────────────────────────────────────────────
log "Starting mainframe..."
exec python -m chimera.mainframe "$@"

# ── Project Chimera — Dockerfile ─────────────────────────────────────────────
#
# Multi-stage build:
#   Stage 1 (builder): installs all Python dependencies into a venv
#   Stage 2 (runtime): copies only the venv + source, no build tools
#
# This keeps the final image lean (~350 MB) and ensures no pip/gcc
# artifacts ship to production.
#
# Usage:
#   docker build -t chimera:latest .
#   docker run --env-file .env -p 8765:8765 chimera:latest
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed only at build time
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libssl-dev libffi-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# Create isolated venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install requirements first (layer-cached until requirements change)
COPY requirements.txt .
RUN pip install --upgrade pip wheel \
    && pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN groupadd -r chimera && useradd -r -g chimera -d /app -s /sbin/nologin chimera

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY --chown=chimera:chimera . /app/chimera
COPY --chown=chimera:chimera deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Data directories (mounted as volumes in production)
RUN mkdir -p /app/data /app/logs && chown -R chimera:chimera /app/data /app/logs

# Switch to non-root
USER chimera

# Environment defaults (override via --env-file or -e)
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    CHIMERA_MODE=paper \
    CHIMERA_API_HOST=0.0.0.0 \
    CHIMERA_API_PORT=8765 \
    TZ=UTC

# Health check — polls the /api/health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fs http://localhost:${CHIMERA_API_PORT}/api/health || exit 1

EXPOSE 8765

ENTRYPOINT ["/app/entrypoint.sh"]

#!/bin/bash
# OpenClaw Gateway 启动脚本
export OPENCLAW_STATE_DIR="/Users/blackdj/Desktop/OpenClaw Bot/.openclaw"
export OPENCLAW_CONFIG_PATH="/Users/blackdj/Desktop/OpenClaw Bot/.openclaw/openclaw.json"
export OPENCLAW_GATEWAY_PORT="18789"
export OPENCLAW_GATEWAY_TOKEN="openclaw-manager-local-token"
export OPENCLAW_LAUNCHD_LABEL="ai.openclaw.gateway"
export OPENCLAW_SERVICE_MARKER="openclaw"
export OPENCLAW_SERVICE_KIND="gateway"
export OPENCLAW_SERVICE_VERSION="2026.3.2"
export NODE_EXTRA_CA_CERTS="/etc/ssl/cert.pem"
export NODE_USE_SYSTEM_CA="1"
export NO_PROXY="127.0.0.1,localhost,::1"
export no_proxy="127.0.0.1,localhost,::1"
exec /opt/homebrew/opt/node/bin/node \
    /Users/blackdj/.npm-global/lib/node_modules/openclaw/dist/index.js \
    gateway --port 18789

#!/bin/bash
# OpenClaw Gateway 启动脚本
export OPENCLAW_STATE_DIR="/Users/blackdj/Desktop/OpenEverything/.openclaw"
export OPENCLAW_CONFIG_PATH="/Users/blackdj/Desktop/OpenEverything/.openclaw/openclaw.json"
export OPENCLAW_GATEWAY_PORT="18789"
# 安全加固(HI-590): 从配置文件读取 token，不在脚本中硬编码弱默认值
# 生成方法: openssl rand -hex 32 > ~/.openclaw/gateway_token
export OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-$(cat ~/.openclaw/gateway_token 2>/dev/null || echo '')}"
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

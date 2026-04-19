#!/bin/bash
# Kiro Gateway 启动脚本 — 解决 launchd 直接调用 Python 时的 EX_CONFIG 问题
cd "/Users/blackdj/Desktop/OpenEverything/packages/clawbot/kiro-gateway"
exec "/Users/blackdj/Desktop/OpenEverything/packages/clawbot/kiro-gateway/.venv/bin/python" \
    "/Users/blackdj/Desktop/OpenEverything/packages/clawbot/kiro-gateway/main.py" \
    --host 127.0.0.1 --port 18793

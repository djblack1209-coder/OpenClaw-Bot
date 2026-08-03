#!/bin/bash
# g4f 免费模型代理启动脚本
PYTHON="/Users/blackdj/Desktop/OpenEverything/packages/clawbot/browser-agent/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "g4f disabled: reproducible runtime is not installed"
    exit 0
fi
cd "/Users/blackdj/Desktop/OpenEverything/packages/clawbot/browser-agent"
exec "$PYTHON" \
    -m g4f api --port 18891 --g4f-api-key dummy --no-gui

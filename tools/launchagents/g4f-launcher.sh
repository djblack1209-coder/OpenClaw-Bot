#!/bin/bash
# g4f 免费模型代理启动脚本
cd "/Users/blackdj/Desktop/OpenEverything/packages/clawbot/browser-agent"
exec "/Users/blackdj/Desktop/OpenEverything/packages/clawbot/browser-agent/.venv/bin/python" \
    -m g4f api --port 18891 --g4f-api-key dummy --no-gui

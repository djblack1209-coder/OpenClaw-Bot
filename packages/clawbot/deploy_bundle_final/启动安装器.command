#!/bin/bash
cd "$(dirname "$0")"
echo ""
echo "  ========================================"
echo "       OpenClaw 一键部署器"
echo "  ========================================"
echo ""

if ! command -v python3 &>/dev/null; then
    echo "  [!] 未检测到 Python3"
    echo "  macOS: brew install python3"
    echo "  Linux: sudo apt install python3 python3-pip"
    exit 1
fi

pip3 install -q flask 2>/dev/null
echo "  启动中，浏览器将自动打开..."
python3 web_installer.py

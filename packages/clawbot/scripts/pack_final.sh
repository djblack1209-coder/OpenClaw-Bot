#!/bin/bash
# 打包 OpenClaw 一键部署包 v3 - 离线验证 + Web安装器 + 教程
set -e
cd "$(dirname "$0")/.."

BUNDLE="deploy_bundle_final"
OUTPUT="OpenClaw_Deploy_v2026.3.zip"

echo "📦 打包 OpenClaw 一键部署包 (最终版)..."
rm -rf "$BUNDLE" "$OUTPUT"
mkdir -p "$BUNDLE"

# 1. Web安装器（核心）
cp src/deployer/web_installer.py "$BUNDLE/"

# 2. 依赖
cat > "$BUNDLE/requirements.txt" << 'EOF'
flask>=3.0.0
EOF

# 3. Windows 启动脚本
cat > "$BUNDLE/启动安装器.bat" << 'BATEOF'
@echo off
chcp 65001 >nul
echo.
echo  ========================================
echo       OpenClaw 一键部署器
echo  ========================================
echo.
echo  正在准备环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] 未检测到 Python
    echo  请先安装 Python 3.8+
    echo  下载: https://www.python.org/downloads/
    echo  安装时务必勾选 "Add to PATH"
    echo.
    pause
    exit /b 1
)
pip install -q flask 2>nul
echo  启动中，浏览器将自动打开...
python web_installer.py
pause
BATEOF

# 4. macOS/Linux 启动脚本
cat > "$BUNDLE/启动安装器.command" << 'SHEOF'
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
SHEOF
chmod +x "$BUNDLE/启动安装器.command"

# 5. 使用说明
cat > "$BUNDLE/使用说明.txt" << 'EOF'
OpenClaw 一键部署包
====================

【Windows 用户】
  双击 "启动安装器.bat"

【macOS 用户】
  双击 "启动安装器.command"
  (如果提示无法打开，右键 → 打开)

【Linux 用户】
  终端执行: bash 启动安装器.command

【部署流程】(全程浏览器操作)
  1. 输入激活码 (购买后自动收到)
  2. 输入 Telegram Bot Token
     (在Telegram搜索 @BotFather → /newbot → 复制Token)
  3. 选择AI模型方案:
     - 免费模型: 直接能用，不花钱
     - 自有API: 填URL和Key即可
  4. 点击部署，等待完成
  5. 去Telegram找你的Bot发 /start

【注意事项】
  - 需要先安装 Python 3.8+ 和 Node.js 18+
  - Windows安装Python时务必勾选 "Add to PATH"
  - Node.js下载: https://nodejs.org/

【售后】
  7天内有问题随时联系卖家
====================
EOF

# 6. 打包
cd "$BUNDLE"
zip -q -r "../$OUTPUT" .
cd ..

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo ""
echo "✅ 打包完成: $OUTPUT ($SIZE)"
echo ""
echo "📤 请上传到百度网盘替换旧文件"

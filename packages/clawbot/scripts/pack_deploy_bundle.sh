#!/bin/bash
# 打包 OpenClaw 一键部署包 - 生成可分发的安装包

set -e
cd "$(dirname "$0")/.."

BUNDLE_DIR="deploy_bundle"
VERSION="2026.3"
OUTPUT="OpenClaw_Deploy_v${VERSION}.zip"

echo "📦 打包 OpenClaw 一键部署包..."

# 清理旧文件
rm -rf "$BUNDLE_DIR" "$OUTPUT"
mkdir -p "$BUNDLE_DIR"

# 1. 复制部署客户端
echo "[1/4] 复制部署客户端..."
cp src/deployer/deploy_client.py "$BUNDLE_DIR/"

# 2. 创建 requirements.txt
echo "[2/4] 生成依赖列表..."
cat > "$BUNDLE_DIR/requirements.txt" << EOF
requests>=2.31.0
EOF

# 3. 创建启动脚本
echo "[3/4] 创建启动脚本..."

# Windows 启动脚本
cat > "$BUNDLE_DIR/一键部署.bat" << 'EOF'
@echo off
chcp 65001 >nul
echo ========================================
echo   OpenClaw 一键部署工具
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/2] 安装依赖...
pip install -q -r requirements.txt

echo [2/2] 启动部署向导...
python deploy_client.py
pause
EOF

# macOS/Linux 启动脚本
cat > "$BUNDLE_DIR/一键部署.sh" << 'EOF'
#!/bin/bash
echo "========================================"
echo "  OpenClaw 一键部署工具"
echo "========================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python3，请先安装"
    exit 1
fi

echo "[1/2] 安装依赖..."
pip3 install -q -r requirements.txt

echo "[2/2] 启动部署向导..."
python3 deploy_client.py
EOF

chmod +x "$BUNDLE_DIR/一键部署.sh"

# 4. 创建 README
cat > "$BUNDLE_DIR/README.txt" << EOF
OpenClaw 一键部署包 v${VERSION}
================================

使用说明:

Windows 用户:
  双击运行 "一键部署.bat"

macOS/Linux 用户:
  终端执行: bash 一键部署.sh

部署流程:
  1. 输入 License Key (购买后获得)
  2. 选择 AI 模型方案 (付费API/免费模型/本地模型)
  3. 配置 Telegram Bot Token (可选)
  4. 自动安装 OpenClaw 及依赖
  5. 验证安装并生成健康报告

售后支持:
  - 7天内有问题随时联系卖家
  - Telegram: @your_support_bot
  - 邮箱: support@openclaw.ai

================================
EOF

# 5. 打包
echo "[4/4] 压缩打包..."
cd "$BUNDLE_DIR"
zip -q -r "../$OUTPUT" .
cd ..

echo ""
echo "✅ 打包完成: $OUTPUT"
echo "📦 大小: $(du -h "$OUTPUT" | cut -f1)"
echo ""
echo "📤 下一步: 上传到百度网盘，更新 .env 中的 BAIDU_PAN_LINK"

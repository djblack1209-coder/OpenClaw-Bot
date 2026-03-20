#!/bin/bash
# 重新打包 - 包含Web安装器

set -e
cd "$(dirname "$0")/.."

BUNDLE_DIR="deploy_bundle_v2"
OUTPUT="OpenClaw_WebInstaller_v2026.3.zip"

echo "📦 打包Web安装器..."

rm -rf "$BUNDLE_DIR" "$OUTPUT"
mkdir -p "$BUNDLE_DIR"

# 复制Web安装器
cp src/deployer/web_installer.py "$BUNDLE_DIR/"
cp src/deployer/auto_download.py "$BUNDLE_DIR/"

# 创建requirements
cat > "$BUNDLE_DIR/requirements.txt" << EOF
flask>=3.0.0
requests>=2.31.0
EOF

# Windows启动脚本
cat > "$BUNDLE_DIR/启动安装器.bat" << 'EOF'
@echo off
chcp 65001 >nul
echo ========================================
echo   OpenClaw Web安装器
echo ========================================
pip install -q -r requirements.txt
start http://localhost:18899
python web_installer.py
pause
EOF

# macOS/Linux启动脚本
cat > "$BUNDLE_DIR/启动安装器.sh" << 'EOF'
#!/bin/bash
echo "========================================"
echo "  OpenClaw Web安装器"
echo "========================================"
pip3 install -q -r requirements.txt
open http://localhost:18899 2>/dev/null || xdg-open http://localhost:18899 2>/dev/null &
python3 web_installer.py
EOF

chmod +x "$BUNDLE_DIR/启动安装器.sh"

# README
cat > "$BUNDLE_DIR/README.txt" << EOF
OpenClaw Web安装器 v2026.3
================================

使用说明:

1. Windows: 双击 "启动安装器.bat"
2. macOS/Linux: 双击 "启动安装器.sh"
3. 浏览器自动打开，输入License Key即可

完全自动化，无需任何技术基础！

================================
EOF

cd "$BUNDLE_DIR"
zip -q -r "../$OUTPUT" .
cd ..

echo ""
echo "✅ 打包完成: $OUTPUT"
echo "📦 大小: $(du -h "$OUTPUT" | cut -f1)"

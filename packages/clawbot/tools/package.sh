#!/bin/bash
# OpenClaw 一键部署器打包脚本

set -e

echo "🦞 OpenClaw 部署器打包工具 v4.0"
echo "================================"

# 项目根目录
PROJECT_ROOT="/Users/blackdj/Desktop/OpenEverything/packages/clawbot"
DIST_DIR="$PROJECT_ROOT/dist"
PACKAGE_NAME="OpenClaw-Installer-v4.0"

# 清理旧文件
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR/$PACKAGE_NAME"

echo "📦 复制文件..."

# 复制核心文件
cp "$PROJECT_ROOT/src/deployer/web_installer.py" "$DIST_DIR/$PACKAGE_NAME/"
cp "$PROJECT_ROOT/src/deployer/license_manager.py" "$DIST_DIR/$PACKAGE_NAME/"
mkdir -p "$DIST_DIR/$PACKAGE_NAME/docs"
cp "$PROJECT_ROOT/docs/agents.md" "$DIST_DIR/$PACKAGE_NAME/docs/"
cp "$PROJECT_ROOT/docs/quick-start-guide.md" "$DIST_DIR/$PACKAGE_NAME/docs/"
cp "$PROJECT_ROOT/docs/product-copy.txt" "$DIST_DIR/$PACKAGE_NAME/docs/"

# 创建启动脚本
cat > "$DIST_DIR/$PACKAGE_NAME/启动安装器.command" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
python3 web_installer.py
EOF
chmod +x "$DIST_DIR/$PACKAGE_NAME/启动安装器.command"

cat > "$DIST_DIR/$PACKAGE_NAME/启动安装器.bat" << 'EOF'
@echo off
cd /d "%~dp0"
python web_installer.py
pause
EOF

cat > "$DIST_DIR/$PACKAGE_NAME/退款销毁.command" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
python3 web_installer.py --destroy
EOF
chmod +x "$DIST_DIR/$PACKAGE_NAME/退款销毁.command"

cat > "$DIST_DIR/$PACKAGE_NAME/退款销毁.bat" << 'EOF'
@echo off
cd /d "%~dp0"
python web_installer.py --destroy
pause
EOF

# 创建README
cat > "$DIST_DIR/$PACKAGE_NAME/README.txt" << 'EOF'
🦞 OpenClaw 龙虾AI助手 - 一键部署器 v4.0
========================================

【使用方法】
1. Windows用户：双击 "启动安装器.bat"
2. Mac/Linux用户：双击 "启动安装器.command"
3. 浏览器会自动打开，输入激活码即可部署

【系统要求】
- Node.js >= 22（安装教程见"docs/quick-start-guide.md"）
- Python 3.7+（系统自带）
- 网络连接

【部署内容】
✅ OpenClaw 核心（GitHub 315k⭐）
✅ 三省六部 AGENTS.md 智能架构
✅ Manager UI 桌面应用（下载链接）
✅ 5个热门 Skills（playwright/pdf/doc/deploy）
✅ ClawHub CLI 技能市场
✅ MCP 服务（Context7 + GitHub Grep）

【免费模型教程】
详见 "docs/quick-start-guide.md"，包含：
- DeepSeek（新用户送¥10）
- 硅基流动（免费模型）
- OpenRouter（免费模型）
- 本地Ollama（完全离线）

【退款说明】
如需退款，运行 "退款销毁" 脚本，会自动删除已部署内容。

【售后支持】
7天内有问题随时联系卖家
EOF

echo "🗜️  压缩打包..."
cd "$DIST_DIR"
zip -r "$PACKAGE_NAME.zip" "$PACKAGE_NAME"

echo "✅ 打包完成！"
echo "📍 位置: $DIST_DIR/$PACKAGE_NAME.zip"
echo ""
echo "📤 下一步："
echo "1. 上传到百度网盘"
echo "2. 获取分享链接"
echo "3. 更新 config/.env 中的 BAIDU_PAN_LINK"

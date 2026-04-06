#!/bin/bash
# ═══════════════════════════════════════════════════
# mitmproxy CA 证书一键安装脚本
#
# 把 mitmproxy 的证书导入 macOS 钥匙串并设为信任，
# 这样微信的小程序流量才能被代理拦截到 token。
#
# 用法: bash scripts/install_mitm_cert.sh
# ═══════════════════════════════════════════════════

set -e

CERT="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"
CERT_NAME="mitmproxy"

echo "🔧 mitmproxy CA 证书安装工具"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查证书文件是否存在
if [ ! -f "$CERT" ]; then
    echo "⚠️  证书文件不存在: $CERT"
    echo "   正在启动 mitmdump 自动生成..."
    
    # 找到项目 venv 里的 mitmdump
    MITM_BIN="$(dirname "$0")/../packages/clawbot/.venv312/bin/mitmdump"
    if [ ! -f "$MITM_BIN" ]; then
        MITM_BIN="$(which mitmdump 2>/dev/null || true)"
    fi
    
    if [ -z "$MITM_BIN" ] || [ ! -f "$MITM_BIN" ]; then
        echo "❌ 找不到 mitmdump，请先运行: pip install mitmproxy"
        exit 1
    fi

    "$MITM_BIN" -p 18999 --set block_global=false &
    MITM_PID=$!
    sleep 3
    kill $MITM_PID 2>/dev/null || true
    wait $MITM_PID 2>/dev/null || true
    
    if [ ! -f "$CERT" ]; then
        echo "❌ 证书生成失败"
        exit 1
    fi
    echo "✅ 证书已生成"
    echo ""
fi

echo "📜 证书文件: $CERT"
echo ""

# 检查是否已安装
if security find-certificate -c "$CERT_NAME" /Library/Keychains/System.keychain >/dev/null 2>&1; then
    echo "ℹ️  证书已在系统钥匙串中，跳过导入"
else
    echo "📥 正在导入证书到系统钥匙串..."
    echo "   （会弹出密码输入框，输入你的 Mac 登录密码）"
    echo ""
    
    sudo security add-trusted-cert \
        -d \
        -r trustRoot \
        -k /Library/Keychains/System.keychain \
        "$CERT"
    
    echo ""
    echo "✅ 证书已导入并设为信任"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 完成！现在领券功能可以正常使用了"
echo ""
echo "💡 小贴士:"
echo "   - 在 Bot 里说「领券」或发 /coupon 即可手动领取"
echo "   - 如需每天自动领取，在 config/.env 里加一行: COUPON_ENABLED=1"
echo ""

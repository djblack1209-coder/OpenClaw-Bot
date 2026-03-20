#!/usr/bin/env python3
"""OpenClaw 全功能链路检测"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

print("🔍 OpenClaw 全功能链路检测")
print("=" * 60)

# 1. 环境检查
print("\n[1/8] 环境检查...")
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, 'config', '.env'))
    print("✅ 配置文件加载成功")
except Exception as e:
    print(f"❌ 配置加载失败: {e}")
    sys.exit(1)

# 2. 闲鱼客服
print("\n[2/8] 闲鱼客服连接...")
try:
    cookies = os.getenv('XIANYU_COOKIES', '')
    if '_m_h5_tk=' in cookies and '_tb_token_=' in cookies:
        print(f"✅ Cookie 已配置 (长度: {len(cookies)})")
    else:
        print("⚠️ Cookie 缺少关键字段")
except Exception as e:
    print(f"❌ 闲鱼配置检查失败: {e}")

# 3. Telegram Bot
print("\n[3/8] Telegram Bot 配置...")
try:
    tokens = [
        ('Qwen235B', os.getenv('QWEN235B_TOKEN')),
        ('GPT-OSS', os.getenv('GPTOSS_TOKEN')),
        ('Claude Sonnet', os.getenv('CLAUDE_SONNET_TOKEN')),
    ]
    for name, token in tokens:
        if token:
            print(f"✅ {name}: {token[:10]}...")
        else:
            print(f"⚠️ {name}: 未配置")
except Exception as e:
    print(f"❌ Telegram 配置检查失败: {e}")

# 4. LLM API
print("\n[4/8] LLM API 配置...")
try:
    apis = [
        ('硅基流动', os.getenv('SILICONFLOW_KEYS')),
        ('Claude代理', os.getenv('CLAUDE_API_KEY')),
        ('Kiro Gateway', os.getenv('KIRO_BASE_URL')),
    ]
    for name, val in apis:
        if val:
            print(f"✅ {name}: 已配置")
        else:
            print(f"⚠️ {name}: 未配置")
except Exception as e:
    print(f"❌ LLM 配置检查失败: {e}")

# 5. 百度网盘
print("\n[5/8] 百度网盘自动交付...")
try:
    link = os.getenv('BAIDU_PAN_LINK')
    code = os.getenv('BAIDU_PAN_CODE')
    if link and code:
        print(f"✅ 网盘链接: {link[:50]}...")
        print(f"✅ 提取码: {code}")
    else:
        print("⚠️ 网盘配置缺失")
except Exception as e:
    print(f"❌ 网盘配置检查失败: {e}")

# 6. IBKR 交易
print("\n[6/8] IBKR 交易配置...")
try:
    host = os.getenv('IBKR_HOST')
    port = os.getenv('IBKR_PORT')
    account = os.getenv('IBKR_ACCOUNT')
    if host and port and account:
        print(f"✅ IBKR: {host}:{port} / {account}")
    else:
        print("⚠️ IBKR 配置不完整")
except Exception as e:
    print(f"❌ IBKR 配置检查失败: {e}")

# 7. 邮件通知
print("\n[7/8] 邮件通知配置...")
try:
    smtp_host = os.getenv('SMTP_HOST')
    smtp_user = os.getenv('SMTP_USER')
    if smtp_host and smtp_user:
        print(f"✅ SMTP: {smtp_host} / {smtp_user}")
    else:
        print("⚠️ SMTP 配置不完整")
except Exception as e:
    print(f"❌ 邮件配置检查失败: {e}")

# 8. 部署服务
print("\n[8/8] 部署授权服务...")
try:
    token = os.getenv('DEPLOY_ADMIN_TOKEN')
    port = os.getenv('DEPLOY_PORT')
    if token and port:
        print(f"✅ 部署服务: 端口 {port}")
    else:
        print("⚠️ 部署服务配置不完整")
except Exception as e:
    print(f"❌ 部署服务检查失败: {e}")

print("\n" + "=" * 60)
print("✅ 配置检查完成！")
print("\n下一步: 启动服务进行实际连接测试")

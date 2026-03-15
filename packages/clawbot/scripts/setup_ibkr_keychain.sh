#!/bin/bash
set -euo pipefail

echo "配置 IBKR 自动登录凭据（保存到 macOS Keychain）"

read -r -p "IBKR 用户名: " IBKR_USER
if [[ -z "$IBKR_USER" ]]; then
  echo "用户名不能为空"
  exit 1
fi

read -r -s -p "IBKR 密码: " IBKR_PASS
echo
if [[ -z "$IBKR_PASS" ]]; then
  echo "密码不能为空"
  exit 1
fi

security add-generic-password -U -s "clawbot.ibkr.username" -a "default" -w "$IBKR_USER"
security add-generic-password -U -s "clawbot.ibkr.password" -a "default" -w "$IBKR_PASS"

echo "已写入 Keychain: clawbot.ibkr.username / clawbot.ibkr.password"

#!/usr/bin/env sh
set -eu

BASE_URL="${1:-http://127.0.0.1:3180}"
ADMIN_CODE="${2:-}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl -fsS "$BASE_URL/" >/dev/null
curl -fsS "$BASE_URL/api/frist/dashboard" -o "$TMP_DIR/dashboard.json"
grep -q '"authenticated":false' "$TMP_DIR/dashboard.json"
curl -fsS "$BASE_URL/api/frist/challenge" -o "$TMP_DIR/challenge.json"
grep -Eq '"id":"cap-|\"required\":false' "$TMP_DIR/challenge.json"

if [ -n "$ADMIN_CODE" ]; then
  status="$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/admin.html")"
  test "$status" = "404"
  curl -fsS "$BASE_URL/admin.html?code=$ADMIN_CODE" -o "$TMP_DIR/admin.html"
  grep -Eq "Frist-API (Admin|管理工作台)|data-admin-token" "$TMP_DIR/admin.html"
fi

echo "Frist-API smoke test passed: $BASE_URL"

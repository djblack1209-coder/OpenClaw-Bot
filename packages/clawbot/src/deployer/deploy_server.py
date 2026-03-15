"""部署授权服务端 — Flask API"""
import os
import logging
from flask import Flask, request, jsonify

from .license_manager import LicenseManager

logger = logging.getLogger(__name__)

app = Flask(__name__)
lm = LicenseManager()

ADMIN_TOKEN = os.getenv("DEPLOY_ADMIN_TOKEN", "changeme-admin-token")


def _check_admin(req):
    token = req.headers.get("X-Admin-Token", "")
    return token == ADMIN_TOKEN


# ---- 客户端接口 ----

@app.route("/api/deploy/auth", methods=["POST"])
def auth():
    """客户端登录验证"""
    data = request.json or {}
    username = data.get("username", "")
    password = data.get("password", "")
    machine_id = data.get("machine_id", "")
    ip = request.remote_addr or ""
    result = lm.authenticate(username, password, machine_id, ip)
    code = 200 if result["ok"] else 403
    return jsonify(result), code


@app.route("/api/deploy/config", methods=["POST"])
def get_deploy_config():
    """获取部署配置包（验证后）"""
    data = request.json or {}
    license_key = data.get("license_key", "")
    machine_id = data.get("machine_id", "")

    if not lm.verify_device(license_key, machine_id):
        return jsonify({"ok": False, "message": "设备未授权"}), 403

    # 返回部署配置模板
    config = _build_deploy_config(data)
    return jsonify({"ok": True, "config": config})


@app.route("/api/deploy/heartbeat", methods=["POST"])
def heartbeat():
    """客户端心跳 — 定期验证 license 有效性"""
    data = request.json or {}
    key = data.get("license_key", "")
    mid = data.get("machine_id", "")
    valid = lm.verify_device(key, mid)
    return jsonify({"ok": valid, "message": "有效" if valid else "授权已失效"})


# ---- 管理接口 ----

@app.route("/api/admin/licenses", methods=["GET"])
def list_licenses():
    if not _check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(lm.list_licenses())


@app.route("/api/admin/licenses", methods=["POST"])
def create_license():
    if not _check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    data = request.json or {}
    key = lm.create_license(
        username=data.get("username", ""),
        password=data.get("password", ""),
        xianyu_order_id=data.get("xianyu_order_id", ""),
        max_devices=data.get("max_devices", 1),
        days=data.get("days", 365),
        notes=data.get("notes", ""),
    )
    return jsonify({"ok": True, "license_key": key})


@app.route("/api/admin/licenses/<key>/revoke", methods=["POST"])
def revoke_license(key):
    if not _check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    lm.revoke_license(key)
    return jsonify({"ok": True})


# ---- 部署配置生成 ----

def _build_deploy_config(data: dict) -> dict:
    """根据客户信息生成 OpenClaw 配置"""
    return {
        "version": "2026.3",
        "gateway": {
            "port": 18789,
        },
        "models": {
            "providers": {
                "custom": {
                    "baseUrl": data.get("api_base_url", "https://api.openai.com/v1"),
                    "apiKey": data.get("api_key", ""),
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": data.get("model_id", "gpt-4o"),
                            "name": data.get("model_name", "GPT-4o"),
                            "reasoning": False,
                            "contextWindow": 128000,
                            "maxTokens": 4096,
                        }
                    ],
                }
            }
        },
        "channels": {
            "telegram": {
                "enabled": bool(data.get("telegram_token")),
                "token": data.get("telegram_token", ""),
            }
        },
        "skills_bundle": [
            "self-improving-agent",
            "openclaw-backup",
            "find-skills",
            "weather",
            "summarize",
            "github",
        ],
        "agent_defaults": {
            "model": data.get("model_id", "gpt-4o"),
            "temperature": 0.7,
        },
    }


def run_server(host: str = "0.0.0.0", port: int = 18800):
    logger.info(f"部署授权服务启动: {host}:{port}")
    app.run(host=host, port=port, debug=False)

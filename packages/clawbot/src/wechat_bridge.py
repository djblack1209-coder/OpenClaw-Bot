"""
微信通知桥接 — 将 Python 后端通知同步推送到微信端

直接调用腾讯 iLink API (ilinkai.weixin.qq.com) 发送消息。
凭证从 .openclaw/openclaw-weixin/accounts/ 目录读取。

工作原理:
  1. 读取本地 openclaw-weixin 插件保存的 Bot Token
  2. 通过 iLink getconfig API 获取 contextToken
  3. 通过 iLink sendmessage API 推送通知文本

使用方式:
  环境变量 WECHAT_NOTIFY_ENABLED=true  → 启用微信通知
  无需额外配置，自动读取已扫码登录的微信凭证

限制:
  - 需要用户先与 Bot 有过对话（iLink 平台要求）
  - contextToken 有时效性，如果长时间未对话可能失效

> 最后更新: 2026-03-25
"""
import asyncio
import base64
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from src.constants import TG_SAFE_LENGTH
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)

from src.http_client import ResilientHTTPClient

# 模块级别 HTTP 客户端（自动重试 + 熔断）
_http = ResilientHTTPClient(timeout=15.0, name="wechat_bridge")

# ── 配置 ────────────────────────────────────────────────
_WECHAT_ENABLED = os.getenv("WECHAT_NOTIFY_ENABLED", "").lower() in ("true", "1", "yes")
_ILINK_BASE = "https://ilinkai.weixin.qq.com"

# 凭证路径 (相对于项目根目录)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # → OpenClaw Bot/
_ACCOUNTS_DIR = _PROJECT_ROOT / ".openclaw" / "openclaw-weixin" / "accounts"

# 缓存
_cached_token: Optional[str] = None
_cached_user_id: Optional[str] = None
_cached_context_token: Optional[str] = None
_context_token_ts: float = 0
_warned_not_configured = False


def _load_credentials() -> tuple[Optional[str], Optional[str]]:
    """从本地文件读取 Bot Token 和用户 ID。"""
    global _cached_token, _cached_user_id
    if _cached_token and _cached_user_id:
        return _cached_token, _cached_user_id

    try:
        # 读取 accounts.json 获取账号 ID
        accounts_file = _ACCOUNTS_DIR.parent / "accounts.json"
        if not accounts_file.exists():
            # 尝试 .openclaw 根目录
            alt = _PROJECT_ROOT / ".openclaw" / "openclaw-weixin" / "accounts.json"
            if alt.exists():
                accounts_file = alt
        
        if not accounts_file.exists():
            return None, None

        with open(accounts_file, "r") as f:
            account_ids = json.load(f)

        if not account_ids:
            return None, None

        account_id = account_ids[0] if isinstance(account_ids, list) else None
        if not account_id:
            return None, None

        # 读取账号凭证
        cred_file = _ACCOUNTS_DIR / f"{account_id}.json"
        if not cred_file.exists():
            return None, None

        with open(cred_file, "r") as f:
            cred = json.load(f)

        _cached_token = cred.get("token", "")
        _cached_user_id = cred.get("userId", "")
        logger.debug(f"[WeChatBridge] 凭证已加载: user={_cached_user_id[:20]}...")
        return _cached_token, _cached_user_id

    except Exception as e:
        logger.debug(f"[WeChatBridge] 凭证读取失败: {e}")
        return None, None


def _random_wechat_uin() -> str:
    """生成 X-WECHAT-UIN header（使用密码学安全随机数）。"""
    uint32 = secrets.randbelow(2**32)
    return base64.b64encode(str(uint32).encode()).decode()


def _build_headers(token: str, body_bytes: bytes) -> dict:
    """构建 iLink API 请求头。"""
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body_bytes)),
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def is_wechat_notify_enabled() -> bool:
    """检查微信通知是否已启用并有凭证。"""
    if not _WECHAT_ENABLED:
        return False
    token, user_id = _load_credentials()
    return bool(token and user_id)


async def _get_context_token(token: str, user_id: str) -> Optional[str]:
    """通过 getconfig API 获取 contextToken（30 分钟 TTL 自动刷新）。"""
    global _cached_context_token, _context_token_ts
    import time
    if _cached_context_token and (time.time() - _context_token_ts) < 1800:
        return _cached_context_token

    try:
        body = json.dumps({
            "ilink_user_id": user_id,
            "base_info": {"channel_version": "1.0.2"},
        })
        body_bytes = body.encode("utf-8")
        headers = _build_headers(token, body_bytes)

        resp = await _http.post(
            f"{_ILINK_BASE}/ilink/bot/getconfig",
            content=body_bytes,
            headers=headers,
        )
        if resp.status_code == 200:
                data = resp.json()
                ct = data.get("context_token", "")
                if ct:
                    _cached_context_token = ct
                    _context_token_ts = time.time()
                    return ct
    except Exception as e:
        logger.debug(f"[WeChatBridge] getconfig 失败: {e}")
    return None


async def send_to_wechat(text: str, user_id: Optional[str] = None) -> bool:
    """将通知文本发送到微信用户。

    Args:
        text: 通知文本（自动截断到 TG_SAFE_LENGTH 字符）
        user_id: 微信用户 ID (默认使用凭证文件中的 userId)

    Returns:
        True 发送成功, False 发送失败
    """
    global _warned_not_configured, _cached_context_token

    if not _WECHAT_ENABLED:
        return False

    token, default_user = _load_credentials()
    target = user_id or default_user

    if not token or not target:
        if not _warned_not_configured:
            logger.info(
                "[WeChatBridge] 微信凭证未找到 — "
                "请先执行 openclaw channels login --channel openclaw-weixin 扫码登录"
            )
            _warned_not_configured = True
        return False

    text = text[:TG_SAFE_LENGTH]

    # 获取 contextToken
    context_token = await _get_context_token(token, target)

    try:
        import httpx  # noqa: F811 — 保留用于 ImportError 检查
    except ImportError:
        logger.debug("[WeChatBridge] httpx 未安装，跳过微信通知")
        return False

    # 构建 sendmessage 请求体（与 TypeScript 插件格式一致）
    client_id = f"openclaw-weixin-py-{secrets.randbelow(90000) + 10000}"
    body = json.dumps({
        "msg": {
            "from_user_id": "",
            "to_user_id": target,
            "client_id": client_id,
            "message_type": 2,  # BOT
            "message_state": 1,  # FINISH
            "item_list": [
                {"type": 1, "text_item": {"text": text}}  # TEXT
            ],
            "context_token": context_token or "",
        },
        "base_info": {"channel_version": "1.0.2"},
    })
    body_bytes = body.encode("utf-8")
    headers = _build_headers(token, body_bytes)

    # 最多重试 1 次（仅用于 401/403 token 刷新，网络级重试由 ResilientHTTPClient 处理）
    for attempt in range(2):
        try:
            resp = await _http.post(
                f"{_ILINK_BASE}/ilink/bot/sendmessage",
                content=body_bytes,
                headers=headers,
            )
            if resp.status_code == 200:
                logger.debug(f"[WeChatBridge] 消息已发送到微信 {target[:20]}...")
                return True
            # token 过期，清缓存重试
            if resp.status_code in (401, 403):
                _cached_context_token = None
                _context_token_ts = 0
                context_token = await _get_context_token(token, target)
                continue
            logger.warning(f"[WeChatBridge] 发送失败 HTTP {resp.status_code}: {scrub_secrets(resp.text[:200])}")
            _cached_context_token = None
            _context_token_ts = 0
        except Exception as e:
            logger.debug("[微信桥接] 发送失败: %s", e)
    return False


def send_to_wechat_sync(text: str, user_id: Optional[str] = None) -> bool:
    """同步版本 — 在非异步上下文中使用。"""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as e:  # noqa: F841
            loop = None
        if loop and loop.is_running():
            # 在已有事件循环中，用线程池执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, send_to_wechat(text, user_id))
                return future.result(timeout=20)
        else:
            return asyncio.run(send_to_wechat(text, user_id))
    except Exception as e:
        logger.debug(f"[WeChatBridge] 同步发送失败: {e}")
        return False

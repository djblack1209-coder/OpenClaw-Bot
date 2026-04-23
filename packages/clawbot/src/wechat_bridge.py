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

# 凭证路径 — 优先 HOME 目录下的 .openclaw（OpenClaw CLI 默认位置），回退到项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # → OpenEverything/
_HOME_OPENCLAW = Path.home() / ".openclaw" / "openclaw-weixin" / "accounts"
_PROJECT_OPENCLAW = _PROJECT_ROOT / ".openclaw" / "openclaw-weixin" / "accounts"
_ACCOUNTS_DIR = _HOME_OPENCLAW if _HOME_OPENCLAW.exists() else _PROJECT_OPENCLAW


class _CredentialStore:
    """微信凭证安全存储 — 防止凭证作为模块级全局变量被随意访问

    使用 __slots__ 限制属性访问，__repr__ 屏蔽敏感值，
    避免 token 在日志、调试器或 dir() 中意外泄露。
    """
    __slots__ = ("_token", "_user_id", "_context_token", "_context_token_ts", "_warned")

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._user_id: Optional[str] = None
        self._context_token: Optional[str] = None
        self._context_token_ts: float = 0
        self._warned: bool = False

    def __repr__(self) -> str:
        # 屏蔽敏感值，防止在日志或调试中意外泄露
        has_token = "set" if self._token else "unset"
        has_user = "set" if self._user_id else "unset"
        return f"<_CredentialStore token={has_token} user_id={has_user}>"

    @property
    def token(self) -> Optional[str]:
        self._ensure_loaded()
        return self._token

    @property
    def user_id(self) -> Optional[str]:
        self._ensure_loaded()
        return self._user_id

    @property
    def context_token(self) -> Optional[str]:
        return self._context_token

    @context_token.setter
    def context_token(self, value: Optional[str]) -> None:
        self._context_token = value

    @property
    def context_token_ts(self) -> float:
        return self._context_token_ts

    @context_token_ts.setter
    def context_token_ts(self, value: float) -> None:
        self._context_token_ts = value

    @property
    def warned(self) -> bool:
        return self._warned

    @warned.setter
    def warned(self, value: bool) -> None:
        self._warned = value

    def _ensure_loaded(self) -> None:
        """懒加载凭证 — 首次访问时才从文件读取"""
        if self._token and self._user_id:
            return
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """从本地凭证文件读取 Bot Token 和用户 ID"""
        try:
            accounts_file = _ACCOUNTS_DIR.parent / "accounts.json"
            if not accounts_file.exists():
                alt = _PROJECT_ROOT / ".openclaw" / "openclaw-weixin" / "accounts.json"
                if alt.exists():
                    accounts_file = alt

            if not accounts_file.exists():
                return

            with open(accounts_file, "r") as f:
                account_ids = json.load(f)

            if not account_ids:
                return

            account_id = account_ids[0] if isinstance(account_ids, list) else None
            if not account_id:
                return

            cred_file = _ACCOUNTS_DIR / f"{account_id}.json"
            if not cred_file.exists():
                return

            with open(cred_file, "r") as f:
                cred = json.load(f)

            self._token = cred.get("token", "")
            self._user_id = cred.get("userId", "")
            logger.debug("[WeChatBridge] 凭证已加载: user=%s...", self._user_id[:20] if self._user_id else "")

        except Exception as e:
            logger.debug("[WeChatBridge] 凭证读取失败: %s", e)

    def clear_context(self) -> None:
        """清除 context_token 缓存（token 过期时调用）"""
        self._context_token = None
        self._context_token_ts = 0


# 模块级单例 — 通过属性访问凭证，不直接暴露 token 字符串
_creds = _CredentialStore()


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
    return bool(_creds.token and _creds.user_id)


async def _get_context_token(token: str, user_id: str) -> Optional[str]:
    """通过 getconfig API 获取 contextToken（30 分钟 TTL 自动刷新）。"""
    import time
    if _creds.context_token and (time.time() - _creds.context_token_ts) < 1800:
        return _creds.context_token

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
                    _creds.context_token = ct
                    _creds.context_token_ts = time.time()
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
    if not _WECHAT_ENABLED:
        return False

    token = _creds.token
    target = user_id or _creds.user_id

    if not token or not target:
        if not _creds.warned:
            logger.info(
                "[WeChatBridge] 微信凭证未找到 — "
                "请先执行 openclaw channels login --channel openclaw-weixin 扫码登录"
            )
            _creds.warned = True
        return False

    text = text[:TG_SAFE_LENGTH]

    # 获取 contextToken
    context_token = await _get_context_token(token, target)

    try:
        import httpx  # noqa: F401 — 保留用于 ImportError 可用性检查
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
                _creds.clear_context()
                context_token = await _get_context_token(token, target)
                continue
            logger.warning(f"[WeChatBridge] 发送失败 HTTP {resp.status_code}: {scrub_secrets(resp.text[:200])}")
            _creds.clear_context()
        except Exception as e:
            logger.warning("[微信桥接] 发送失败: %s", e)
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

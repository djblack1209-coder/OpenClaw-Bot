"""
微信消息接收服务 — 云端部署版

通过 iLink getUpdates 长轮询接收微信消息，转发到本地 Mac 后端处理，
收到回复后通过 sendMessage 发回微信。

部署到腾讯云服务器，作为微信消息的云端中转站。

工作原理:
  1. 长轮询 iLink getUpdates API 接收微信消息
  2. 将收到的消息通过 HTTP POST 转发到 Mac 后端 (/api/v1/wechat/incoming)
  3. Mac 后端用 LLM 生成回复，返回给本服务
  4. 本服务通过 sendMessage 将回复发回微信

配置（环境变量）:
  WECHAT_BOT_TOKEN — iLink Bot Token（从 ~/.openclaw 读取或手动设置）
  WECHAT_USER_ID — Bot 的 user_id
  WECHAT_ILINK_BASE — iLink API 地址（默认 https://ilinkai.weixin.qq.com）
  BACKEND_URL — Mac 后端地址（如 http://your-mac-ip:18790）
  BACKEND_API_TOKEN — 后端 API 鉴权 Token

> 最后更新: 2026-04-22
"""
import asyncio
import base64
import json
import logging
import os
import secrets
import signal
import sys
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("wechat_receiver")

# ── 配置 ──────────────────────────────────────────────
ILINK_BASE = os.getenv("WECHAT_ILINK_BASE", "https://ilinkai.weixin.qq.com")
BACKEND_URL = os.getenv("BACKEND_URL", "")
BACKEND_API_TOKEN = os.getenv("BACKEND_API_TOKEN", "")
CHANNEL_VERSION = "1.0.3"

# 长轮询配置
POLL_TIMEOUT_S = 35  # iLink 默认长轮询超时（服务端控制，不能改太小）
MAX_CONSECUTIVE_ERRORS = 5  # 连续错误次数上限
ERROR_BACKOFF_S = 30  # 连续错误后的退避时间
SESSION_PAUSE_S = 3600  # session 过期后暂停时间（1小时）

# ── 凭证管理 ──────────────────────────────────────────


def _load_credentials() -> tuple[str, str]:
    """加载 Bot Token 和 User ID

    优先级: 环境变量 > ~/.openclaw 本地文件
    """
    token = os.getenv("WECHAT_BOT_TOKEN", "")
    user_id = os.getenv("WECHAT_USER_ID", "")

    if token and user_id:
        return token, user_id

    # 从本地文件读取
    accounts_dir = Path.home() / ".openclaw" / "openclaw-weixin" / "accounts"
    accounts_file = accounts_dir.parent / "accounts.json"

    if not accounts_file.exists():
        logger.error("找不到微信凭证文件: %s", accounts_file)
        return "", ""

    try:
        with open(accounts_file) as f:
            account_ids = json.load(f)
        if not account_ids:
            return "", ""

        account_id = account_ids[0] if isinstance(account_ids, list) else None
        if not account_id:
            return "", ""

        cred_file = accounts_dir / f"{account_id}.json"
        if not cred_file.exists():
            logger.error("找不到凭证文件: %s", cred_file)
            return "", ""

        with open(cred_file) as f:
            cred = json.load(f)

        return cred.get("token", ""), cred.get("userId", "")
    except Exception as e:
        logger.error("读取微信凭证失败: %s", e)
        return "", ""


def _random_uin() -> str:
    """生成 X-WECHAT-UIN header"""
    return base64.b64encode(str(secrets.randbelow(2**32)).encode()).decode()


def _build_headers(token: str, body_bytes: bytes) -> dict:
    """构建 iLink API 请求头"""
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "Content-Length": str(len(body_bytes)),
        "X-WECHAT-UIN": _random_uin(),
    }


# ── context_token 缓存（每个用户独立） ──────────────────
_context_tokens: dict[str, str] = {}
_CONTEXT_FILE = Path.home() / ".openclaw" / "wechat_receiver_contexts.json"


def _load_context_tokens():
    """从磁盘恢复 context_token 缓存"""
    global _context_tokens
    if _CONTEXT_FILE.exists():
        try:
            with open(_CONTEXT_FILE) as f:
                _context_tokens = json.load(f)
            logger.info("恢复了 %d 个 context_token", len(_context_tokens))
        except Exception:
            _context_tokens = {}


def _save_context_tokens():
    """持久化 context_token 到磁盘"""
    try:
        _CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONTEXT_FILE, "w") as f:
            json.dump(_context_tokens, f)
    except Exception as e:
        logger.warning("保存 context_token 失败: %s", e)


# ── get_updates_buf 持久化 ─────────────────────────────
_BUF_FILE = Path.home() / ".openclaw" / "wechat_receiver_buf.txt"


def _load_buf() -> str:
    """恢复上次的轮询游标"""
    if _BUF_FILE.exists():
        return _BUF_FILE.read_text().strip()
    return ""


def _save_buf(buf: str):
    """保存轮询游标"""
    try:
        _BUF_FILE.parent.mkdir(parents=True, exist_ok=True)
        _BUF_FILE.write_text(buf)
    except Exception:
        pass


# ── 核心 API 调用 ─────────────────────────────────────


async def _get_updates(client: httpx.AsyncClient, token: str, buf: str) -> dict:
    """调用 getUpdates 长轮询 API"""
    body = json.dumps({
        "get_updates_buf": buf,
        "base_info": {"channel_version": CHANNEL_VERSION},
    })
    body_bytes = body.encode("utf-8")
    headers = _build_headers(token, body_bytes)

    resp = await client.post(
        f"{ILINK_BASE}/ilink/bot/getupdates",
        content=body_bytes,
        headers=headers,
        timeout=POLL_TIMEOUT_S + 10,  # 客户端超时比服务器长一点
    )
    return resp.json()


async def _send_message(client: httpx.AsyncClient, token: str,
                        to_user: str, text: str, context_token: str) -> bool:
    """发送回复消息到微信"""
    body = json.dumps({
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user,
            "client_id": f"oc-{secrets.token_hex(8)}",
            "message_type": 2,  # BOT
            "message_state": 2,  # FINISH
            "item_list": [
                {"type": 1, "text_item": {"text": text}}
            ],
            "context_token": context_token,
        },
        "base_info": {"channel_version": CHANNEL_VERSION},
    })
    body_bytes = body.encode("utf-8")
    headers = _build_headers(token, body_bytes)

    try:
        resp = await client.post(
            f"{ILINK_BASE}/ilink/bot/sendmessage",
            content=body_bytes,
            headers=headers,
            timeout=15,
        )
        data = resp.json()
        # iLink sendMessage 成功时返回 {} 或 {"ret": 0}
        # 只有明确的错误码才算失败
        if resp.status_code == 200 and data.get("ret", 0) == 0:
            return True
        logger.warning("sendMessage 失败: status=%s body=%s", resp.status_code, data)
    except Exception as e:
        logger.error("sendMessage 异常: %s", e)
    return False


# ── 消息处理 ──────────────────────────────────────────


def _extract_text(msg: dict) -> str:
    """从消息中提取文本内容"""
    items = msg.get("item_list", [])
    texts = []
    for item in items:
        if item.get("type") == 1 and item.get("text_item"):
            t = item["text_item"].get("text", "")
            if t:
                texts.append(t)
    return "\n".join(texts)


async def _forward_to_backend(client: httpx.AsyncClient, from_user: str,
                               text: str) -> str:
    """生成 AI 回复 — 优先云端直接调 LLM API，后端不可达时降级"""

    # 方案 1: 云端直接调 SiliconFlow（最快，不依赖 Mac）
    sf_key = os.getenv("SILICONFLOW_API_KEY", "")
    if sf_key:
        try:
            resp = await client.post(
                "https://api.siliconflow.cn/v1/chat/completions",
                json={
                    "model": "Qwen/Qwen2.5-7B-Instruct",  # 7B 更快，微信场景够用
                    "messages": [
                        {"role": "system", "content": "你是 OpenClaw AI 助手。用中文简洁友好地回答。"},
                        {"role": "user", "content": text},
                    ],
                    "max_tokens": 500,
                    "temperature": 0.7,
                },
                headers={
                    "Authorization": f"Bearer {sf_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if reply.strip():
                    import re
                    reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL)
                    reply = re.sub(r'<think>.*$', '', reply, flags=re.DOTALL)
                    reply = reply.strip()
                    if reply:
                        logger.info("SiliconFlow 回复成功 (%.1fs)", resp.elapsed.total_seconds())
                        return reply
        except Exception as e:
            logger.warning("SiliconFlow 调用失败: %s", e)

    # 方案 2: 云端调 Groq（备选，速度极快）
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "你是 OpenClaw AI 助手。用中文简洁友好地回答。"},
                        {"role": "user", "content": text},
                    ],
                    "max_tokens": 500,
                },
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if reply.strip():
                    logger.info("Groq 回复成功 (%.1fs)", resp.elapsed.total_seconds())
                    return reply.strip()
        except Exception as e:
            logger.warning("Groq 调用失败: %s", e)

    # 方案 3: 走 Mac 后端（最后手段）
    if BACKEND_URL:
        try:
            headers = {"Content-Type": "application/json"}
            if BACKEND_API_TOKEN:
                headers["X-API-Token"] = BACKEND_API_TOKEN
            resp = await client.post(
                f"{BACKEND_URL}/api/v1/wechat/incoming",
                json={"from_user": from_user, "text": text},
                headers=headers,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("reply", "（无回复）")
        except Exception as e:
            logger.warning("Mac 后端调用失败: %s", e)

    return "⚠️ AI 服务暂时不可用，请稍后再试。"


async def _direct_llm_reply(text: str) -> str:
    """直接通过 g4f 或 LiteLLM 获取回复（后端不可达时的降级方案）"""
    g4f_url = os.getenv("G4F_BASE_URL", "http://127.0.0.1:18891/v1")
    g4f_key = os.getenv("G4F_API_KEY", "dummy")

    try:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                f"{g4f_url}/chat/completions",
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "你是 OpenClaw AI 助手。用中文简洁回复。"},
                        {"role": "user", "content": text},
                    ],
                    "max_tokens": 500,
                },
                headers={
                    "Authorization": f"Bearer {g4f_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            data = resp.json()
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if reply:
                # 过滤 g4f 广告
                import re
                reply = re.sub(r'\n*Need proxies.*?https?://op\.wtf\s*', '', reply).strip()
                return reply or "（无回复）"
    except Exception as e:
        logger.error("直接 LLM 调用失败: %s", e)
    return "⚠️ AI 服务暂时不可用。"


# ── 主循环 ────────────────────────────────────────────


async def main():
    """微信消息接收主循环"""
    token, user_id = _load_credentials()
    if not token:
        logger.error("❌ 无法加载微信凭证，退出。")
        logger.error("请设置环境变量 WECHAT_BOT_TOKEN 和 WECHAT_USER_ID，")
        logger.error("或确保 ~/.openclaw/openclaw-weixin/accounts/ 目录存在凭证文件。")
        sys.exit(1)

    logger.info("✅ 微信凭证已加载: user=%s...", user_id[:20])
    logger.info("   iLink: %s", ILINK_BASE)
    logger.info("   后端: %s", BACKEND_URL or "（未配置，使用本地 LLM）")

    # 恢复状态
    _load_context_tokens()
    buf = _load_buf()
    if buf:
        logger.info("恢复轮询游标: %s...", buf[:30])

    consecutive_errors = 0
    running = True

    # 优雅退出
    def _shutdown(sig, frame):
        nonlocal running
        logger.info("收到信号 %s，正在退出...", sig)
        running = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    async with httpx.AsyncClient() as client:
        logger.info("🚀 微信消息接收服务已启动，开始长轮询...")

        while running:
            try:
                data = await _get_updates(client, token, buf)

                ret = data.get("ret", 0)  # iLink 正常响应无 ret 字段，默认 0 表示成功
                errcode = data.get("errcode", 0)

                # session 过期
                if ret == -14 or errcode == -14:
                    logger.warning("⚠️ Session 过期 (errcode=-14)，暂停 %d 秒后重试", SESSION_PAUSE_S)
                    await asyncio.sleep(SESSION_PAUSE_S)
                    continue

                # 有明确错误码的失败
                if errcode and errcode != 0:
                    consecutive_errors += 1
                    logger.warning("getUpdates 错误: ret=%s errcode=%s errmsg=%s (连续%d次)",
                                   ret, errcode, data.get("errmsg", ""), consecutive_errors)
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error("连续 %d 次错误，退避 %d 秒", consecutive_errors, ERROR_BACKOFF_S)
                        await asyncio.sleep(ERROR_BACKOFF_S)
                        consecutive_errors = 0
                    else:
                        await asyncio.sleep(2)
                    continue

                # 成功（无 ret 字段或 ret=0 都算成功）
                consecutive_errors = 0
                new_buf = data.get("get_updates_buf", buf)
                if new_buf != buf:
                    buf = new_buf
                    _save_buf(buf)

                msgs = data.get("msgs", [])
                if not msgs:
                    continue  # 没有新消息，继续轮询

                logger.info("收到 %d 条消息", len(msgs))

                for msg in msgs:
                    # 只处理用户发送的完成消息
                    msg_type = msg.get("message_type", 0)
                    msg_state = msg.get("message_state", 0)
                    if msg_type != 1 or msg_state != 2:
                        continue  # 跳过非用户消息和未完成消息

                    from_user = msg.get("from_user_id", "")
                    text = _extract_text(msg)
                    if not text or not from_user:
                        continue

                    # 保存 context_token（发回复时需要）
                    ctx_token = msg.get("context_token", "")
                    if ctx_token:
                        _context_tokens[from_user] = ctx_token
                        _save_context_tokens()

                    logger.info("📩 来自 %s...: %s", from_user[:15], text[:50])

                    # 获取 AI 回复
                    reply = await _forward_to_backend(client, from_user, text)

                    # 发回微信
                    ctx = _context_tokens.get(from_user, ctx_token)
                    if await _send_message(client, token, from_user, reply, ctx):
                        logger.info("✅ 回复已发送: %s...", reply[:50])
                    else:
                        logger.error("❌ 回复发送失败")

            except httpx.TimeoutException:
                # 长轮询超时是正常的
                continue
            except asyncio.CancelledError:
                logger.info("任务被取消，退出")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error("轮询异常: %s", e)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    await asyncio.sleep(ERROR_BACKOFF_S)
                    consecutive_errors = 0
                else:
                    await asyncio.sleep(2)

    logger.info("微信消息接收服务已停止")


if __name__ == "__main__":
    asyncio.run(main())

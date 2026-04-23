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


# ── 微信命令路由 — 核心指令直接调后端 API ──────────────


async def _handle_command(client: httpx.AsyncClient, text: str) -> str | None:
    """识别微信端核心指令，直接调后端 API 返回结构化数据。

    返回 None 表示不是命令，走普通 LLM 聊天。
    返回字符串表示已处理，直接发回微信。
    """
    # 去空白和标点
    cmd = text.strip().lower().replace("？", "").replace("?", "").replace("！", "").replace("!", "")

    backend = BACKEND_URL
    if not backend:
        return None

    headers = {"Content-Type": "application/json"}
    if BACKEND_API_TOKEN:
        headers["X-API-Token"] = BACKEND_API_TOKEN

    try:
        # 日报类指令
        if cmd in ("日报", "简报", "今日简报", "brief", "/brief"):
            resp = await client.get(
                f"{backend}/api/v1/system/daily-brief",
                headers=headers, timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                # 从 JSON 构建简洁文本摘要
                lines = ["📊 今日简报\n"]
                if data.get("cpu_percent") is not None:
                    lines.append(f"CPU: {data['cpu_percent']:.0f}% | 内存: {data.get('memory_percent', 0):.0f}%")
                if data.get("bots_online") is not None:
                    lines.append(f"Bot: {data.get('bots_online', 0)}/{data.get('bots_total', 0)} 在线")
                if data.get("today_messages") is not None:
                    lines.append(f"今日消息: {data['today_messages']}")
                return "\n".join(lines) if len(lines) > 1 else None

        # 系统状态类指令
        if cmd in ("状态", "系统状态", "status", "/status"):
            resp = await client.get(
                f"{backend}/api/v1/status",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                bots = data.get("bots", [])
                alive = sum(1 for b in bots if b.get("alive"))
                uptime_h = data.get("uptime_seconds", 0) / 3600
                xianyu = data.get("xianyu", {})
                lines = [
                    "🖥 系统状态\n",
                    f"运行时间: {uptime_h:.1f} 小时",
                    f"Bot: {alive}/{len(bots)} 在线",
                    f"闲鱼: {'✅ 在线' if xianyu.get('online') else '❌ 离线'}",
                ]
                if xianyu.get("auto_reply_active"):
                    lines.append(f"自动回复: ✅ | 今日咨询: {xianyu.get('conversations_today', 0)}")
                return "\n".join(lines)

        # 持仓/投资组合类指令
        if cmd in ("持仓", "仓位", "portfolio", "/portfolio", "ipositions", "/ipositions"):
            resp = await client.get(
                f"{backend}/api/v1/portfolio/positions",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                positions = data if isinstance(data, list) else data.get("positions", [])
                if not positions:
                    return "💼 当前无持仓"
                lines = ["💼 持仓概览\n"]
                total_pnl = 0
                for p in positions[:10]:
                    sym = p.get("symbol", "?")
                    qty = p.get("quantity", p.get("position", 0))
                    pnl = p.get("unrealized_pnl", p.get("pnl", 0))
                    total_pnl += pnl
                    pnl_icon = "📈" if pnl >= 0 else "📉"
                    lines.append(f"{pnl_icon} {sym}: {qty}股 ${pnl:+.2f}")
                lines.append(f"\n总浮盈亏: ${total_pnl:+.2f}")
                return "\n".join(lines)

        # 行情类指令
        if cmd in ("行情", "market", "/market", "大盘"):
            resp = await client.get(
                f"{backend}/api/v1/monitor/finance",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                quotes = data if isinstance(data, list) else data.get("quotes", [])
                if not quotes:
                    return "💹 行情数据暂不可用"
                lines = ["💹 市场行情\n"]
                for q in quotes[:8]:
                    name = q.get("name", q.get("symbol", "?"))
                    price = q.get("price", 0)
                    change = q.get("change_pct", q.get("change_percent", 0))
                    icon = "🟢" if change >= 0 else "🔴"
                    lines.append(f"{icon} {name}: {price:.2f} ({change:+.2f}%)")
                return "\n".join(lines)

        # 性能/延迟类指令
        if cmd in ("性能", "perf", "/perf", "延迟"):
            resp = await client.get(
                f"{backend}/api/v1/perf",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                lines = [
                    "⚡ 性能指标\n",
                    f"CPU: {data.get('cpu_percent', 0):.0f}% | 内存: {data.get('memory_percent', 0):.0f}%",
                ]
                for m in data.get("latency_metrics", [])[:3]:
                    lines.append(f"{m['name']}: avg {m['avg']:.1f}s p95 {m['p95']:.1f}s ({m['count']}次)")
                return "\n".join(lines)

        # 闲鱼类指令
        if cmd in ("闲鱼", "xianyu", "/xianyu", "闲鱼状态"):
            resp = await client.get(
                f"{backend}/api/v1/status",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                xy = data.get("xianyu", {})
                lines = [
                    "🐟 闲鱼状态\n",
                    f"在线: {'✅' if xy.get('online') else '❌'}",
                    f"自动回复: {'✅' if xy.get('auto_reply_active') else '❌'}",
                    f"Cookie: {'✅' if xy.get('cookie_ok') else '⚠️ 需刷新'}",
                    f"今日咨询: {xy.get('conversations_today', 0)}",
                ]
                return "\n".join(lines)

        # 帮助指令
        if cmd in ("帮助", "help", "/help", "指令", "命令"):
            return (
                "📱 微信可用指令\n\n"
                "日报 — 查看今日简报\n"
                "状态 — 系统运行状态\n"
                "持仓 — 查看投资持仓\n"
                "行情 — 市场行情\n"
                "性能 — 系统性能指标\n"
                "闲鱼 — 闲鱼客服状态\n"
                "帮助 — 查看本列表\n\n"
                "其他消息 → AI 对话"
            )

    except Exception as e:
        logger.warning("[WeChat命令] %s 执行失败: %s", cmd, e)
        return None

    return None  # 不是已知命令，走 LLM 聊天


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

                    # 优先走命令路由（日报/持仓/行情/状态等核心指令）
                    reply = await _handle_command(client, text)
                    if reply is None:
                        # 不是命令，走 LLM 聊天
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

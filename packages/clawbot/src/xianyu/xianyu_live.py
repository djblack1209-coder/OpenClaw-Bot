"""闲鱼 WebSocket 实时监控 — 消息处理 + 订单检测 + AI 自动回复"""

import asyncio
import base64
import json
import logging
import os
import random
import re
import secrets
import sys
import time
import uuid
from collections import OrderedDict
from datetime import timedelta

import websockets

from src.constants import XIANYU_USER_AGENT
from src.utils import now_et

from .cookie_refresher import (
    build_cookie_str,
    is_cookie_expiring,
    refresh_cookies_via_session,
    update_env_file,
)
from .order_notifier import OrderNotifier
from .utils import decrypt, generate_device_id, generate_mid, generate_uuid, trans_cookies
from .xianyu_agent import XianyuReplyBot
from .xianyu_apis import XianyuApis
from .xianyu_context import XianyuContextManager

logger = logging.getLogger(__name__)

# ---- 快速回复规则（不走 LLM，省 token 秒回）----
QUICK_REPLIES = [
    (["还在吗", "在吗", "在不在", "有人吗", "你好", "hello", "hi"], "在的，有什么可以帮你的？"),
    (["能发货吗", "什么时候发货", "多久发货"], "拍下后马上远程部署，一般30分钟内搞定。"),
    (
        ["怎么用", "怎么使用", "好用吗"],
        "OpenClaw 是一个强大的 AI 助手，支持多模型、多渠道。拍下后我远程帮你装好，手把手教你用。",
    ),
    (["包邮吗", "有运费吗"], "这是远程服务，不需要物流，拍下后直接远程部署到你电脑上。"),
    (["能退吗", "退款"], "部署前可以全额退款。部署完成后如有问题，7天内免费售后。"),
    (
        ["安全吗", "靠谱吗"],
        "OpenClaw 是 GitHub 68K+ Star 的开源项目，代码完全透明。我提供的是部署服务，不涉及你的隐私数据。",
    ),
]


def _quick_reply(msg: str) -> str | None:
    clean = msg.strip().lower().replace("？", "").replace("?", "").replace("！", "")
    for keywords, reply in QUICK_REPLIES:
        if any(clean == kw or clean.endswith(kw) for kw in keywords):
            return reply
    return None


# ---- 价格提取（用于底价自动接受）----

_CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _cn_to_float(s: str) -> float | None:
    """将简单中文数字转为浮点数，如 '十五' -> 15, '二十' -> 20, '三十五' -> 35"""
    s = s.strip()
    if not s:
        return None
    # 纯中文数字（仅支持 1-99 的常见用法）
    if s == "十":
        return 10.0
    if s.startswith("十"):
        # 十五 -> 15
        rest = s[1:]
        if rest in _CN_DIGITS:
            return 10.0 + _CN_DIGITS[rest]
        return None
    if len(s) == 1 and s in _CN_DIGITS:
        return float(_CN_DIGITS[s])
    if len(s) >= 2 and s[0] in _CN_DIGITS and s[1] == "十":
        # 二十, 三十五
        tens = _CN_DIGITS[s[0]] * 10
        if len(s) == 2:
            return float(tens)
        if len(s) == 3 and s[2] in _CN_DIGITS:
            return float(tens + _CN_DIGITS[s[2]])
    return None


# 匹配 "¥15", "15块", "15元", "15.5", "能15吗", "15可以吗", "15行吗" 等
_PRICE_PATTERNS = [
    r"[¥￥]\s*(\d+(?:\.\d+)?)",  # ¥15 or ￥15.5
    r"(\d+(?:\.\d+)?)\s*[块元]",  # 15块, 15.5元
    r"(\d+(?:\.\d+)?)\s*(?:行|可以|卖|出|入|收|吗|么|嘛|不|怎么样|ok|OK|Ok)",  # 15行吗, 15可以吗
    r"(?:能不能|能否|可以|可不可以|出|卖|入|收)\s*(\d+(?:\.\d+)?)",  # 能不能15
]

_CN_PRICE_PATTERNS = [
    r"[¥￥]\s*([零一二两三四五六七八九十]+)",
    r"([零一二两三四五六七八九十]+)\s*[块元]",
    r"([零一二两三四五六七八九十]+)\s*(?:行|可以|卖|出|入|收|吗|么|嘛|不)",
    r"(?:能不能|能否|可以|可不可以|出|卖|入|收)\s*([零一二两三四五六七八九十]+)",
]


def _extract_price(msg: str) -> float | None:
    """从买家消息中提取出价金额，返回 float 或 None"""
    # 先尝试阿拉伯数字
    for pattern in _PRICE_PATTERNS:
        m = re.search(pattern, msg)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, IndexError) as e:  # noqa: F841
                continue
    # 尝试中文数字
    for pattern in _CN_PRICE_PATTERNS:
        m = re.search(pattern, msg)
        if m:
            val = _cn_to_float(m.group(1))
            if val is not None:
                return val
    # 兜底：消息中只有一个纯数字（含小数），且像是报价
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", msg)
    if m:
        try:
            return float(m.group(1))
        except ValueError as e:
            logger.debug("值解析失败: %s", e)
    return None


class XianyuLive:
    WSS_URL = "wss://wss-goofish.dingtalk.com/"

    def __init__(self, cookies_str: str):
        self.cookies_str = cookies_str
        self.cookies = trans_cookies(cookies_str)
        self.myid = self.cookies.get("unb", "")
        self.device_id = generate_device_id(self.myid)

        self.api = XianyuApis(cookies_str)
        self.ctx = XianyuContextManager()
        self.bot = XianyuReplyBot(ctx=self.ctx)
        self.notifier = OrderNotifier()

        # 心跳
        self.hb_interval = int(os.getenv("XIANYU_HB_INTERVAL", "15"))
        self.hb_timeout = int(os.getenv("XIANYU_HB_TIMEOUT", "5"))
        self.last_hb_time = 0.0
        self.last_hb_resp = 0.0

        # Token
        self.token_ttl = int(os.getenv("XIANYU_TOKEN_TTL", "3600"))
        self.current_token: str | None = None
        self.token_ts = 0.0
        self.restart_flag = False

        # 人工接管
        self.manual_chats: dict[str, float] = {}
        self.manual_timeout = int(os.getenv("XIANYU_MANUAL_TIMEOUT", "3600"))
        self.toggle_kw = os.getenv("XIANYU_TOGGLE_KW", "。")

        # 消息过期
        self.msg_expire = int(os.getenv("XIANYU_MSG_EXPIRE", "300000"))
        self.simulate_typing = os.getenv("XIANYU_SIMULATE_TYPING", "true").lower() == "true"

        # 首次咨询通知（避免重复）— HI-578: 用 OrderedDict 实现 FIFO 逐出
        self._notified_chats: OrderedDict[str, None] = OrderedDict()
        self._NOTIFIED_CHATS_MAX = 10000

        # Cookie 健康检查间隔（秒）
        self.cookie_check_interval = int(os.getenv("XIANYU_COOKIE_CHECK_INTERVAL", "600"))
        self._cookie_ok = True

        # HI-577/HI-733: app-key 从环境变量读取，缺省回退到与 xianyu_apis.py 一致的公共 appKey
        _DEFAULT_APP_KEY = "34839810"
        self._app_key = os.getenv("XIANYU_APP_KEY", _DEFAULT_APP_KEY)
        if self._app_key == _DEFAULT_APP_KEY:
            logger.debug("[闲鱼] XIANYU_APP_KEY 未设置，使用默认公共 appKey")

        # 消息速率限制（防止买家刷消息触发无限 LLM 调用）
        self._msg_timestamps: dict[str, list[float]] = {}
        self.MAX_MSGS_PER_MINUTE = int(os.getenv("XIANYU_MAX_MSGS_PER_MINUTE", "10"))

        # 并发状态锁 — 保护 _notified_chats / _msg_timestamps / manual_chats
        # 多个买家同时发消息时 handle_message 并发执行，需要锁保护共享状态
        self._state_lock = asyncio.Lock()

        # License 自动创建
        self._license_mgr = None
        try:
            from ..deployer.license_manager import LicenseManager

            self._license_mgr = LicenseManager()
        except Exception:
            logger.debug("LicenseManager 不可用，付款不自动创建 License")

        self.ws = None

    async def close(self):
        """关闭底层 HTTP 连接，防止 TCP 泄漏（HI-410）"""
        try:
            await self.api.close()
        except Exception as e:
            logger.debug("XianyuLive.close() 关闭 API 连接失败: %s", e)

    # ---- Token ----
    async def refresh_token(self) -> str | None:
        result = await self.api.get_token(self.device_id)
        if result and "data" in result and "accessToken" in result["data"]:
            self.current_token = result["data"]["accessToken"]
            self.token_ts = time.time()
            logger.info("Token 刷新成功")
            return self.current_token
        # 脱敏处理：不直接记录可能包含 accessToken 的完整响应
        safe_result = str(result)[:200] if result else "None"
        logger.error("Token 刷新失败（响应摘要）: %s", safe_result)
        return None

    async def token_loop(self):
        while True:
            await asyncio.sleep(60)
            if time.time() - self.token_ts >= self.token_ttl:
                t = await self.refresh_token()
                if t:
                    # 仅标记需要重启，由主循环的 restart_flag 检查来处理断线重连
                    # 不再主动关闭 WS — 让当前消息处理完成后再重连
                    self.restart_flag = True
                    return

    # ---- Cookie 自动刷新 + 健康检查 ----
    async def cookie_health_loop(self):
        """定期检查 Cookie 过期状态，主动刷新，失败时弹出浏览器登录（静默模式）"""
        refresh_margin = int(os.getenv("XIANYU_COOKIE_REFRESH_MARGIN", "300"))  # 提前刷新秒数
        consecutive_failures = 0
        max_failures_before_alert = 2
        # 自动登录冷却：避免短时间内反复弹出浏览器
        _last_auto_login = 0.0
        _auto_login_cooldown = 1800  # 30 分钟冷却（从 5 分钟延长，减少通知轰炸）
        # 通知限频：同类通知在窗口期内只发一次
        _last_notify_ts: dict[str, float] = {}
        _NOTIFY_COOLDOWN = 1800  # 同类通知 30 分钟内最多 1 次

        while True:
            # Cookie 失效时用退避间隔，不是固定 60 秒
            if not self._cookie_ok:
                # 退避: 60 → 120 → 300 → 600（与正常间隔齐平后不再增加）
                backoff = min(60 * (2 ** min(consecutive_failures, 3)), self.cookie_check_interval)
                check_wait = backoff
            else:
                check_wait = self.cookie_check_interval
            await asyncio.sleep(check_wait)
            try:
                # 0) 检测 Cookie 是否完全为空
                cookies_empty = not self.cookies_str or not self.cookies_str.strip()
                if cookies_empty:
                    # Cookie 完全为空，直接标记为失效并触发登录
                    consecutive_failures = max_failures_before_alert
                    expiring = True
                else:
                    # 1) 先用 has_login() API 验证真实登录状态
                    #    _m_h5_tk 解析仅作为辅助提前刷新的依据，不作为过期判断
                    current_cookies = dict(self.api.client.cookies.items())
                    expiring = is_cookie_expiring(current_cookies, margin_seconds=refresh_margin)

                if not expiring:
                    # Cookie 还没过期，正常
                    if not self._cookie_ok:
                        self._cookie_ok = True
                        consecutive_failures = 0
                        self._notify_throttled(_last_notify_ts, "cookie_ok", "Cookie 已恢复有效", _NOTIFY_COOLDOWN)
                    continue

                # 2) Cookie 即将过期或已过期，先尝试 CookieCloud 自动同步
                cc_ok = False
                try:
                    from src.xianyu.cookie_cloud import get_cookie_cloud_manager
                    cc_mgr = get_cookie_cloud_manager()
                    if cc_mgr.enabled:
                        cc_ok = await cc_mgr.sync_once()
                        if cc_ok and cc_mgr._last_cookie_str:
                            # CookieCloud 同步成功，更新内存状态
                            new_cookie_str = cc_mgr._last_cookie_str
                            self.cookies_str = new_cookie_str
                            self.cookies = trans_cookies(new_cookie_str)
                            self.myid = self.cookies.get("unb", self.myid)
                            consecutive_failures = 0
                            if not self._cookie_ok:
                                self._cookie_ok = True
                                self._notify_throttled(_last_notify_ts, "cookie_ok", "Cookie 已通过 CookieCloud 自动恢复", _NOTIFY_COOLDOWN)
                            else:
                                logger.info("Cookie 已通过 CookieCloud 自动更新")
                            continue
                except Exception as e:
                    logger.debug("CookieCloud 同步尝试失败，回退到传统方式: %s", e)

                # 3) CookieCloud 失败或未启用，回退到传统 has_login 刷新
                if not cookies_empty:
                    logger.info("Cookie 即将过期，尝试自动刷新...")
                    ok = await refresh_cookies_via_session(self.api)
                else:
                    ok = False

                if ok:
                    # 刷新成功 → 同步到 XianyuLive 内存状态
                    new_cookie_str = build_cookie_str(self.api.client)
                    self.cookies_str = new_cookie_str
                    self.cookies = trans_cookies(new_cookie_str)
                    self.myid = self.cookies.get("unb", self.myid)

                    # 写回 .env（下次重启也能用新 cookie）
                    await asyncio.to_thread(update_env_file, new_cookie_str)

                    consecutive_failures = 0
                    if not self._cookie_ok:
                        self._cookie_ok = True
                        self._notify_throttled(_last_notify_ts, "cookie_ok", "Cookie 自动刷新成功", _NOTIFY_COOLDOWN)
                    else:
                        logger.info("Cookie 自动刷新成功")
                else:
                    # 刷新失败
                    if not cookies_empty:
                        consecutive_failures += 1
                    logger.warning("Cookie 刷新失败 (%d/%d)", consecutive_failures, max_failures_before_alert)

                    # 连续失败达到阈值且不在冷却期内，才触发自动登录
                    if consecutive_failures >= max_failures_before_alert:
                        self._cookie_ok = False
                        now = time.time()
                        if now - _last_auto_login >= _auto_login_cooldown:
                            _last_auto_login = now
                            logger.info("Cookie 已失效，自动弹出浏览器登录...")
                            # 静默模式：只记日志，不发 Telegram 通知（用户已明确要求静默）
                            login_ok = await self._auto_browser_login()
                            if login_ok:
                                self._cookie_ok = True
                                consecutive_failures = 0
                                logger.info("扫码登录成功，Cookie 已自动更新")
                            else:
                                # 登录失败也只记日志，不轰炸用户
                                logger.warning("自动登录未完成，等待下一轮重试")
                        else:
                            remaining = int(_auto_login_cooldown - (now - _last_auto_login))
                            logger.info("自动登录冷却中，%ds 后可再次尝试", remaining)

            except Exception as e:
                logger.warning("Cookie 健康检查异常: %s", e)

    def _notify_throttled(self, last_ts: dict[str, float], event_type: str, message: str, cooldown: float):
        """限频通知：同类事件在 cooldown 秒内只发一次 Telegram 通知"""
        now = time.time()
        if now - last_ts.get(event_type, 0) >= cooldown:
            last_ts[event_type] = now
            self.notifier.notify_health(event_type, message)
        else:
            logger.info("[通知限频] %s: %s", event_type, message)

    async def _auto_browser_login(self) -> bool:
        """Cookie 过期时自动登录。静默模式：不发任何 Telegram 通知。

        方案1: Playwright 浏览器登录（自动提取 Cookie）— 弹出可见浏览器窗口
        方案2: 等待 .env 手动更新

        返回 True 表示登录成功且 Cookie 已更新。
        """
        # 方案1: Playwright 浏览器登录 — 直接弹出可见浏览器窗口让用户扫码
        try:
            import subprocess

            script_path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "xianyu_login.py")
            if os.path.exists(script_path):

                def _run_login():
                    # 使用可见模式（不加 --headless），让用户能看到并扫码
                    result = subprocess.run(
                        [sys.executable, script_path, "--quiet"],
                        capture_output=True,
                        text=True,
                        timeout=360,
                        cwd=os.path.dirname(os.path.dirname(script_path)),
                    )
                    return result.returncode == 0

                ok = await asyncio.to_thread(_run_login)
                if ok:
                    return await self._reload_cookies_from_env()
                logger.warning("Playwright 登录失败")
            else:
                logger.warning("登录脚本不存在")
        except subprocess.TimeoutExpired:
            logger.warning("Playwright 登录超时")
        except Exception as e:
            logger.warning("Playwright 登录异常: %s", e)

        # 方案2: 静默等待 .env 更新（不发通知，不弹弹窗）
        return await self._native_browser_login()

    async def _native_browser_login(self) -> bool:
        """静默等待 .env 中 Cookie 更新（用户通过其他方式登录后自动检测恢复）。

        完全静默：不发任何通知/弹窗/声音。只在后台轮询 .env 文件变化。
        """
        logger.info("等待 .env 中 Cookie 更新（静默模式，不发通知）...")

        # 轮询等待 .env 中 Cookie 更新，最多等 15 分钟
        old_cookies = self.cookies_str
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", ".env")

        for i in range(90):  # 每 10 秒检查一次，共 15 分钟
            await asyncio.sleep(10)
            # 读取 .env 检查 Cookie 是否更新
            if os.path.exists(env_path):
                try:
                    with open(env_path, encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("XIANYU_COOKIES="):
                                new_cookies = line.strip().split("=", 1)[1]
                                if new_cookies and new_cookies != old_cookies:
                                    logger.info("检测到 .env 中 Cookie 已更新，自动恢复...")
                                    self.cookies_str = new_cookies
                                    self.cookies = trans_cookies(new_cookies)
                                    self.myid = self.cookies.get("unb", self.myid)
                                    self.api.client.cookies.update(self.cookies)
                                    self.restart_flag = True
                                    return True
                except Exception as e:
                    logger.debug("读取 .env 异常: %s", e)

        logger.warning("等待 Cookie 更新超时（15 分钟）")
        return False

    async def _reload_cookies_from_env(self) -> bool:
        """从 .env 重新加载 Cookie 到内存状态。登录脚本成功后调用。"""
        try:
            logger.info("浏览器登录成功，重新加载 Cookie...")
            from dotenv import load_dotenv

            env_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", ".env")
            if os.path.exists(env_path):
                load_dotenv(env_path, override=True)
            new_cookies = os.getenv("XIANYU_COOKIES", "")
            if new_cookies and new_cookies != self.cookies_str:
                self.cookies_str = new_cookies
                self.cookies = trans_cookies(new_cookies)
                self.myid = self.cookies.get("unb", self.myid)
                self.api.client.cookies.update(self.cookies)
                self.restart_flag = True
                return True
            else:
                logger.warning("登录脚本执行成功但 Cookie 未变化")
                return False
        except Exception as e:
            logger.error("重新加载 Cookie 异常: %s", e)
            return False

    # ---- 每日日报 ----
    async def daily_report_loop(self):
        """每天 21:00 推送闲鱼日报"""
        while True:
            now = now_et()
            # 计算到今天 21:00 的秒数（美东时间）
            target = now.replace(hour=21, minute=0, second=0, microsecond=0)
            if now >= target:
                # 已过 21:00，等到明天
                target = target + timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            await asyncio.sleep(wait_secs)
            try:
                stats = self.ctx.daily_stats()
                if stats["consultations"] > 0 or stats["orders"] > 0:
                    self.notifier.notify_daily_report(stats)
                    logger.info("日报已推送: %s", stats)
                else:
                    logger.info("今日无咨询/订单，跳过日报")
            except Exception as e:
                logger.error("日报推送异常: %s", e)

    # ---- 心跳 ----
    async def heartbeat_loop(self, ws):
        while True:
            now = time.time()
            if now - self.last_hb_time >= self.hb_interval:
                try:
                    await ws.send(json.dumps({"lwp": "/!", "headers": {"mid": generate_mid()}}))
                except Exception as e:
                    logger.warning("心跳发送失败: %s", e)
                    break
                self.last_hb_time = now

                # 清理超过 1 小时的聊天速率记录，防止内存无限增长
                async with self._state_lock:
                    stale_chats = [cid for cid, ts_list in self._msg_timestamps.items()
                                   if not ts_list or ts_list[-1] < now - 3600]
                    for cid in stale_chats:
                        del self._msg_timestamps[cid]

            if now - self.last_hb_resp > self.hb_interval + self.hb_timeout:
                # 心跳超时 — 主动关闭 WS 触发重连，防止连接僵死
                logger.warning("心跳超时，主动关闭 WebSocket 触发重连")
                self.restart_flag = True
                try:
                    await ws.close()
                except Exception as e:
                    logger.debug("心跳超时关闭 WS 异常: %s", e)
                break
            await asyncio.sleep(1)

    # ---- 人工接管（加锁保护 manual_chats 并发读写）----
    async def is_manual(self, cid: str) -> bool:
        async with self._state_lock:
            if cid not in self.manual_chats:
                return False
            if time.time() - self.manual_chats[cid] > self.manual_timeout:
                self.manual_chats.pop(cid, None)
                return False
            return True

    async def toggle_manual(self, cid: str) -> str:
        async with self._state_lock:
            # 内联 is_manual 逻辑避免嵌套锁
            is_man = False
            if cid in self.manual_chats:
                if time.time() - self.manual_chats[cid] > self.manual_timeout:
                    self.manual_chats.pop(cid, None)
                else:
                    is_man = True
            if is_man:
                self.manual_chats.pop(cid, None)
                return "auto"
            self.manual_chats[cid] = time.time()
            return "manual"

    # ---- 发消息 ----
    async def send_msg(self, ws, cid: str, toid: str, text: str):
        payload = {"contentType": 1, "text": {"text": text}}
        b64 = base64.b64encode(json.dumps(payload).encode()).decode()
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{cid}@goofish",
                    "conversationType": 1,
                    "content": {"contentType": 101, "custom": {"type": 1, "data": b64}},
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {"actualReceivers": [f"{toid}@goofish", f"{self.myid}@goofish"]},
            ],
        }
        await ws.send(json.dumps(msg))

    # ---- 初始化连接 ----
    async def init_ws(self, ws):
        if not self.current_token or time.time() - self.token_ts >= self.token_ttl:
            await self.refresh_token()
        if not self.current_token:
            raise RuntimeError("无法获取 token")
        reg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": self._app_key,
                "token": self.current_token,
                "ua": XIANYU_USER_AGENT + " DingTalk(2.1.5)",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid(),
            },
        }
        await ws.send(json.dumps(reg))
        await asyncio.sleep(1)
        ack = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "pipeline": "sync",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": int(time.time() * 1000) * 1000,
                    "seq": 0,
                    "timestamp": int(time.time() * 1000),
                }
            ],
        }
        await ws.send(json.dumps(ack))
        logger.info("闲鱼 WebSocket 连接注册完成")

    # ---- 消息分类 ----
    @staticmethod
    def _is_sync_pkg(d: dict) -> bool:
        try:
            return bool(d.get("body", {}).get("syncPushPackage", {}).get("data"))
        except Exception as e:  # noqa: F841
            return False

    @staticmethod
    def _is_chat_msg(m: dict) -> bool:
        try:
            return isinstance(m.get("1"), dict) and "10" in m["1"] and "reminderContent" in m["1"]["10"]
        except Exception as e:  # noqa: F841
            return False

    # ---- 订单状态检测 ----
    ORDER_STATUSES = {
        "等待买家付款": "pending_payment",
        "等待卖家发货": "paid",
        "交易关闭": "closed",
        "交易成功": "completed",
        "退款成功": "refunded",
        "退款中": "refunding",
    }

    def _check_order(self, message: dict) -> str | None:
        try:
            reminder = message.get("3", {}).get("redReminder", "")
            return self.ORDER_STATUSES.get(reminder)
        except Exception as e:  # noqa: F841
            return None

    # ---- 商品描述构建 ----
    def _build_item_desc(self, info: dict) -> str:
        skus = []
        for sku in info.get("skuList", []):
            specs = " ".join(p.get("valueText", "") for p in sku.get("propertyList", []) if p.get("valueText"))
            price = round(float(sku.get("price", 0)) / 100, 2)
            skus.append({"spec": specs or "默认", "price": price, "stock": sku.get("quantity", 0)})
        valid = [s["price"] for s in skus if s["price"] > 0]
        if valid:
            pr = f"¥{min(valid)}" if min(valid) == max(valid) else f"¥{min(valid)}-¥{max(valid)}"
        else:
            pr = f"¥{round(float(info.get('soldPrice', 0)), 2)}"
        return json.dumps(
            {
                "title": info.get("title", ""),
                "desc": info.get("desc", ""),
                "price": pr,
                "stock": info.get("quantity", 0),
                "skus": skus,
            },
            ensure_ascii=False,
        )

    # ---- 核心消息处理 ----
    async def handle_message(self, data: dict, ws):
        try:
            # ACK
            if "headers" in data and "mid" in data["headers"]:
                ack = {"code": 200, "headers": {"mid": data["headers"]["mid"], "sid": data["headers"].get("sid", "")}}
                await ws.send(json.dumps(ack))

            if not self._is_sync_pkg(data):
                return

            # 安全地提取四层嵌套数据（外部 WebSocket 格式不可控）
            try:
                sync = data["body"]["syncPushPackage"]["data"][0]
            except (KeyError, IndexError, TypeError):
                logger.debug("闲鱼 WebSocket 消息格式异常，跳过")
                return
            if "data" not in sync:
                return

            raw = sync["data"]
            try:
                decoded = base64.b64decode(raw).decode()
                json.loads(decoded)
                return  # 明文系统消息，跳过
            except Exception as e:  # noqa: F841
                message = json.loads(decrypt(raw))

            # 订单检测
            order_status = self._check_order(message)
            if order_status:
                uid = message.get("1", "").split("@")[0] if isinstance(message.get("1"), str) else ""
                logger.info("订单事件: %s (用户: %s)", order_status, uid)
                if order_status == "paid":
                    # 先获取上下文，生成 order_id（后续 record_order / process_order 共用）
                    recent_item = self.ctx.get_recent_item_id(uid) or ""
                    order_id = f"xy_{uid}_{uuid.uuid4().hex[:12]}"

                    # 买家已付款 → 记录订单 + 标记转化 + 通知
                    # 从商品信息中提取价格，用于利润核算
                    order_amount = 0.0
                    if recent_item:
                        _item = self.ctx.get_item(recent_item)
                        if _item:
                            # 优先从 SKU 列表取价（单位：分，需 /100）
                            for _sku in _item.get("skuList", []):
                                _p = float(_sku.get("price", 0)) / 100
                                if _p > 0:
                                    order_amount = _p
                                    break
                            # 兜底：取 soldPrice（单位：元）
                            if order_amount == 0:
                                order_amount = float(_item.get("soldPrice", 0))
                    self.ctx.record_order(
                        chat_id=str(uid),
                        user_id=uid,
                        item_id=recent_item or "",
                        status="等待卖家发货",
                        amount=order_amount,
                    )
                    self.ctx.mark_converted(str(uid), recent_item or "")
                    self.notifier.notify_order(
                        {
                            "user_id": uid,
                            "item_id": recent_item,
                            "status": "买家已付款，请接手远程部署",
                            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )

                    # 发射订单支付事件到 EventBus — 触发主动通知引擎提醒发货
                    try:
                        from src.core.event_bus import EventType, get_event_bus

                        _item_title = ""
                        if recent_item:
                            _cached = self.ctx.get_item(recent_item)
                            if _cached:
                                _item_title = _cached.get("title", "")[:50]
                        await get_event_bus().publish(
                            EventType.XIANYU_ORDER_PAID,
                            {
                                "item_name": _item_title or recent_item or "未知商品",
                                "amount": order_amount,
                                "buyer_id": uid,
                            },
                            source="xianyu_live",
                        )
                    except Exception as e:
                        logger.warning("[闲鱼] 发射订单事件失败: %s", e)

                    # HI-580: 自动发货拆为后台任务，不阻塞消息处理
                    if recent_item:
                        task = asyncio.create_task(
                            self._delayed_auto_ship(ws, order_id, recent_item, uid)
                        )
                        task.add_done_callback(self._log_bg_task_error)

                    # 自动创建 License 并通知（原有逻辑保留）
                    await self._auto_create_license(uid, ws)
                elif order_status == "refunded":
                    # 退款成功 → 自动吊销 License
                    await self._auto_revoke_license(uid)
                return

            # 非聊天消息
            if not self._is_chat_msg(message):
                return

            info = message["1"]
            create_time = int(info["5"])
            meta = info["10"]
            sender_name = meta.get("reminderTitle", "")
            sender_id = meta.get("senderUserId", "")
            content = meta.get("reminderContent", "")
            url_info = meta.get("reminderUrl", "")
            item_id = ""
            if "itemId=" in url_info:
                item_id = url_info.split("itemId=")[1].split("&")[0]
            chat_id = info["2"].split("@")[0]

            # 消息速率限制（加锁保护 _msg_timestamps 并发写入）
            now_ts = time.time()
            async with self._state_lock:
                ts_list = self._msg_timestamps.setdefault(chat_id, [])
                ts_list[:] = [t for t in ts_list if now_ts - t < 60]
                if len(ts_list) >= self.MAX_MSGS_PER_MINUTE:
                    logger.warning("Rate limit hit for chat %s (%d msgs/min)", chat_id, len(ts_list))
                    return
                ts_list.append(now_ts)

            # 过期消息
            if time.time() * 1000 - create_time > self.msg_expire:
                return

            # 系统消息
            if content.strip().startswith("[") and content.strip().endswith("]"):
                return

            # 卖家自己的消息
            if sender_id == self.myid:
                if content.strip() in self.toggle_kw:
                    mode = await self.toggle_manual(chat_id)
                    logger.info("%s 会话 %s", "🔴 人工接管" if mode == "manual" else "🟢 恢复自动", chat_id)
                    return
                self.ctx.add_message(chat_id, self.myid, item_id, "assistant", content)
                return

            logger.info("买家 %s(%s) 商品 %s: %s", sender_name, sender_id, item_id, content)

            # 咨询追踪
            self.ctx.track_consultation(chat_id, sender_id, sender_name, item_id, content)

            # 首次咨询通知（加锁保护 _notified_chats 并发写入）
            notify_key = f"{chat_id}:{item_id}"
            should_notify = False
            async with self._state_lock:
                if notify_key not in self._notified_chats:
                    self._notified_chats[notify_key] = None
                    # HI-578: FIFO 逐出最旧条目，避免 clear() 导致重复通知轰炸
                    while len(self._notified_chats) > self._NOTIFIED_CHATS_MAX:
                        self._notified_chats.popitem(last=False)
                    should_notify = True
            if should_notify:
                self.notifier.notify_consultation(sender_name, sender_id, item_id, content)

            # 人工接管
            if await self.is_manual(chat_id):
                logger.info("🔴 会话 %s 人工接管中，跳过", chat_id)
                self.ctx.add_message(chat_id, sender_id, item_id, "user", content)
                return

            # 快速回复（不走 LLM，省 token 秒回）
            quick = _quick_reply(content)
            if quick:
                self.ctx.add_message(chat_id, sender_id, item_id, "user", content)
                self.ctx.add_message(chat_id, self.myid, item_id, "assistant", quick)
                logger.info("快速回复: %s", quick)
                if self.simulate_typing:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                await self.send_msg(ws, chat_id, sender_id, quick)
                return

            # 获取商品信息
            item_info = self.ctx.get_item(item_id)
            if not item_info and item_id:
                result = await self.api.get_item_info(item_id)
                if result and "data" in result and "itemDO" in result["data"]:
                    item_info = result["data"]["itemDO"]
                    self.ctx.save_item(item_id, item_info)
            item_desc = self._build_item_desc(item_info) if item_info else "OpenClaw 远程部署服务"

            # ---- 底价自动接受 ----
            floor = None  # 安全修复: 在 if 块外初始化，防止后续引用时 NameError
            if item_id:
                floor = self.ctx.get_floor_price(item_id)
                if floor is not None:
                    buyer_price = _extract_price(content)
                    if buyer_price is not None:
                        # 自动接受上限：优先用商品标价，兜底用底价的10倍
                        # 目的是防止价格提取错误（如把手机号当价格）导致误接受
                        list_price = float(item_info.get("soldPrice", 0)) if item_info else 0
                        accept_ceiling = list_price if list_price > floor else floor * 10
                        if buyer_price >= floor and buyer_price <= accept_ceiling:
                            # 买家出价 >= 底价 → 自动接受
                            accept_reply = "好的，这个价格可以接受！直接拍下就行～"
                            self.ctx.add_message(chat_id, sender_id, item_id, "user", content)
                            self.ctx.incr_bargain(chat_id)
                            self.ctx.add_message(chat_id, self.myid, item_id, "assistant", accept_reply)
                            logger.info("底价自动接受: 买家出价 %s >= 底价 %s", buyer_price, floor)
                            if self.simulate_typing:
                                await asyncio.sleep(random.uniform(0.5, 1.5))
                            await self.send_msg(ws, chat_id, sender_id, accept_reply)
                            return
                        elif buyer_price >= floor * 0.9:
                            # 接近底价（差 10% 以内）→ 注入底价上下文让 AI 参考
                            logger.info("接近底价: 买家出价 %s, 底价 %s, 交给 AI 处理", buyer_price, floor)

            # 注入底价到 AI 上下文（防止 AI 在不知道底价的情况下同意低于底价的报价）
            # 使用上面已查询的 floor 变量，避免重复数据库查询
            if item_id and floor is not None:
                item_desc += f"\n⚠️ 底价: ¥{floor}，严总设定的底线价格，低于此价格的报价必须礼貌拒绝，不可同意"

            # 对买家消息进行安全消毒（防止 prompt injection / XSS / 命令注入）
            # 安全策略: fail-close — 消毒失败时跳过本条消息，防止恶意输入
            try:
                from src.core.security import get_security_gate

                _sec = get_security_gate()
                content = _sec.sanitize_input(content)
            except Exception as _san_err:
                logger.warning("闲鱼消息消毒失败（fail-close，跳过本条消息）: %s", _san_err)
                # HI-735: 消毒失败时给买家一个兜底回复，避免完全无响应
                try:
                    await self.send_msg(ws, chat_id, sender_id, "亲，消息没收到呢，麻烦重新发一下哦～")
                except Exception:
                    pass
                return

            # AI 回复（直接异步调用 LiteLLM Router）
            context = self.ctx.get_context(chat_id)
            reply = await self.bot.agenerate_reply(
                content, item_desc, context, item_id=item_id or "", user_id=sender_id
            )

            if reply == "-":
                logger.info("无需回复: %s", content)
                return

            self.ctx.add_message(chat_id, sender_id, item_id, "user", content)

            if self.bot.last_intent == "price":
                self.ctx.incr_bargain(chat_id)

            self.ctx.add_message(chat_id, self.myid, item_id, "assistant", reply)
            logger.info("AI 回复: %s", reply)

            # 模拟打字延迟
            if self.simulate_typing:
                delay = min(random.uniform(0, 1) + len(reply) * random.uniform(0.1, 0.25), 8.0)
                await asyncio.sleep(delay)

            await self.send_msg(ws, chat_id, sender_id, reply)

        except Exception as e:
            logger.error("消息处理异常: %s", e, exc_info=True)

    # ---- HI-580: 自动发货后台任务 ----
    async def _delayed_auto_ship(self, ws, order_id: str, item_id: str, buyer_id: str):
        """延时自动发货后台任务（HI-580: 不阻塞消息主路径）"""
        try:
            from src.xianyu.auto_shipper import AutoShipper

            if not hasattr(self, "_shipper"):
                self._shipper = AutoShipper()
            # 延时发货(防风控)
            rule = self._shipper.get_rule(item_id)
            delay = rule.get("delay_seconds", 30) if rule else 30
            if delay > 0:
                await asyncio.sleep(min(delay, 120))

            ship_result = self._shipper.process_order(
                order_id=order_id,
                item_id=item_id,
                buyer_id=buyer_id,
            )
            if ship_result.get("success"):
                # 通过上下文管理器获取正确的 chat_id（buyer_id != chat_id）
                _ship_chat_id = self.ctx.get_latest_chat_id(buyer_id) or buyer_id
                await self.send_msg(ws, _ship_chat_id, buyer_id, ship_result["message"])
                logger.info(
                    "[自动发货] 成功: buyer=%s, item=%s, 剩余=%d",
                    buyer_id, item_id, ship_result["remaining"],
                )
                self.notifier.notify_order({
                    "user_id": buyer_id,
                    "item_id": item_id,
                    "status": f"✅ 已自动发货 (库存剩余{ship_result['remaining']})",
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
                if "low_stock_warning" in ship_result:
                    self.notifier.notify_health("low_stock", ship_result["low_stock_warning"])
            else:
                logger.info("[自动发货] 跳过: %s", ship_result.get("reason", "无卡券"))
        except Exception as e:
            logger.error("[自动发货] 后台任务异常: %s", e)

    @staticmethod
    def _log_bg_task_error(task: asyncio.Task) -> None:
        """记录后台任务异常"""
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("[闲鱼] 后台任务异常: %s", exc, exc_info=exc)

    # ---- 自动创建 License ----
    async def _auto_create_license(self, buyer_id: str, ws):
        """买家付款后自动创建离线License并通过闲鱼消息发送"""
        if not self._license_mgr:
            logger.info("LicenseManager 不可用，跳过自动创建")
            return
        try:
            username = f"xy_{buyer_id[-8:]}"
            password = secrets.token_urlsafe(8)
            order_id = f"xy_{buyer_id}_{int(time.time())}"
            key = self._license_mgr.create_license(
                username=username,
                password=password,
                xianyu_order_id=order_id,
                max_devices=2,
                days=365,
                notes=f"闲鱼自动创建 buyer={buyer_id}",
            )
            # 通过闲鱼消息发给买家（离线Key，不需要用户名密码）
            # 百度网盘链接和提取码必须在 .env 中配置
            baidu_link = os.getenv("BAIDU_PAN_LINK", "")
            baidu_code = os.getenv("BAIDU_PAN_CODE", "")
            if not baidu_link or not baidu_code or "PLACEHOLDER" in baidu_link:
                logger.error("BAIDU_PAN_LINK 或 BAIDU_PAN_CODE 未配置，无法发送部署包下载信息")
                baidu_link = "[未配置-请联系客服]"
                baidu_code = "[未配置]"
            deploy_msg = (
                f"感谢购买 OpenClaw 一键部署包！\n\n"
                f"下载地址：\n"
                f"{baidu_link}\n"
                f"提取码: {baidu_code}\n\n"
                f"您的激活码：\n"
                f"{key}\n\n"
                f"使用步骤：\n"
                f"1. 复制上方链接到浏览器下载\n"
                f"2. 解压后双击【启动安装器】\n"
                f"3. 浏览器自动打开，粘贴上方激活码\n"
                f"4. 填写Telegram Bot Token即可\n\n"
                f"有问题随时联系我！"
            )
            # 找到与该买家的 chat_id（通过封装层查询，不直接操作数据库）
            chat_id_for_buyer = self.ctx.get_latest_chat_id(buyer_id)
            if chat_id_for_buyer:
                await self.send_msg(ws, chat_id_for_buyer, buyer_id, deploy_msg)
            self.notifier.notify_license_created(buyer_id, key, username, password)
            # 日志中脱敏 License Key，防止完整密钥泄露到日志文件
            logger.info("License 自动创建: %s...%s (订单: %s)", key[:4], key[-4:], order_id)
        except Exception as e:
            logger.error("自动创建 License 失败: %s", e)
            self.notifier.notify_health("error", f"自动创建 License 失败: {e}")

    async def _auto_revoke_license(self, buyer_id: str):
        """退款后自动吊销 License"""
        if not self._license_mgr:
            return
        try:
            # 安全修复: 使用精确匹配替代 LIKE 模糊匹配，防止短 buyer_id 误匹配其他用户的 License
            with self._license_mgr._conn() as c:
                row = c.execute(
                    "SELECT license_key FROM licenses WHERE xianyu_order_id = ? AND status='active'",
                    (buyer_id,),
                ).fetchone()
                # 如果精确匹配无结果，尝试 xianyu_buyer_id 字段（兼容旧数据）
                if not row:
                    row = c.execute(
                        "SELECT license_key FROM licenses WHERE xianyu_buyer_id = ? AND status='active'",
                        (buyer_id,),
                    ).fetchone()
            if row:
                key = row[0]
                self._license_mgr.revoke_license(key)
                self.notifier.notify_health("revoke", f"退款检测：已自动吊销 License {key[:12]}...")
                # 日志中脱敏 License Key，防止完整密钥泄露到日志文件
                logger.info("退款自动吊销: %s...%s (buyer: %s)", key[:4], key[-4:], buyer_id)
            else:
                logger.warning("未找到 buyer_id=%s 对应的 License", buyer_id)
        except Exception as e:
            logger.error("自动吊销 License 失败: %s", e)

    # ---- 主循环 ----
    async def run(self):
        self.notifier.notify_health("start", f"闲鱼 AI 客服启动 (卖家ID: {self.myid})")
        reconnect_count = 0  # 连续失败次数（成功后重置）
        total_reconnects = 0  # 累计重连总次数（不重置，用于监控）
        CIRCUIT_BREAKER_LIMIT = 50  # 熔断阈值：连续失败此次数后进入冷却
        CIRCUIT_BREAKER_COOLDOWN = 600  # 熔断冷却时间（秒）= 10 分钟
        _notify_suppressed = False  # 通知是否已被抑制（超过上限后不再推送 Telegram）
        _NOTIFY_ESCALATION = [5, 15, 30, 50]  # 累计重连达到这些次数时推送 Telegram，之后静默

        # 启动独立的 Cookie 健康检查任务（不依赖 WS 连接，确保 Cookie 失效时也能弹登录窗口）
        def _bg_health_cb(t):
            if not t.cancelled() and t.exception():
                logger.error("Cookie 健康检查任务异常: %s", t.exception())

        _cookie_health_task = asyncio.create_task(self.cookie_health_loop())
        _cookie_health_task.add_done_callback(_bg_health_cb)

        while True:
            self.restart_flag = False

            # 如果 Cookie 为空或只是占位符，等待 cookie_health_loop 弹出登录窗口并获取到真正的 Cookie
            if not self.cookies_str or self.cookies_str.strip() in ("", "placeholder=1"):
                logger.info("Cookie 为空，等待登录弹窗获取 Cookie（60 秒后重试）...")
                await asyncio.sleep(60)
                # 重新检查（cookie_health_loop 可能已经通过自动登录更新了 cookies_str）
                continue

            try:
                headers = {
                    "Cookie": self.cookies_str,
                    "Host": "wss-goofish.dingtalk.com",
                    "Origin": "https://www.goofish.com",
                    "User-Agent": XIANYU_USER_AGENT,
                }
                async with websockets.connect(self.WSS_URL, extra_headers=headers) as ws:
                    self.ws = ws
                    await self.init_ws(ws)
                    self.last_hb_time = self.last_hb_resp = time.time()
                    if reconnect_count > 0:
                        self.notifier.notify_health(
                            "reconnect", f"第 {reconnect_count} 次重连成功 (累计 {total_reconnects} 次)"
                        )
                    reconnect_count = 0  # 连续失败计数归零（连上了）
                    _notify_suppressed = False  # 恢复通知能力

                    def _bg_task_cb(t):
                        if not t.cancelled() and t.exception():
                            logger.error("闲鱼后台任务异常: %s", t.exception())

                    hb_task = asyncio.create_task(self.heartbeat_loop(ws))
                    hb_task.add_done_callback(_bg_task_cb)
                    tk_task = asyncio.create_task(self.token_loop())
                    tk_task.add_done_callback(_bg_task_cb)
                    rp_task = asyncio.create_task(self.daily_report_loop())
                    rp_task.add_done_callback(_bg_task_cb)

                    async for raw in ws:
                        if self.restart_flag:
                            break
                        try:
                            data = json.loads(raw)
                            # 心跳响应
                            if data.get("code") == 200 and "headers" in data:
                                self.last_hb_resp = time.time()
                                continue
                            await self.handle_message(data, ws)
                        except json.JSONDecodeError:
                            logger.debug("WebSocket 消息 JSON 解析失败", exc_info=True)
                        except Exception as e:
                            logger.error("处理异常: %s", e)

                    # 取消 WS 相关后台任务并等待清理完成（cookie_health_loop 不取消，它是独立的）
                    for task in [hb_task, tk_task, rp_task]:
                        task.cancel()
                    await asyncio.gather(hb_task, tk_task, rp_task, return_exceptions=True)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket 连接关闭")
                reconnect_count += 1
                total_reconnects += 1
            except Exception as e:
                logger.error("连接异常: %s", e)
                reconnect_count += 1
                total_reconnects += 1

            # 告警逻辑：渐进式通知 — 在 5、15、30、50 次时推送 Telegram，之后只写日志
            if reconnect_count > 0 and reconnect_count % 5 == 0:
                logger.warning(
                    "❌ 闲鱼客服 [error] 连续重连 %d 次，可能存在网络或 Cookie 问题 (累计 %d 次)",
                    reconnect_count, total_reconnects,
                )
                # 只在关键节点推送 Telegram，避免通知轰炸
                if not _notify_suppressed and reconnect_count in _NOTIFY_ESCALATION:
                    self.notifier.notify_health(
                        "error",
                        f"连续重连 {reconnect_count} 次，可能存在网络或 Cookie 问题 (累计 {total_reconnects} 次)",
                    )
                    if reconnect_count >= _NOTIFY_ESCALATION[-1]:
                        _notify_suppressed = True
                        logger.info("重连通知已达上限 (%d 次)，后续仅写日志不推送 Telegram", reconnect_count)

            # 熔断器：连续失败超过阈值，暂停较长时间避免无意义重试
            if reconnect_count >= CIRCUIT_BREAKER_LIMIT:
                logger.error("连续重连 %d 次触发熔断，冷却 %d 秒", reconnect_count, CIRCUIT_BREAKER_COOLDOWN)
                logger.error(
                    "⚠️ 闲鱼客服熔断：连续重连 %d 次失败，暂停 %d 分钟 | 可能原因：Cookie 过期或网络中断",
                    reconnect_count, CIRCUIT_BREAKER_COOLDOWN // 60,
                )
                await asyncio.sleep(CIRCUIT_BREAKER_COOLDOWN)
                # 冷却后不重置 reconnect_count，让它继续累加
                # 这样下次熔断间隔保持一致，不会重新从 0 开始快速重试
                continue  # 跳过下方普通等待逻辑，直接重连

            wait = 0 if self.restart_flag else min(5 * reconnect_count, 60)
            if wait:
                logger.info("%ss 后重连 (第 %s 次)...", wait, reconnect_count)
                await asyncio.sleep(wait)

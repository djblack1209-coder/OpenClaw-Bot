"""订单通知模块 — 邮件 + Telegram 推送 + 日报 + 健康告警"""
import asyncio
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict

import httpx

logger = logging.getLogger(__name__)


class OrderNotifier:
    def __init__(self):
        # 邮件配置
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.qq.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "465"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.notify_email = os.getenv("NOTIFY_EMAIL", self.smtp_user)
        # Telegram 配置
        self.tg_token = os.getenv("NOTIFY_TG_TOKEN", "")
        self.tg_chat_id = os.getenv("NOTIFY_TG_CHAT_ID", "")

    def notify_order(self, order: Dict):
        """下单通知：同时发邮件和 Telegram"""
        user_id = order.get("user_id", "unknown")
        item_id = order.get("item_id", "unknown")
        status = order.get("status", "unknown")
        ts = order.get("ts", "")
        user_url = f"https://www.goofish.com/personal?userId={user_id}"
        item_url = f"https://www.goofish.com/item?id={item_id}"

        subject = f"[闲鱼订单] {status}"
        body = (
            f"订单状态: {status}\n"
            f"时间: {ts}\n"
            f"买家: {user_url}\n"
            f"商品: {item_url}\n"
            f"---\n"
            f"请尽快接手处理，开启远程部署。"
        )

        self._send_email(subject, body)
        self._send_telegram(f"🦞 {subject}\n\n{body}")

    def notify_consultation(self, user_name: str, user_id: str, item_id: str, message: str):
        """新买家咨询通知（仅 Telegram，不发邮件避免骚扰）"""
        text = (
            f"💬 闲鱼新咨询\n"
            f"买家: {user_name} (ID: {user_id})\n"
            f"商品: {item_id}\n"
            f"消息: {message[:200]}"
        )
        self._send_telegram(text)

    def notify_license_created(self, user_id: str, license_key: str, username: str, password: str):
        """License 自动创建通知"""
        # 脱敏处理：License Key 只显示首尾各4字符，密码只显示前2字符
        redacted_key = f"{license_key[:4]}...{license_key[-4:]}" if len(license_key) > 8 else "***"
        redacted_pw = f"{password[:2]}***" if len(password) >= 2 else "***"
        text = (
            f"🔑 License 已自动创建\n"
            f"买家: {user_id}\n"
            f"License: {redacted_key}\n"
            f"用户名: {username}\n"
            f"密码: {redacted_pw}\n"
            f"---\n"
            f"已通过闲鱼消息发送给买家"
        )
        self._send_telegram(text)

    def notify_health(self, event: str, detail: str = ""):
        """服务健康事件通知"""
        emoji = {"start": "🟢", "stop": "🔴", "reconnect": "🔄", "cookie_expired": "⚠️",
                 "cookie_ok": "✅", "error": "❌"}.get(event, "ℹ️")
        text = f"{emoji} 闲鱼客服 [{event}]\n{detail}" if detail else f"{emoji} 闲鱼客服 [{event}]"
        self._send_telegram(text)

    def notify_daily_report(self, stats: Dict):
        """每日销售/咨询日报"""
        text = (
            f"📊 闲鱼日报 [{stats['date']}]\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💬 咨询: {stats['consultations']} 人\n"
            f"📝 消息: {stats['messages']} 条\n"
            f"🛒 下单: {stats['orders']} 笔\n"
            f"💰 付款: {stats['paid']} 笔\n"
            f"📈 转化率: {stats['conversion_rate']}\n"
            f"━━━━━━━━━━━━━━━"
        )
        self._send_telegram(text)

    def _send_email(self, subject: str, body: str):
        if not self.smtp_user or not self.smtp_pass:
            logger.debug("邮件未配置，跳过")
            return
        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_user
            msg["To"] = self.notify_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as s:
                    s.login(self.smtp_user, self.smtp_pass)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
                    s.ehlo()
                    s.starttls()
                    s.ehlo()
                    s.login(self.smtp_user, self.smtp_pass)
                    s.send_message(msg)
            logger.info(f"邮件已发送: {subject}")
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")

    def _send_telegram(self, text: str):
        if not self.tg_token or not self.tg_chat_id:
            logger.debug("Telegram 通知未配置，跳过")
            return
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        payload = {
            "chat_id": self.tg_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        # 检测是否在异步上下文中
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # 异步上下文 — 在后台任务中用 httpx 异步发送，不阻塞事件循环
            asyncio.ensure_future(self._send_telegram_async(url, payload))
        else:
            # 同步上下文 — 用 httpx 同步客户端
            self._send_telegram_sync(url, payload)

    async def _send_telegram_async(self, url: str, payload: dict):
        """异步版 Telegram 通知发送（3 次重试 + 指数退避）"""
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        logger.info("Telegram 通知已发送")
                        return
                    logger.debug("[订单通知] 异步发送尝试 %d/3 HTTP %d: %s", attempt + 1, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.debug("[订单通知] 异步发送尝试 %d/3 失败: %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
        logger.warning("[订单通知] Telegram 异步 3 次重试均失败")

    async def send_qr_login(self, qr_png: bytes):
        """发送闲鱼登录二维码图片到 Telegram"""
        if not self.tg_token or not self.tg_chat_id:
            logger.debug("Telegram 未配置，无法发送二维码")
            return
        url = f"https://api.telegram.org/bot{self.tg_token}/sendPhoto"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    data={
                        "chat_id": self.tg_chat_id,
                        "caption": (
                            "🔐 闲鱼 Cookie 已过期，需要重新登录\n\n"
                            "请用 闲鱼 或 淘宝 APP 扫描上方二维码\n"
                            "扫码后在手机上确认登录\n\n"
                            "⏱️ 二维码有效期 5 分钟"
                        ),
                    },
                    files={"photo": ("xianyu_qr.png", qr_png, "image/png")},
                )
                if resp.status_code == 200:
                    logger.info("闲鱼登录二维码已发送到 Telegram")
                else:
                    logger.warning(f"发送二维码失败: HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"发送二维码到 Telegram 失败: {e}")

    def _send_telegram_sync(self, url: str, payload: dict):
        """同步版 Telegram 通知发送（3 次重试 + 指数退避）"""
        import time as _time
        for attempt in range(3):
            try:
                with httpx.Client(timeout=10) as client:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        logger.info("Telegram 通知已发送")
                        return
                    logger.debug("[订单通知] 同步发送尝试 %d/3 HTTP %d: %s", attempt + 1, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.debug("[订单通知] 同步发送尝试 %d/3 失败: %s", attempt + 1, e)
            if attempt < 2:
                _time.sleep(2 ** attempt)
        logger.warning("[订单通知] Telegram 同步 3 次重试均失败")

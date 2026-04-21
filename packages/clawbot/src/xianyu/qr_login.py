"""闲鱼 API 扫码登录 — 纯 API 实现，不弹浏览器

搬运自 GuDong2003/xianyu-auto-reply-fix 的 qr_login.py，
适配 OpenClaw 的 Telegram Bot + .env Cookie 管理。

流程：
1. 调 API 获取 _m_h5_tk
2. 调 API 获取登录参数
3. 调 API 生成二维码内容
4. 用 qrcode 库生成 PNG 图片
5. 通过 Telegram 发送给用户（或 macOS 弹窗展示）
6. 轮询状态直到用户扫码确认
7. 从响应 Cookie 中提取完整登录态
8. 写入 .env + 通知闲鱼进程热更新

使用示例:
    manager = QRLoginManager()
    result = await manager.login_via_telegram(bot, chat_id)
"""

import asyncio
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from io import BytesIO
from random import random
from typing import Any, Dict

import httpx
from loguru import logger
from src.utils import scrub_secrets


# 闲鱼护照 API 地址
_PASSPORT_HOST = "https://passport.goofish.com"
_API_MINI_LOGIN = f"{_PASSPORT_HOST}/mini_login.htm"
_API_GENERATE_QR = f"{_PASSPORT_HOST}/newlogin/qrcode/generate.do"
_API_QUERY_QR = f"{_PASSPORT_HOST}/newlogin/qrcode/query.do"
_API_H5_TK = "https://h5api.m.goofish.com/h5/mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get/1.0/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://passport.goofish.com/",
    "Origin": "https://passport.goofish.com",
}

# 超时配置
_TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=60.0)


class QRLoginManager:
    """纯 API 扫码登录管理器 — 不弹浏览器"""

    def __init__(self):
        self.cookies: Dict[str, str] = {}
        self.params: Dict[str, Any] = {}

    async def _get_m_h5_tk(self) -> Dict[str, str]:
        """步骤1: 获取 _m_h5_tk Cookie（签名用）"""
        data = {"bizScene": "home"}
        data_str = json.dumps(data, separators=(",", ":"))
        t = str(int(time.time() * 1000))
        app_key = "34839810"

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            # 先请求一次，从响应 Cookie 拿到 m_h5_tk
            resp = await client.get(_API_H5_TK, headers=_HEADERS)
            cookies = {k: v for k, v in resp.cookies.items()}
            self.cookies.update(cookies)

            m_h5_tk = cookies.get("m_h5_tk", "")
            token = m_h5_tk.split("_")[0] if "_" in m_h5_tk else ""

            # 生成签名
            sign_input = f"{token}&{t}&{app_key}&{data_str}"
            sign = hashlib.md5(sign_input.encode()).hexdigest()

            params = {
                "jsv": "2.7.2", "appKey": app_key, "t": t,
                "sign": sign, "v": "1.0", "type": "originaljson",
                "dataType": "json", "timeout": 20000,
                "api": "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get",
                "data": data_str,
            }

            # 二次请求确保 token 有效
            await client.post(_API_H5_TK, params=params,
                              headers=_HEADERS, cookies=self.cookies)

            return cookies

    async def _get_login_params(self) -> Dict[str, Any]:
        """步骤2: 获取二维码登录的表单参数"""
        params = {
            "lang": "zh_cn", "appName": "xianyu", "appEntrance": "web",
            "styleType": "vertical", "bizParams": "",
            "notLoadSsoView": False, "notKeepLogin": False,
            "isMobile": False, "qrCodeFirst": False,
            "stie": 77, "rnd": random(),
        }

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=_TIMEOUT
        ) as client:
            resp = await client.get(
                _API_MINI_LOGIN, params=params,
                cookies=self.cookies, headers=_HEADERS,
            )

            # 从页面 JS 中提取 loginFormData
            match = re.search(
                r"window\.viewData\s*=\s*(\{.*?\});", resp.text
            )
            if not match:
                raise RuntimeError("获取登录参数失败: 页面中未找到 viewData")

            view_data = json.loads(match.group(1))
            form_data = view_data.get("loginFormData")
            if not form_data:
                raise RuntimeError("获取登录参数失败: 未找到 loginFormData")

            form_data["umidTag"] = "SERVER"
            self.params.update(form_data)
            return form_data

    async def generate_qr_code(self) -> Dict[str, Any]:
        """生成二维码，返回 PNG 字节数据。

        Returns:
            {"success": True, "qr_png": bytes, "qr_content": str}
            或 {"success": False, "message": str}
        """
        try:
            # 1. 获取 m_h5_tk
            await self._get_m_h5_tk()
            logger.info("闲鱼 QR 登录: 获取 m_h5_tk 成功")

            # 2. 获取登录参数
            await self._get_login_params()
            logger.info("闲鱼 QR 登录: 获取登录参数成功")

            # 3. 请求生成二维码
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=_TIMEOUT
            ) as client:
                resp = await client.get(
                    _API_GENERATE_QR, params=self.params,
                    headers=_HEADERS,
                )
                result = resp.json()

                content_data = result.get("content", {}).get("data", {})
                if not result.get("content", {}).get("success"):
                    return {"success": False,
                            "message": f"二维码生成失败: {result}"}

                # 更新轮询参数
                self.params["t"] = content_data["t"]
                self.params["ck"] = content_data["ck"]

                qr_content = content_data["codeContent"]

            # 4. 生成二维码 PNG 图片
            import qrcode
            qr = qrcode.QRCode(
                version=5,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10, border=2,
            )
            qr.add_data(qr_content)
            qr.make()
            qr_img = qr.make_image()

            buf = BytesIO()
            qr_img.save(buf, format="PNG")
            qr_png = buf.getvalue()

            logger.info(f"闲鱼 QR 登录: 二维码已生成 ({len(qr_png)} bytes)")
            return {
                "success": True,
                "qr_png": qr_png,
                "qr_content": qr_content,
            }

        except Exception as e:
            logger.error(f"闲鱼 QR 登录: 生成二维码失败: {scrub_secrets(str(e))}")
            return {"success": False, "message": scrub_secrets(str(e))}

    async def poll_login_status(
        self, timeout: int = 300, interval: float = 1.5
    ) -> Dict[str, Any]:
        """轮询扫码状态，直到成功/过期/取消。

        Returns:
            {"success": True, "cookies_str": str, "unb": str}
            或 {"success": False, "status": "expired"/"cancelled"/"timeout"}
        """
        start = time.time()

        while time.time() - start < timeout:
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True, timeout=_TIMEOUT
                ) as client:
                    resp = await client.post(
                        _API_QUERY_QR,
                        data=self.params,
                        cookies=self.cookies,
                        headers=_HEADERS,
                    )
                    data = resp.json()
                    qr_status = (
                        data.get("content", {})
                        .get("data", {})
                        .get("qrCodeStatus", "")
                    )

                    if qr_status == "CONFIRMED":
                        # 检查是否有风控验证
                        if data.get("content", {}).get("data", {}).get("iframeRedirect"):
                            logger.warning("闲鱼 QR 登录: 账号被风控，需要手机验证")
                            # 更新 Cookie 继续等待（用户可能在手机上完成验证）
                            self.cookies.update(
                                {k: v for k, v in resp.cookies.items()}
                            )
                            await asyncio.sleep(interval)
                            continue

                        # 登录成功 — 从响应 Cookie 中提取
                        self.cookies.update(
                            {k: v for k, v in resp.cookies.items()}
                        )
                        unb = self.cookies.get("unb", "")
                        cookies_str = "; ".join(
                            f"{k}={v}" for k, v in self.cookies.items()
                        )
                        logger.info(
                            f"闲鱼 QR 登录: 扫码成功! UNB={unb}"
                        )
                        return {
                            "success": True,
                            "cookies_str": cookies_str,
                            "unb": unb,
                        }

                    elif qr_status == "SCANED":
                        logger.info("闲鱼 QR 登录: 已扫码，等待确认...")

                    elif qr_status == "EXPIRED":
                        logger.warning("闲鱼 QR 登录: 二维码已过期")
                        return {"success": False, "status": "expired"}

                    elif qr_status == "NEW":
                        pass  # 等待扫码

                    else:
                        logger.info(f"闲鱼 QR 登录: 状态 {qr_status}")
                        if qr_status not in ("NEW", "SCANED", "CONFIRMED"):
                            return {"success": False, "status": "cancelled"}

            except Exception as e:
                logger.debug(f"闲鱼 QR 登录: 轮询异常: {e}")

            await asyncio.sleep(interval)

        return {"success": False, "status": "timeout"}

    async def login_and_save(self) -> Dict[str, Any]:
        """完整登录流程: 生成二维码 → 轮询 → 保存 Cookie → 通知进程。

        Returns:
            {"success": True, "qr_png": bytes, ...}
        """
        # 生成二维码
        qr_result = await self.generate_qr_code()
        if not qr_result["success"]:
            return qr_result

        qr_png = qr_result["qr_png"]

        # 轮询状态
        login_result = await self.poll_login_status(timeout=300)
        if not login_result["success"]:
            return login_result

        # 保存到 .env
        cookies_str = login_result["cookies_str"]
        try:
            from src.xianyu.cookie_refresher import update_env_file
            update_env_file(cookies_str)
            logger.info("闲鱼 QR 登录: Cookie 已写入 .env")
        except Exception as e:
            logger.error(f"闲鱼 QR 登录: 写入 .env 失败: {scrub_secrets(str(e))}")

        # 通知闲鱼进程热更新
        try:
            result = subprocess.run(
                ["pgrep", "-f", "xianyu_main"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                for pid in result.stdout.strip().split("\n"):
                    if pid.strip():
                        os.kill(int(pid.strip()), signal.SIGUSR1)
                        logger.info(f"闲鱼 QR 登录: 已通知进程 PID={pid} 热更新")
        except Exception as e:
            logger.debug(f"闲鱼 QR 登录: 通知进程失败: {e}")

        login_result["qr_png"] = qr_png
        return login_result

    async def login_via_telegram(self, bot, chat_id: int) -> bool:
        """通过 Telegram 发送二维码并等待扫码登录。

        这是最推荐的使用方式：
        1. 生成二维码 → 发到 Telegram 聊天
        2. 用户用闲鱼/淘宝 APP 扫码
        3. 自动获取 Cookie 写入 .env
        4. 通知闲鱼进程热更新

        Args:
            bot: Telegram Bot 实例
            chat_id: 发送到的聊天 ID

        Returns:
            是否登录成功
        """
        # 生成二维码
        qr_result = await self.generate_qr_code()
        if not qr_result["success"]:
            await bot.send_message(
                chat_id,
                f"❌ 闲鱼登录二维码生成失败: {qr_result.get('message', '未知错误')}"
            )
            return False

        # 发送二维码到 Telegram
        qr_png = qr_result["qr_png"]
        try:
            from telegram import InputFile
            await bot.send_photo(
                chat_id,
                photo=InputFile(BytesIO(qr_png), filename="xianyu_login.png"),
                caption=(
                    "🔐 **闲鱼登录**\n\n"
                    "请用 **闲鱼** 或 **淘宝** APP 扫描上方二维码\n"
                    "扫码后在手机上确认登录\n\n"
                    "⏱️ 二维码有效期 5 分钟"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"发送二维码到 Telegram 失败: {e}")
            # 仅记录日志，不弹 Mac 窗口

        # 发送"等待中"消息
        wait_msg = await bot.send_message(
            chat_id, "⏳ 等待扫码中..."
        )

        # 轮询登录状态
        login_result = await self.poll_login_status(timeout=300)

        if login_result["success"]:
            # 保存 Cookie
            cookies_str = login_result["cookies_str"]
            try:
                from src.xianyu.cookie_refresher import update_env_file
                update_env_file(cookies_str)
            except Exception as e:
                logger.error(f"写入 .env 失败: {e}")

            # 通知进程热更新
            try:
                result = subprocess.run(
                    ["pgrep", "-f", "xianyu_main"],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    for pid in result.stdout.strip().split("\n"):
                        if pid.strip():
                            os.kill(int(pid.strip()), signal.SIGUSR1)
            except Exception as e:
                logger.warning("通知闲鱼进程刷新Cookie失败: %s", e)

            await bot.edit_message_text(
                "✅ 闲鱼登录成功！Cookie 已更新，客服正在自动恢复。",
                chat_id=chat_id,
                message_id=wait_msg.message_id,
            )
            return True
        else:
            status = login_result.get("status", "unknown")
            msg_map = {
                "expired": "二维码已过期，请重新发送 /xianyu_login",
                "cancelled": "登录已取消",
                "timeout": "等待超时，请重新发送 /xianyu_login",
            }
            await bot.edit_message_text(
                f"❌ 闲鱼登录失败: {msg_map.get(status, status)}",
                chat_id=chat_id,
                message_id=wait_msg.message_id,
            )
            return False

    # _show_qr_on_mac 已移除 — 不再弹 Mac 桌面窗口

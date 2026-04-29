"""闲鱼 API 封装 — Token/商品信息/登录状态（异步版，使用 httpx.AsyncClient）"""
import asyncio
import logging
import os
import re
import time

import httpx

from src.constants import XIANYU_USER_AGENT
from src.utils import scrub_secrets

from .utils import generate_sign, trans_cookies

logger = logging.getLogger(__name__)


class XianyuApis:
    """闲鱼 API 客户端 — 支持 async with 上下文管理器自动关闭连接"""

    def __init__(self, cookies_str: str = ""):
        # 将 cookie 字符串解析为字典，httpx 直接接受 dict 格式的 cookies
        self._cookies = trans_cookies(cookies_str) if cookies_str else {}
        self.client = httpx.AsyncClient(
            headers={
                "accept": "application/json",
                "origin": "https://www.goofish.com",
                "referer": "https://www.goofish.com/",
                "user-agent": XIANYU_USER_AGENT,
            },
            cookies=self._cookies,
            # 默认超时 30 秒，防止请求无限挂起
            timeout=httpx.Timeout(30.0),
            # 自动跟随重定向
            follow_redirects=True,
        )
        self._closed = False
        # 初始化后立即去重，防止从扁平化 Cookie 字符串导入时产生重复
        self._clear_dup_cookies()

    async def __aenter__(self):
        """支持 async with XianyuApis(...) as api: 用法"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器时自动关闭连接"""
        await self.close()
        return False

    def __del__(self):
        """析构时检查是否忘记关闭连接"""
        if not self._closed and hasattr(self, 'client'):
            logger.warning("[XianyuApis] 连接未正确关闭，可能存在 TCP 泄漏。请使用 async with 或显式调用 close()")

    # ------------------------------------------------------------------
    def _h5_token(self) -> str:
        """从 cookies 中提取 h5 token（用于签名计算）"""
        val = self.client.cookies.get("_m_h5_tk", "")
        return val.split("_")[0]

    def _clear_dup_cookies(self):
        """去除重复的 cookie — httpx CookieJar 可能存储多个同 name 不同 domain 的条目，
        发请求时会触发 'Multiple cookies exist' 错误。这里强制扁平化为纯 name→value 映射。
        """
        cleaned = {}
        # 遍历底层 jar 确保拿到所有条目
        try:
            for cookie in self.client.cookies.jar:
                cleaned[cookie.name] = cookie.value
        except Exception:
            # 降级：使用 items() 迭代
            for name, value in self.client.cookies.items():
                cleaned[name] = value
        self.client.cookies.clear()
        self.client.cookies.update(cleaned)

    def _update_env_cookies(self):
        """将当前 cookies 写回 .env 文件（原子写入，防止崩溃时损坏）"""
        import tempfile
        env_path = os.path.join(os.getcwd(), ".env")
        if not os.path.exists(env_path):
            return
        cookie_str = "; ".join(f"{name}={value}" for name, value in self.client.cookies.items())
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        if "XIANYU_COOKIES=" in content:
            content = re.sub(r"XIANYU_COOKIES=.*", f"XIANYU_COOKIES={cookie_str}", content)
            # 原子写入：先写临时文件，再替换（防止写入中途崩溃导致文件损坏）
            dir_name = os.path.dirname(env_path)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".env_tmp_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                os.replace(tmp_path, env_path)
            except Exception:
                # 清理临时文件
                try:
                    os.unlink(tmp_path)
                except OSError as e:
                    logger.debug("文件操作失败: %s", e)
                raise

    # ------------------------------------------------------------------
    async def has_login(self, retry: int = 0) -> bool:
        """检查登录状态（异步）"""
        if retry >= 2:
            return False
        try:
            resp = await self.client.post(
                "https://passport.goofish.com/newlogin/hasLogin.do",
                params={"appName": "xianyu", "fromSite": "77"},
                data={
                    "hid": self.client.cookies.get("unb", ""),
                    "ltl": "true",
                    "appName": "xianyu",
                    "appEntrance": "web",
                    "_csrf_token": self.client.cookies.get("XSRF-TOKEN", ""),
                    "fromSite": "77",
                    "documentReferer": "https://www.goofish.com/",
                    "defaultView": "hasLogin",
                    "deviceId": self.client.cookies.get("cna", ""),
                },
            )
            if resp.json().get("content", {}).get("success"):
                self._clear_dup_cookies()
                return True
        except Exception as e:
            logger.warning(f"hasLogin 异常: {scrub_secrets(str(e))}")
        await asyncio.sleep(0.5)
        return await self.has_login(retry + 1)

    # ------------------------------------------------------------------
    async def get_token(self, device_id: str, retry: int = 0, _refreshed: bool = False) -> dict:
        """获取 WebSocket 连接所需的 accessToken（异步）"""
        if retry >= 2:
            # 只允许刷新一次登录态后重试，防止无限递归
            if not _refreshed and await self.has_login():
                return await self.get_token(device_id, 0, _refreshed=True)
            logger.error("Cookie 已失效，无法获取 token")
            return {}
        t = str(int(time.time()) * 1000)
        xianyu_message_app_key = "".join(["444e9908", "a51d1cb2", "36a27862", "abc769c9"])
        data_val = f'{{"appKey":"{xianyu_message_app_key}","deviceId":"{device_id}"}}'
        params = {
            "jsv": "2.7.2", "appKey": "34839810", "t": t,
            "sign": generate_sign(t, self._h5_token(), data_val),
            "v": "1.0", "type": "originaljson", "accountSite": "xianyu",
            "dataType": "json", "timeout": "20000",
            "api": "mtop.taobao.idlemessage.pc.login.token",
            "sessionOption": "AutoLoginOnly",
        }
        try:
            resp = await self.client.post(
                "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/",
                params=params, data={"data": data_val},
            )
            rj = resp.json()
            ret = rj.get("ret", [])
            if any("SUCCESS" in r for r in ret):
                return rj
            # 服务端可能通过 Set-Cookie 下发新的 h5_tk，httpx 会自动存储
            if "set-cookie" in resp.headers:
                self._clear_dup_cookies()
        except Exception as e:
            logger.error(f"get_token 异常: {scrub_secrets(str(e))}")
        await asyncio.sleep(0.5)
        return await self.get_token(device_id, retry + 1, _refreshed=_refreshed)

    # ------------------------------------------------------------------
    async def get_item_info(self, item_id: str, retry: int = 0) -> dict:
        """获取闲鱼商品详情（异步）"""
        if retry >= 3:
            return {}
        t = str(int(time.time()) * 1000)
        data_val = f'{{"itemId":"{item_id}"}}'
        params = {
            "jsv": "2.7.2", "appKey": "34839810", "t": t,
            "sign": generate_sign(t, self._h5_token(), data_val),
            "v": "1.0", "type": "originaljson", "accountSite": "xianyu",
            "dataType": "json", "timeout": "20000",
            "api": "mtop.taobao.idle.pc.detail",
            "sessionOption": "AutoLoginOnly",
        }
        try:
            resp = await self.client.post(
                "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/",
                params=params, data={"data": data_val},
            )
            rj = resp.json()
            ret = rj.get("ret", [])
            if any("SUCCESS" in r for r in ret):
                return rj
            if "set-cookie" in resp.headers:
                self._clear_dup_cookies()
        except Exception as e:
            logger.error(f"get_item_info 异常: {scrub_secrets(str(e))}")
        await asyncio.sleep(0.5)
        return await self.get_item_info(item_id, retry + 1)

    # ------------------------------------------------------------------
    async def close(self):
        """关闭底层 HTTP 连接（必须在不再使用时调用，防止连接泄漏）"""
        if not self._closed:
            await self.client.aclose()
            self._closed = True

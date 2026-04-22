"""CookieCloud 集成模块 — 从 CookieCloud 服务端自动同步闲鱼 Cookie

搬运参考: easychen/CookieCloud (2958 星) + RickForYK/xianyu-auto-reply-cookiecloud
支持 legacy (CryptoJS OpenSSL 格式) 和 aes-128-cbc-fixed 两种加密算法。
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util.Padding import unpad
except ImportError:
    from Crypto.Cipher import AES  # type: ignore[no-redef]
    from Crypto.Util.Padding import unpad  # type: ignore[no-redef]

from src.utils import scrub_secrets

logger = logging.getLogger(__name__)

# ---- 闲鱼相关域名（按优先级排序，越前面的越重要）----
XIANYU_DOMAINS = [".goofish.com", ".taobao.com", ".alicdn.com", ".aliyun.com"]

# ---- 最小刷新间隔（秒），防止频繁请求 ----
MIN_REFRESH_INTERVAL = 60

# ---- 同步记录最大保留条数 ----
MAX_SYNC_HISTORY = 50


class CookieCloudClient:
    """CookieCloud 客户端 — 从服务端拉取并解密 Cookie

    加密方案:
    - legacy: CryptoJS AES-256-CBC + OpenSSL EVP_BytesToKey(MD5) 密钥派生
    - aes-128-cbc-fixed: AES-128-CBC + 固定全零 IV
    """

    def __init__(self, host: str, uuid: str, password: str):
        """初始化客户端

        Args:
            host: CookieCloud 服务端地址（如 http://127.0.0.1:8088）
            uuid: 唯一标识（浏览器插件中设置的 UUID）
            password: 加密密码（浏览器插件中设置的密码）
        """
        self.host = host.rstrip("/")
        self.uuid = uuid
        self.password = password
        # 密钥派生: md5(uuid + "-" + password) 的前 16 个 hex 字符
        self._passphrase = hashlib.md5(
            f"{uuid}-{password}".encode("utf-8")
        ).hexdigest()[:16]

    def _evp_bytes_to_key(
        self, passphrase: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16
    ) -> Tuple[bytes, bytes]:
        """OpenSSL EVP_BytesToKey(MD5) 密钥派生实现

        CryptoJS 默认使用此算法从 passphrase + salt 派生 AES 密钥和 IV。
        """
        d = b""
        prev = b""
        while len(d) < key_len + iv_len:
            prev = hashlib.md5(prev + passphrase + salt).digest()
            d += prev
        return d[:key_len], d[key_len : key_len + iv_len]

    def _decrypt_legacy(self, encrypted_b64: str) -> dict:
        """解密 legacy 格式（CryptoJS OpenSSL 兼容，AES-256-CBC）"""
        raw = base64.b64decode(encrypted_b64)
        if raw[:8] != b"Salted__":
            raise ValueError("密文缺少 'Salted__' 头部，格式不正确")
        salt = raw[8:16]
        ciphertext = raw[16:]
        key, iv = self._evp_bytes_to_key(self._passphrase.encode("utf-8"), salt)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return json.loads(plaintext.decode("utf-8"))

    def _decrypt_fixed_iv(self, encrypted_b64: str) -> dict:
        """解密 aes-128-cbc-fixed 格式（AES-128-CBC，固定全零 IV）"""
        ciphertext = base64.b64decode(encrypted_b64)
        key = self._passphrase.encode("utf-8")  # 16 字节 = 128 bit
        iv = b"\x00" * 16  # 固定全零 IV
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return json.loads(plaintext.decode("utf-8"))

    async def fetch_decrypted(self, timeout: int = 15) -> dict:
        """拉取并解密 Cookie 数据

        先尝试 POST 明文模式（服务端解密），失败则回退到 GET 加密 + 本地解密。
        返回 { "cookie_data": {...}, "local_storage_data": {...} }
        """
        # 方案一: POST 带 password，服务端直接返回明文
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.host}/get/{self.uuid}",
                    json={"password": self.password},
                )
                resp.raise_for_status()
                data = resp.json()
                if "cookie_data" in data:
                    logger.debug("CookieCloud: POST 明文模式成功")
                    return data
        except Exception as e:
            logger.debug("CookieCloud POST 明文模式失败，回退到加密模式: %s", scrub_secrets(str(e)))

        # 方案二: GET 加密数据 + 本地解密
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{self.host}/get/{self.uuid}")
            resp.raise_for_status()
            data = resp.json()

        encrypted = data.get("encrypted")
        if not encrypted:
            raise ValueError("CookieCloud 服务端返回数据中缺少 encrypted 字段")

        crypto_type = data.get("crypto_type", "legacy")
        if crypto_type == "aes-128-cbc-fixed":
            return self._decrypt_fixed_iv(encrypted)
        else:
            return self._decrypt_legacy(encrypted)

    async def get_xianyu_cookie_string(self, timeout: int = 15) -> Optional[str]:
        """获取闲鱼相关域名的 Cookie 字符串（name=value; 格式）

        按域名优先级合并: .goofish.com > .taobao.com > .alicdn.com > .aliyun.com
        同名 Cookie 以高优先级域名的为准。
        """
        try:
            data = await self.fetch_decrypted(timeout=timeout)
            cookie_data = data.get("cookie_data", {})

            # 按优先级反序遍历，让高优先级的覆盖低优先级的
            kv: Dict[str, str] = {}
            for domain in reversed(XIANYU_DOMAINS):
                for key, cookies in cookie_data.items():
                    if domain in key:
                        for c in cookies:
                            name = c.get("name", "")
                            value = c.get("value", "")
                            if name and value:
                                kv[name] = value

            if not kv:
                logger.warning("CookieCloud: 未找到闲鱼相关域名的 Cookie（%s）", list(cookie_data.keys()))
                return None

            cookie_str = "; ".join(f"{k}={v}" for k, v in kv.items())
            logger.info("CookieCloud: 成功获取闲鱼 Cookie（%d 个键值对）", len(kv))
            return cookie_str

        except Exception as e:
            logger.error("CookieCloud: 获取闲鱼 Cookie 失败: %s", scrub_secrets(str(e)))
            return None

    async def health_check(self, timeout: int = 5) -> bool:
        """检查 CookieCloud 服务端是否可达"""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{self.host}/health")
                return resp.status_code == 200
        except Exception:
            return False


class CookieCloudManager:
    """CookieCloud 同步管理器 — 定时从 CookieCloud 拉取 Cookie 并更新到 .env

    集成到现有 cookie_refresher.py 作为主要 Cookie 来源，
    QR 扫码降级为备用方案。
    """

    def __init__(self):
        self._client: Optional[CookieCloudClient] = None
        self._enabled = False
        self._last_sync_time = 0.0
        self._sync_interval = 300  # 默认 5 分钟
        self._consecutive_failures = 0
        self._max_failures_before_notify = 6  # 连续失败 6 次（30 分钟）后才通知
        self._sync_history: List[Dict[str, Any]] = []
        self._last_cookie_str: Optional[str] = ""
        self._load_config()

    def _load_config(self):
        """从环境变量加载 CookieCloud 配置"""
        host = os.environ.get("COOKIECLOUD_HOST", "").strip()
        uuid = os.environ.get("COOKIECLOUD_UUID", "").strip()
        password = os.environ.get("COOKIECLOUD_PASSWORD", "").strip()

        if host and uuid and password:
            self._client = CookieCloudClient(host, uuid, password)
            self._enabled = True
            interval = os.environ.get("COOKIECLOUD_REFRESH_SECONDS", "300")
            try:
                self._sync_interval = max(MIN_REFRESH_INTERVAL, int(interval))
            except ValueError:
                self._sync_interval = 300
            logger.info(
                "CookieCloud 已启用: host=%s, 同步间隔=%d秒",
                scrub_secrets(host), self._sync_interval,
            )
        else:
            self._enabled = False
            logger.info("CookieCloud 未配置（缺少 COOKIECLOUD_HOST/UUID/PASSWORD），使用传统 Cookie 管理")

    @property
    def enabled(self) -> bool:
        """是否已启用 CookieCloud"""
        return self._enabled and self._client is not None

    @property
    def status(self) -> Dict[str, Any]:
        """返回当前同步状态（用于 API/GUI 展示）"""
        return {
            "enabled": self._enabled,
            "host": scrub_secrets(os.environ.get("COOKIECLOUD_HOST", "")),
            "sync_interval_seconds": self._sync_interval,
            "last_sync_time": self._last_sync_time,
            "consecutive_failures": self._consecutive_failures,
            "last_cookie_available": bool(self._last_cookie_str),
            "sync_history": self._sync_history[-10:],  # 最近 10 条同步记录
        }

    def _add_sync_record(self, success: bool, message: str):
        """添加同步记录"""
        record = {
            "time": time.time(),
            "success": success,
            "message": message,
        }
        self._sync_history.append(record)
        if len(self._sync_history) > MAX_SYNC_HISTORY:
            self._sync_history = self._sync_history[-MAX_SYNC_HISTORY:]

    async def sync_once(self) -> bool:
        """执行一次 Cookie 同步

        成功时更新 .env 文件并发送 SIGUSR1 信号热重载闲鱼进程。
        返回 True 表示同步成功且 Cookie 有更新。
        """
        if not self.enabled:
            return False

        try:
            cookie_str = await self._client.get_xianyu_cookie_string()
            if not cookie_str:
                self._consecutive_failures += 1
                self._add_sync_record(False, "未获取到闲鱼 Cookie（浏览器可能离线）")
                return False

            # 检查 Cookie 是否有变化
            if cookie_str == self._last_cookie_str:
                self._consecutive_failures = 0
                self._last_sync_time = time.time()
                self._add_sync_record(True, "Cookie 无变化，跳过更新")
                return True

            # Cookie 有变化，先验证有效性再写入 .env（HI-734: 防止同步过期 cookie）
            is_valid = await self._validate_cookie(cookie_str)
            if not is_valid:
                self._consecutive_failures += 1
                self._add_sync_record(False, "Cookie 已同步但验证无效（可能已过期），跳过写入")
                logger.warning("CookieCloud: 同步到的 Cookie 验证失败（hasLogin=False），不写入 .env")
                return False

            # 验证通过，写入 .env
            from .cookie_refresher import update_env_file
            update_env_file(cookie_str)
            self._last_cookie_str = cookie_str
            self._consecutive_failures = 0
            self._last_sync_time = time.time()
            self._add_sync_record(True, "Cookie 已更新并写入 .env")

            # 发送 SIGUSR1 信号通知闲鱼进程热重载 Cookie
            self._signal_xianyu_reload()

            logger.info("CookieCloud: Cookie 同步成功并已更新")
            return True

        except Exception as e:
            self._consecutive_failures += 1
            msg = f"同步失败: {scrub_secrets(str(e))}"
            self._add_sync_record(False, msg)
            logger.error("CookieCloud: %s", msg)
            return False

    def _signal_xianyu_reload(self):
        """通知闲鱼进程热重载 Cookie（通过 SIGUSR1 信号）"""
        import signal
        try:
            # 查找闲鱼进程的 PID
            pid_file = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "xianyu.pid"
            )
            if os.path.exists(pid_file):
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGUSR1)
                logger.info("已发送 SIGUSR1 到闲鱼进程 (PID %d)", pid)
            else:
                logger.debug("闲鱼 PID 文件不存在，跳过信号发送")
        except (ValueError, ProcessLookupError, PermissionError) as e:
            logger.warning("发送 SIGUSR1 失败: %s", e)

    async def _validate_cookie(self, cookie_str: str) -> bool:
        """HI-734: 用 hasLogin API 验证 cookie 是否有效

        创建临时 XianyuApis 客户端，调用 has_login() 判断 cookie 是否已过期。
        验证通过返回 True，失败（过期/无效/异常）返回 False。
        """
        try:
            from .xianyu_apis import XianyuApis
            async with XianyuApis(cookie_str) as api:
                ok = await api.has_login()
                if ok:
                    logger.debug("CookieCloud: Cookie 验证通过 (hasLogin=True)")
                    return True
                else:
                    logger.warning("CookieCloud: Cookie 验证失败 (hasLogin=False)")
                    return False
        except Exception as e:
            logger.warning("CookieCloud: Cookie 验证异常: %s", scrub_secrets(str(e)))
            return False

    def should_notify_user(self) -> bool:
        """判断是否应该通知用户（静默模式策略）

        策略:
        - 连续失败 < 6 次（30 分钟）→ 不通知（静默）
        - 连续失败 >= 6 次 → 发一条通知
        - 深夜 23:00-07:00 → 不通知
        """
        if self._consecutive_failures < self._max_failures_before_notify:
            return False

        # 深夜不通知
        from datetime import datetime
        import pytz
        try:
            tz = pytz.timezone(os.environ.get("TIMEZONE", "Asia/Shanghai"))
            now = datetime.now(tz)
            if now.hour >= 23 or now.hour < 7:
                return False
        except Exception as e:
            logger.warning("Cookie/会话操作失败: %s", e)

        # 只在刚好达到阈值时通知一次，之后每 12 次（1 小时）再通知
        return (
            self._consecutive_failures == self._max_failures_before_notify
            or self._consecutive_failures % 12 == 0
        )

    async def run_sync_loop(self):
        """持续运行的同步循环（作为后台任务注册到 APScheduler 或 asyncio）"""
        logger.info("CookieCloud 同步循环已启动，间隔 %d 秒", self._sync_interval)
        while True:
            try:
                await self.sync_once()
            except Exception as e:
                logger.error("CookieCloud 同步循环异常: %s", scrub_secrets(str(e)))
            await asyncio.sleep(self._sync_interval)

    async def configure(self, host: str, uuid: str, password: str, interval: int = 300) -> bool:
        """动态配置 CookieCloud（从 GUI/API 调用）

        配置成功后立即执行一次同步测试。
        """
        # 验证参数
        if not host or not uuid or not password:
            return False

        # 写入环境变量（运行时生效）
        os.environ["COOKIECLOUD_HOST"] = host
        os.environ["COOKIECLOUD_UUID"] = uuid
        os.environ["COOKIECLOUD_PASSWORD"] = password
        os.environ["COOKIECLOUD_REFRESH_SECONDS"] = str(max(MIN_REFRESH_INTERVAL, interval))

        # 同步写入 .env 文件（持久化）
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", ".env")
        if os.path.exists(env_path):
            try:
                import dotenv
                dotenv.set_key(env_path, "COOKIECLOUD_HOST", host)
                dotenv.set_key(env_path, "COOKIECLOUD_UUID", uuid)
                dotenv.set_key(env_path, "COOKIECLOUD_PASSWORD", password)
                dotenv.set_key(env_path, "COOKIECLOUD_REFRESH_SECONDS", str(interval))
                logger.info("CookieCloud 配置已持久化到 .env")
            except Exception as e:
                logger.warning("CookieCloud 配置持久化失败: %s", scrub_secrets(str(e)))

        # 重新加载配置
        self._load_config()

        # 立即测试一次同步
        if self.enabled:
            success = await self.sync_once()
            return success
        return False


# ---- 全局单例 ----
_manager: Optional[CookieCloudManager] = None


def get_cookie_cloud_manager() -> CookieCloudManager:
    """获取 CookieCloud 管理器全局单例"""
    global _manager
    if _manager is None:
        _manager = CookieCloudManager()
    return _manager

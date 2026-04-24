"""Cookie 自动刷新 — 监控 _m_h5_tk 过期并主动续期"""
import logging
import os
import re
import tempfile
import time

from src.utils import scrub_secrets

logger = logging.getLogger(__name__)


def parse_h5_tk_timestamp(cookies: dict) -> float:
    """从 _m_h5_tk 中提取过期时间戳（毫秒级，取 _ 后的部分）"""
    tk = cookies.get("_m_h5_tk", "")
    if "_" in tk:
        try:
            return float(tk.split("_")[1]) / 1000.0
        except (ValueError, IndexError) as e:
            logger.debug("解析 _m_h5_tk 时间戳失败: %s", e)
    return 0.0


def is_cookie_expiring(cookies: dict, margin_seconds: int = 300) -> bool:
    """判断 cookie 是否即将过期（默认 5 分钟内）

    修复: 无法解析 _m_h5_tk 时返回 False（假定有效），
    因为 httpx CookieJar 的 domain 匹配问题经常导致读不到 _m_h5_tk，
    不代表真正过期。真实过期判断应依赖 has_login() API 验证。
    """
    expires_at = parse_h5_tk_timestamp(cookies)
    if expires_at <= 0:
        # 无法解析 _m_h5_tk — 不作为过期依据，返回 False 让 has_login() 做最终裁决
        return False
    return time.time() + margin_seconds >= expires_at


async def refresh_cookies_via_session(api) -> bool:
    """通过 has_login + get_token 刷新 httpx client 中的 cookie。

    has_login 会触发服务端下发新的 Set-Cookie，httpx.AsyncClient 自动存储。
    刷新后立即验证 token 能否获取 — 防止 hasLogin 返回 True 但 cookie 实际无效的"假成功"。
    返回 True 表示刷新成功且 token 验证通过。
    """
    try:
        ok = await api.has_login()
        if ok:
            api._clear_dup_cookies()
            # 验证刷新后的 cookie 是否真正有效 — 尝试获取 WS token
            import secrets
            test_device_id = secrets.token_hex(16)
            token_result = await api.get_token(test_device_id)
            if token_result:
                logger.info("Cookie 刷新成功 (via hasLogin + token 验证通过)")
                return True
            else:
                logger.warning("Cookie 刷新假成功: hasLogin 返回 True 但 token 获取失败，Cookie 实际无效")
                return False
        logger.warning("Cookie 刷新失败: hasLogin 返回 False")
        return False
    except Exception as e:
        logger.error(f"Cookie 刷新异常: {scrub_secrets(str(e))}")
        return False


def build_cookie_str(client) -> str:
    """从 httpx.AsyncClient 构建 cookie 字符串"""
    return "; ".join(f"{name}={value}" for name, value in client.cookies.items())


def update_env_file(cookie_str: str):
    """将新 cookie 写回 .env 文件"""
    env_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", ".env"
    )
    if not os.path.exists(env_path):
        logger.debug("未找到 .env 文件，跳过写回")
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        if "XIANYU_COOKIES=" in content:
            content = re.sub(
                r"XIANYU_COOKIES=.*",
                f"XIANYU_COOKIES={cookie_str}",
                content,
            )
            # Atomic write: temp file + rename to prevent corruption
            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(env_path), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                os.replace(tmp, env_path)
            except Exception as e:  # noqa: F841
                try:
                    os.unlink(tmp)
                except OSError as e:
                    logger.debug("清理临时文件失败: %s", e)
                raise
            logger.info("Cookie 已写回 .env")
    except Exception as e:
        logger.error(f"写回 .env 失败: {scrub_secrets(str(e))}")


class CookieHealthMonitor:
    """Cookie 健康监控器 — 定期检查所有平台 Cookie 状态并推送告警"""

    CHECK_INTERVAL = 3600  # 每小时检查一次
    WARN_THRESHOLD = 43200  # 12小时预警阈值（秒）

    def __init__(self):
        self._last_check: dict[str, float] = {}

    async def check_all_cookies(self) -> dict:
        """检查所有平台 Cookie 健康状态

        Returns:
            dict: {platform: {valid: bool, expires_at: str|None, hours_left: float|None, status: str}}
        """
        from pathlib import Path

        results = {}
        cookie_dir = Path.home() / ".openclaw"

        # 闲鱼 Cookie — 从环境变量和 .env 检查
        xianyu_status = await self._check_xianyu_cookie()
        results["xianyu"] = xianyu_status

        # X (Twitter) Cookie
        x_cookie_file = cookie_dir / "x_cookies.json"
        results["x"] = self._check_file_cookie(x_cookie_file, "x")

        # 小红书 Cookie
        xhs_cookie_file = cookie_dir / "xhs_cookies.json"
        results["xhs"] = self._check_file_cookie(xhs_cookie_file, "xhs")

        return results

    async def _check_xianyu_cookie(self) -> dict:
        """检查闲鱼 Cookie 状态"""
        import os
        cookie_str = os.environ.get("XIANYU_COOKIES", "")
        if not cookie_str:
            return {"valid": False, "expires_at": None, "hours_left": None, "status": "missing"}

        # 解析 cookie 字符串为 dict
        cookies = {}
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, val = pair.split("=", 1)
                cookies[key.strip()] = val.strip()

        expires_at_ts = parse_h5_tk_timestamp(cookies)
        if expires_at_ts <= 0:
            # 无法解析过期时间，尝试验证
            return {"valid": True, "expires_at": None, "hours_left": None, "status": "unknown_expiry"}

        import time
        from datetime import datetime
        hours_left = (expires_at_ts - time.time()) / 3600
        expires_at_str = datetime.fromtimestamp(expires_at_ts).isoformat()

        if hours_left <= 0:
            return {"valid": False, "expires_at": expires_at_str, "hours_left": 0, "status": "expired"}
        elif hours_left < self.WARN_THRESHOLD / 3600:
            return {"valid": True, "expires_at": expires_at_str, "hours_left": round(hours_left, 1), "status": "expiring_soon"}
        else:
            return {"valid": True, "expires_at": expires_at_str, "hours_left": round(hours_left, 1), "status": "valid"}

    def _check_file_cookie(self, cookie_file, platform: str) -> dict:
        """检查文件形式存储的 Cookie"""
        import json
        import time
        from datetime import datetime

        if not cookie_file.exists():
            return {"valid": False, "expires_at": None, "hours_left": None, "status": "missing"}

        try:
            data = json.loads(cookie_file.read_text(encoding="utf-8"))
            # 检查文件修改时间作为最后更新参考
            mtime = cookie_file.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600

            # 大多数 Cookie 文件有 expires_at 或 updated_at 字段
            expires_at = data.get("expires_at") or data.get("expiry")
            if expires_at:
                if isinstance(expires_at, (int, float)):
                    hours_left = (expires_at - time.time()) / 3600
                    expires_str = datetime.fromtimestamp(expires_at).isoformat()
                else:
                    hours_left = None
                    expires_str = str(expires_at)
                if hours_left is not None and hours_left <= 0:
                    return {"valid": False, "expires_at": expires_str, "hours_left": 0, "status": "expired"}
                elif hours_left is not None and hours_left < self.WARN_THRESHOLD / 3600:
                    return {"valid": True, "expires_at": expires_str, "hours_left": round(hours_left, 1), "status": "expiring_soon"}
                else:
                    return {"valid": True, "expires_at": expires_str, "hours_left": round(hours_left, 1) if hours_left else None, "status": "valid"}

            # 没有过期时间字段 — 用文件修改时间估算（超过48小时视为可能过期）
            if age_hours > 48:
                return {"valid": True, "expires_at": None, "hours_left": None, "status": "possibly_stale"}
            return {"valid": True, "expires_at": None, "hours_left": None, "status": "valid"}

        except (json.JSONDecodeError, OSError) as e:
            logger.debug("检查 %s Cookie 文件失败: %s", platform, e)
            return {"valid": False, "expires_at": None, "hours_left": None, "status": "error"}

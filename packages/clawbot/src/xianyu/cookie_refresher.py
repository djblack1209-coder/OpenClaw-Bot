"""Cookie 自动刷新 — 监控 _m_h5_tk 过期并主动续期"""
import logging
import os
import re
import tempfile
import time

logger = logging.getLogger(__name__)


def parse_h5_tk_timestamp(cookies: dict) -> float:
    """从 _m_h5_tk 中提取过期时间戳（毫秒级，取 _ 后的部分）"""
    tk = cookies.get("_m_h5_tk", "")
    if "_" in tk:
        try:
            return float(tk.split("_")[1]) / 1000.0
        except (ValueError, IndexError):
            pass
    return 0.0


def is_cookie_expiring(cookies: dict, margin_seconds: int = 300) -> bool:
    """判断 cookie 是否即将过期（默认 5 分钟内）"""
    expires_at = parse_h5_tk_timestamp(cookies)
    if expires_at <= 0:
        return True  # 无法解析，视为需要刷新
    return time.time() + margin_seconds >= expires_at


def refresh_cookies_via_session(api) -> bool:
    """通过 has_login + get_token 刷新 session 中的 cookie。
    
    has_login 会触发服务端下发新的 Set-Cookie，requests.Session 自动存储。
    返回 True 表示刷新成功。
    """
    try:
        ok = api.has_login()
        if ok:
            api._clear_dup_cookies()
            logger.info("Cookie 刷新成功 (via hasLogin)")
            return True
        logger.warning("Cookie 刷新失败: hasLogin 返回 False")
        return False
    except Exception as e:
        logger.error(f"Cookie 刷新异常: {e}")
        return False


def build_cookie_str(session) -> str:
    """从 requests.Session 构建 cookie 字符串"""
    return "; ".join(f"{c.name}={c.value}" for c in session.cookies)


def update_env_file(cookie_str: str):
    """将新 cookie 写回 .env 文件"""
    env_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", ".env"
    )
    if not os.path.exists(env_path):
        logger.debug("未找到 .env 文件，跳过写回")
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
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
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            logger.info("Cookie 已写回 .env")
    except Exception as e:
        logger.error(f"写回 .env 失败: {e}")

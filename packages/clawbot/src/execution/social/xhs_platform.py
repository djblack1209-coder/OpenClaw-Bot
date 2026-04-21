"""
Social — 小红书 (Xiaohongshu) 集成层 v2.0

v2.0 变更 (2026-04-20):
  - 新增 xhs 库（ReaJason/xhs）— Cookie 持久化登录，API 直发笔记
  - Cookie 自动保存到 ~/.openclaw/xhs_cookies.json
  - 二级降级: xhs API → browser worker
  - 新增 xhs_login / xhs_is_authenticated / xhs_create_note 函数

v1.0:
  - 完全依赖 browser worker 发布
  - 基于 social_browser_worker.py 的封装

支持:
- 发布笔记 (xhs API / browser worker)
- Cookie 持久化登录（支持浏览器 Cookie 字符串导入）
- 回复评论
- 更新个人资料
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)

# ── Cookie 存储路径 ──────────────────────────────────────────
_OPENCLAW_DIR = Path.home() / ".openclaw"
XHS_COOKIES_PATH = _OPENCLAW_DIR / "xhs_cookies.json"


# ── xhs 库 (ReaJason/xhs) — Cookie 持久化登录 ──────────────
_HAS_XHS = False
_xhs_client = None


def _init_xhs() -> bool:
    """初始化 xhs 客户端，从本地 Cookie 文件加载"""
    global _HAS_XHS, _xhs_client
    if _xhs_client is not None:
        return _HAS_XHS
    try:
        from xhs import XhsClient
        try:
            from xhs.help import sign as local_sign
        except ImportError:
            local_sign = None

        if XHS_COOKIES_PATH.exists():
            try:
                cookie_data = json.loads(XHS_COOKIES_PATH.read_text(encoding="utf-8"))
                cookie_str = cookie_data.get("cookie", "") if isinstance(cookie_data, dict) else ""
                if not cookie_str:
                    logger.warning("[XHS] Cookie 文件为空，需要重新登录")
                    return False

                # 构建签名函数
                def sign_func(uri, data=None, a1="", web_session=""):
                    if local_sign:
                        return local_sign(uri, data, a1=a1)
                    return {}

                _xhs_client = XhsClient(cookie=cookie_str, sign=sign_func)
                _HAS_XHS = True
                logger.info("[XHS] xhs 已加载 (Cookie 持久化: %s)", XHS_COOKIES_PATH)
            except Exception as e:
                logger.warning("[XHS] xhs Cookie 加载失败，需要重新登录: %s", e)
                _HAS_XHS = False
        else:
            logger.info("[XHS] xhs 已就绪，但无 Cookie 文件 — 需要调用 xhs_login() 登录")
            _HAS_XHS = False
        return _HAS_XHS
    except ImportError:
        logger.info("[XHS] xhs 未安装 (pip install xhs)")
        return False

# 模块加载时尝试初始化
_init_xhs()


def xhs_login(cookie_str: str) -> Dict:
    """使用浏览器 Cookie 字符串登录小红书

    获取方法: 打开小红书网页版，F12 → Network → 复制请求头中的 Cookie 值。
    Cookie 保存到本地文件，后续启动免登录。

    Args:
        cookie_str: 浏览器中复制的完整 Cookie 字符串
    """
    global _HAS_XHS, _xhs_client
    try:
        from xhs import XhsClient
    except ImportError:
        return {"success": False, "error": "xhs 未安装 (pip install xhs)"}

    if not cookie_str or not cookie_str.strip():
        return {"success": False, "error": "Cookie 字符串不能为空"}

    try:
        from xhs.help import sign as local_sign
    except ImportError:
        local_sign = None

    try:
        # 确保存储目录存在
        _OPENCLAW_DIR.mkdir(parents=True, exist_ok=True)

        # 构建签名函数
        def sign_func(uri, data=None, a1="", web_session=""):
            if local_sign:
                return local_sign(uri, data, a1=a1)
            return {}

        client = XhsClient(cookie=cookie_str.strip(), sign=sign_func)

        # 验证 Cookie 有效性 — 尝试获取用户信息
        try:
            info = client.get_self_info()
            if not info:
                return {"success": False, "error": "Cookie 无效或已过期，无法获取用户信息"}
            nickname = info.get("nickname", "未知用户")
        except Exception as e:
            logger.warning("[XHS] Cookie 验证失败（可能仍可用）: %s", e)
            nickname = "未验证"

        # 保存 Cookie 到文件
        cookie_data = {
            "cookie": cookie_str.strip(),
            "nickname": nickname,
        }
        XHS_COOKIES_PATH.write_text(
            json.dumps(cookie_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        _xhs_client = client
        _HAS_XHS = True
        logger.info("[XHS] 小红书登录成功 (用户: %s)，Cookie 已保存到 %s", nickname, XHS_COOKIES_PATH)

        return {
            "success": True,
            "message": f"小红书登录成功 (用户: {nickname})，Cookie 已保存",
            "nickname": nickname,
            "cookies_path": str(XHS_COOKIES_PATH),
        }
    except Exception as e:
        logger.error("[XHS] 小红书登录失败: %s", e)
        return {"success": False, "error": f"小红书登录失败: {e}"}


def xhs_is_authenticated() -> bool:
    """检查小红书是否已认证（Cookie 文件存在且已加载）"""
    if _HAS_XHS:
        return True
    # 尝试重新初始化
    return _init_xhs()


def xhs_create_note(
    title: str,
    content: str,
    images: Optional[List[str]] = None,
    is_private: bool = False,
) -> Dict:
    """通过 xhs 库发布小红书笔记（Cookie 认证）

    Args:
        title: 笔记标题（最多 20 字）
        content: 笔记正文
        images: 图片文件路径列表（至少需要 1 张图片才能发布图文笔记）
        is_private: 是否设为私密笔记
    """
    global _HAS_XHS
    if not _HAS_XHS or _xhs_client is None:
        return {"success": False, "error": "小红书未认证，请先调用 xhs_login()"}

    if not title:
        return {"success": False, "error": "标题不能为空"}

    try:
        # 小红书标题限制 20 字
        title = title[:20]

        # 如果有图片，使用 create_image_note
        if images:
            valid_images = [p for p in images if Path(p).exists()]
            if not valid_images:
                return {"success": False, "error": "所有图片路径无效"}
            result = _xhs_client.create_image_note(
                title=title,
                desc=content,
                files=valid_images,
                is_private=is_private,
            )
        else:
            # 纯文字笔记（小红书要求至少 1 张图，此处会由 API 返回错误）
            result = _xhs_client.create_image_note(
                title=title,
                desc=content,
                files=[],
                is_private=is_private,
            )

        logger.info("[XHS] 笔记发布成功: %s", title)
        return {
            "success": True,
            "result": result,
            "method": "xhs_api",
            "title": title,
        }
    except Exception as e:
        error_msg = str(e).lower()
        # 检测 Cookie 过期
        if any(kw in error_msg for kw in ["登录", "login", "cookie", "sign", "未登录", "401", "403"]):
            _HAS_XHS = False
            logger.warning("[XHS] Cookie 可能已过期，需要重新登录: %s", e)
            return {
                "success": False,
                "error": f"小红书 Cookie 已过期，请重新登录: {e}",
                "needs_relogin": True,
            }
        logger.error("[XHS] 笔记发布失败: %s", e)
        return {"success": False, "error": f"发布失败: {e}"}


async def publish_xhs_article(
    title: str,
    body: str,
    worker_fn=None,
    image_path: str = None,
) -> Dict:
    """发布小红书笔记

    v2.0 二级降级: xhs API → browser worker
    """
    if not title or not body:
        return {"success": False, "error": "标题和正文不能为空"}

    # 方式0: xhs API 直发（v2.0 新增）
    if _HAS_XHS and _xhs_client:
        images = [image_path] if image_path and Path(image_path).exists() else None
        result = xhs_create_note(
            title=title,
            content=body,
            images=images,
        )
        if result.get("success"):
            return result
        # API 失败则降级到 browser worker
        logger.info("[XHS] xhs API 发布失败，尝试降级到 browser worker: %s", result.get("error"))

    # 方式1: browser worker（现有逻辑）
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置，且 xhs 未认证"}
    try:
        payload = {"title": title, "body": body}
        if image_path:
            payload["image"] = image_path
        # 浏览器自动化是同步阻塞操作（5-30秒），必须丢到线程池避免冻结事件循环
        result = await asyncio.to_thread(worker_fn, "publish_xhs", payload)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[XHS.publish] failed: {scrub_secrets(str(e))}")
        return {"success": False, "error": str(e)}


async def reply_to_xhs_comment(
    note_url: str,
    reply_text: str,
    worker_fn=None,
) -> Dict:
    """回复小红书评论"""
    if not note_url or not reply_text:
        return {"success": False, "error": "URL 和回复内容不能为空"}
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        # 浏览器自动化是同步阻塞操作，必须丢到线程池
        reply_payload = {
            "url": note_url,
            "text": reply_text,
        }
        result = await asyncio.to_thread(worker_fn, "reply_xhs", reply_payload)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[XHS.reply] failed: {scrub_secrets(str(e))}")
        return {"success": False, "error": str(e)}


async def update_xhs_profile(
    bio: str = None,
    worker_fn=None,
) -> Dict:
    """更新小红书个人资料"""
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        payload = {}
        if bio:
            payload["bio"] = bio
        # 浏览器自动化是同步阻塞操作，必须丢到线程池
        result = await asyncio.to_thread(worker_fn, "update_xhs_profile", payload)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[XHS.profile] failed: {scrub_secrets(str(e))}")
        return {"success": False, "error": str(e)}

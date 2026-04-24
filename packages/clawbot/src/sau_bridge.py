"""
社媒发布桥接层 — 对接 social-auto-upload (9K星, MIT)
通过 subprocess 调用 sau CLI 实现多平台发布

支持平台: 抖音/B站/小红书/快手
调用方式: CLI 桥接 (解耦、稳定、不受 sau 内部重构影响)

用法:
    from src.sau_bridge import publish_video, publish_note, check_login, get_supported_platforms
    result = await publish_video("douyin", "my_account", "/path/to/video.mp4", "标题", "描述")
"""
import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 支持的平台映射
PLATFORMS = {
    "douyin": {"name": "抖音", "video": True, "note": True},
    "bilibili": {"name": "B站", "video": True, "note": False},
    "xiaohongshu": {"name": "小红书", "video": True, "note": True},
    "kuaishou": {"name": "快手", "video": True, "note": True},
}

# 默认账号名（可通过环境变量覆盖）
DEFAULT_ACCOUNT = os.getenv("SAU_DEFAULT_ACCOUNT", "default")


async def _run_sau_cmd(args: list[str], timeout: int = 120) -> dict:
    """执行 sau CLI 命令并返回结构化结果"""
    cmd = ["sau"] + args
    logger.info("[SAU] 执行: %s", " ".join(cmd[:5]))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        result = {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace").strip(),
            "stderr": stderr.decode("utf-8", errors="replace").strip(),
        }
        if result["success"]:
            logger.info("[SAU] 成功: %s", result["stdout"][:200])
        else:
            logger.warning("[SAU] 失败 (rc=%d): %s", proc.returncode, result["stderr"][:200])
        return result
    except TimeoutError:
        logger.error("[SAU] 命令超时 (%ds)", timeout)
        return {"success": False, "error": f"命令超时 ({timeout}s)", "returncode": -1}
    except FileNotFoundError:
        logger.error("[SAU] sau 命令未找到，请先安装: pip install social-auto-upload")
        return {"success": False, "error": "sau 未安装", "returncode": -1}
    except Exception as e:
        logger.error("[SAU] 执行异常: %s", e)
        return {"success": False, "error": str(e), "returncode": -1}


async def check_sau_installed() -> bool:
    """检查 sau CLI 是否可用"""
    result = await _run_sau_cmd(["--version"], timeout=10)
    return result["success"]


async def check_login(platform: str, account: str = "") -> dict:
    """检查指定平台的登录状态"""
    account = account or DEFAULT_ACCOUNT
    if platform not in PLATFORMS:
        return {"success": False, "error": f"不支持的平台: {platform}"}
    result = await _run_sau_cmd([platform, "check", "--account", account], timeout=30)
    return result


async def login(platform: str, account: str = "") -> dict:
    """登录指定平台（需要扫码）"""
    account = account or DEFAULT_ACCOUNT
    if platform not in PLATFORMS:
        return {"success": False, "error": f"不支持的平台: {platform}"}
    result = await _run_sau_cmd([platform, "login", "--account", account], timeout=300)
    return result


async def publish_video(
    platform: str,
    video_path: str,
    title: str,
    description: str = "",
    tags: list[str] = None,
    account: str = "",
    timeout: int = 180,
) -> dict:
    """发布视频到指定平台"""
    account = account or DEFAULT_ACCOUNT
    if platform not in PLATFORMS:
        return {"success": False, "error": f"不支持的平台: {platform}"}
    if not PLATFORMS[platform]["video"]:
        return {"success": False, "error": f"{PLATFORMS[platform]['name']}不支持视频发布"}
    if not Path(video_path).exists():
        return {"success": False, "error": f"视频文件不存在: {video_path}"}

    args = [platform, "upload-video",
            "--account", account,
            "--file", str(video_path),
            "--title", title[:100]]
    if description:
        args += ["--desc", description[:500]]
    if tags:
        args += ["--tags"] + [t[:20] for t in tags[:10]]

    return await _run_sau_cmd(args, timeout=timeout)


async def publish_note(
    platform: str,
    images: list[str],
    title: str,
    content: str = "",
    tags: list[str] = None,
    account: str = "",
    timeout: int = 120,
) -> dict:
    """发布图文笔记到指定平台"""
    account = account or DEFAULT_ACCOUNT
    if platform not in PLATFORMS:
        return {"success": False, "error": f"不支持的平台: {platform}"}
    if not PLATFORMS[platform]["note"]:
        return {"success": False, "error": f"{PLATFORMS[platform]['name']}不支持图文发布"}

    # 验证图片文件存在
    valid_images = [img for img in images if Path(img).exists()]
    if not valid_images:
        return {"success": False, "error": "没有有效的图片文件"}

    args = [platform, "upload-note",
            "--account", account,
            "--title", title[:100],
            "--images"] + valid_images
    if content:
        args += ["--note", content[:2000]]
    if tags:
        args += ["--tags"] + [t[:20] for t in tags[:10]]

    return await _run_sau_cmd(args, timeout=timeout)


async def publish_multi_platform(
    platforms: list[str],
    video_path: str = "",
    images: list[str] = None,
    title: str = "",
    description: str = "",
    tags: list[str] = None,
    account: str = "",
) -> dict[str, dict]:
    """一键多平台发布（并行执行）"""
    async def _publish_one(platform):
        if platform not in PLATFORMS:
            return platform, {"success": False, "error": f"不支持: {platform}"}
        if video_path:
            return platform, await publish_video(platform, video_path, title, description, tags, account)
        elif images:
            return platform, await publish_note(platform, images, title, description, tags, account)
        else:
            return platform, {"success": False, "error": "需要视频或图片"}

    tasks = [_publish_one(p) for p in platforms]
    done = await asyncio.gather(*tasks, return_exceptions=True)
    results = {}
    for item in done:
        if isinstance(item, Exception):
            continue
        results[item[0]] = item[1]
    return results


def get_supported_platforms() -> dict:
    """返回支持的平台列表"""
    return PLATFORMS


def format_publish_result(results: dict[str, dict]) -> str:
    """格式化多平台发布结果为用户友好消息"""
    lines = ["📤 发布结果:\n"]
    for platform, result in results.items():
        name = PLATFORMS.get(platform, {}).get("name", platform)
        if result.get("success"):
            lines.append(f"  ✅ {name}: 发布成功")
        else:
            error = result.get("error", result.get("stderr", "未知错误"))
            lines.append(f"  ❌ {name}: {error[:50]}")
    return "\n".join(lines)

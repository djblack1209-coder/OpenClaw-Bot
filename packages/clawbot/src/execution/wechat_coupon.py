"""微信「提现笔笔省」自动领券模块

通过 mitmproxy 中间人代理截获微信小程序流量中的 session-token，
然后直接调用微信后端 API 领取每日免费提现券（365天有效期）。

工作流:
  1. 设置 macOS 系统代理 → 127.0.0.1:8080
  2. 启动 mitmdump 监听，addon 截获 session-token
  3. 通过 weixin:// URL scheme 打开小程序触发流量
  4. 从截获的 token 文件中提取凭证
  5. POST 领券 API
  6. 恢复代理、清理进程

支持 token 持久化存储和有效期测试，为后续云端部署做准备。

参考: https://github.com/whether1/txbbs-WxMiniProgramScript
"""

import asyncio
import json
import os
import re
import signal
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

import logging

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────

# 领券 API 地址
_COUPON_API = (
    "https://discount.wxpapp.wechatpay.cn"
    "/txbbs-mall/coupon/deliveryfreewithdrawalcoupon"
)
# 小程序 App ID
_APP_ID = "wxdb3c0e388702f785"
# 微信 URL Scheme（打开小程序）
_MINI_PROGRAM_URL = f"weixin://launchapplet/?app_id={_APP_ID}"
# token 临时文件路径（与 mitm_token_addon.py 约定）
_TOKEN_FILE = Path(os.getenv("COUPON_TOKEN_FILE", "/tmp/wechat_coupon_token.txt"))
# mitm addon 脚本路径
_MITM_ADDON = Path(__file__).parent.parent.parent / "scripts" / "mitm_token_addon.py"
# 最大重试次数
_MAX_RETRIES = 3
# mitmproxy 监听端口
_PROXY_PORT = 8080
# HTTP 请求超时
_TIMEOUT = 15.0
# macOS 网络服务名（默认 Wi-Fi，可通过环境变量覆盖）
_NETWORK_SERVICE = os.getenv("COUPON_NETWORK_SERVICE", "Wi-Fi")

# 请求头中的 User-Agent（伪装 macOS 微信客户端）
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Mac WindowsWechat/WMPF XWEB/16771"
)

# token 提取正则（按优先级排列）
_TOKEN_PATTERNS = [
    re.compile(r"header:session-token\t([A-Za-z0-9_\-+/=]+)"),
    re.compile(r"response_json:session_token\t([A-Za-z0-9_\-+/=]+)"),
    re.compile(r"session[-_]token[:\t=]\s*([A-Za-z0-9_\-+/=]{40,})"),
]

# 持久化 token 存储路径（~/.openclaw/coupon_token.json）
_PERSISTENT_TOKEN_DIR = Path.home() / ".openclaw"
_PERSISTENT_TOKEN_PATH = _PERSISTENT_TOKEN_DIR / "coupon_token.json"


# ── Token 持久化存储 ───────────────────────────────────

def save_token_persistent(token: str) -> None:
    """将 token 持久化保存到本地文件（带捕获时间戳）

    保存格式: {"token": "xxx", "captured_at": "ISO时间", "captured_ts": unix时间戳}
    用于后续测试 token 有效期和云端部署。
    """
    try:
        _PERSISTENT_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        data = {
            "token": token,
            "captured_at": now.isoformat(),
            "captured_ts": int(now.timestamp()),
        }
        _PERSISTENT_TOKEN_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("token 已持久化保存到 %s", _PERSISTENT_TOKEN_PATH)
    except OSError as e:
        logger.error("持久化保存 token 失败: %s", e)


def load_saved_token() -> Optional[dict]:
    """从持久化文件加载已保存的 token

    Returns:
        包含 token、捕获时间等信息的字典，文件不存在或格式错误返回 None。
        字典结构: {
            "token": str,          # session-token 值
            "captured_at": str,    # ISO 格式捕获时间
            "captured_ts": int,    # Unix 时间戳
            "age_hours": float,    # token 已存活小时数
            "age_text": str,       # 人类可读的存活时间描述
        }
    """
    if not _PERSISTENT_TOKEN_PATH.exists():
        logger.debug("持久化 token 文件不存在")
        return None

    try:
        raw = _PERSISTENT_TOKEN_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("读取持久化 token 失败: %s", e)
        return None

    token = data.get("token")
    captured_ts = data.get("captured_ts")
    if not token or not captured_ts:
        logger.warning("持久化 token 文件格式不完整")
        return None

    # 计算 token 年龄
    now_ts = int(datetime.now(timezone.utc).timestamp())
    age_seconds = now_ts - captured_ts
    age_hours = age_seconds / 3600

    # 生成人类可读描述
    if age_hours < 1:
        age_text = f"{int(age_seconds / 60)} 分钟前"
    elif age_hours < 24:
        age_text = f"{age_hours:.1f} 小时前"
    else:
        age_days = age_hours / 24
        age_text = f"{age_days:.1f} 天前"

    data["age_hours"] = age_hours
    data["age_text"] = age_text
    return data


def set_token_manual(token: str) -> str:
    """手动设置 token（供 /set_coupon_token 命令使用）

    用户可以通过手机抓包工具获取 token 后手动设置，
    无需走 mitmproxy 流程。

    Args:
        token: 用户提供的 session-token 字符串

    Returns:
        操作结果消息
    """
    if not token or len(token) < 40:
        return "❌ token 格式不对，至少 40 个字符。请确认复制完整。"

    save_token_persistent(token)
    return f"✅ token 已保存（长度 {len(token)}）。可以用 /test_token 测试是否有效。"


async def test_saved_token() -> str:
    """测试已保存的 token 是否仍然有效

    直接用持久化保存的 token 调用领券 API，根据返回判断 token 状态。
    不走 mitmproxy 流程，纯 API 调用。

    Returns:
        中文结果消息，包含 token 年龄和有效性判断
    """
    saved = load_saved_token()
    if not saved:
        return (
            "❌ 没有保存的 token。\n"
            "请先用 /coupon 领一次券（会自动保存 token），\n"
            "或用 /set_coupon_token <token值> 手动设置。"
        )

    token = saved["token"]
    age_text = saved["age_text"]
    age_hours = saved["age_hours"]

    # 调用领券 API 测试
    result = await _claim_coupon(token)
    result_msg = _parse_claim_result(result)

    # 判断 token 是否仍然有效
    if result_msg.startswith("✅") or result_msg.startswith("ℹ️"):
        # 成功领取或已领过 → token 仍然有效
        status = "✅ Token 仍然有效！"
        validity = "有效"
    elif "鉴权" in result_msg or "登录" in result_msg or "268566816" in result_msg:
        # 鉴权失败 → token 已过期
        status = "❌ Token 已过期"
        validity = "已过期"
    else:
        # 其他错误（网络问题等），无法确定
        status = "⚠️ 无法确定 token 状态（可能是网络问题）"
        validity = "未知"

    return (
        f"🔍 Token 有效期测试结果\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Token 年龄: {age_text}（{age_hours:.1f} 小时）\n"
        f"测试结果: {status}\n"
        f"API 返回: {result_msg}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{'💡 结论: token 在 ' + age_text + ' 后依然可用，可以继续观察更长时间。' if validity == '有效' else ''}"
        f"{'💡 结论: token 有效期不足 ' + f'{age_hours:.1f} 小时' + '，需要更频繁地刷新。' if validity == '已过期' else ''}"
    )


async def claim_with_saved_token() -> str:
    """使用已保存的 token 直接领券（跳过 mitmproxy 流程）

    适用于 token 仍在有效期内的场景，可在任意平台运行（不依赖 macOS）。
    如果 token 过期会提示用户刷新。

    Returns:
        中文结果消息
    """
    saved = load_saved_token()
    if not saved:
        return (
            "❌ 没有可用的 token。\n"
            "请先用 /coupon 领一次券（会自动保存 token），\n"
            "或用 /set_coupon_token <token值> 手动设置。"
        )

    token = saved["token"]
    age_text = saved["age_text"]

    result = await _claim_coupon(token)
    result_msg = _parse_claim_result(result)

    # 如果鉴权失败，提示用户刷新 token
    if "鉴权" in result_msg or "登录" in result_msg:
        return (
            f"{result_msg}\n\n"
            f"⏰ 当前 token 是 {age_text} 获取的，已过期。\n"
            f"请用 /coupon 重新获取，或手动提供新 token。"
        )

    return f"{result_msg}\n（使用缓存 token，获取于 {age_text}）"


# ── 系统代理管理 ──────────────────────────────────────

def _set_macos_proxy(enable: bool) -> bool:
    """设置或恢复 macOS 系统 HTTP/HTTPS 代理

    使用 networksetup 命令操作。开启时指向 127.0.0.1:8080，
    关闭时恢复为直连。

    Args:
        enable: True 开启代理, False 恢复直连

    Returns:
        操作是否成功
    """
    try:
        if enable:
            # 设置 HTTP 代理
            subprocess.run(
                ["networksetup", "-setwebproxy", _NETWORK_SERVICE,
                 "127.0.0.1", str(_PROXY_PORT)],
                check=True, capture_output=True, timeout=10,
            )
            # 设置 HTTPS 代理
            subprocess.run(
                ["networksetup", "-setsecurewebproxy", _NETWORK_SERVICE,
                 "127.0.0.1", str(_PROXY_PORT)],
                check=True, capture_output=True, timeout=10,
            )
            logger.info("macOS 系统代理已开启 → 127.0.0.1:%d", _PROXY_PORT)
        else:
            # 关闭 HTTP 代理
            subprocess.run(
                ["networksetup", "-setwebproxystate", _NETWORK_SERVICE, "off"],
                check=True, capture_output=True, timeout=10,
            )
            # 关闭 HTTPS 代理
            subprocess.run(
                ["networksetup", "-setsecurewebproxystate", _NETWORK_SERVICE, "off"],
                check=True, capture_output=True, timeout=10,
            )
            logger.info("macOS 系统代理已恢复直连")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error("代理设置失败: %s", e)
        return False


# ── mitmproxy 进程管理 ─────────────────────────────────

def _start_mitmdump() -> Optional[subprocess.Popen]:
    """启动 mitmdump 代理进程

    使用项目内的 mitm_token_addon.py 作为 addon 脚本，
    监听指定端口截获微信流量。

    Returns:
        mitmdump 子进程对象，启动失败返回 None
    """
    if not _MITM_ADDON.exists():
        logger.error("mitm addon 脚本不存在: %s", _MITM_ADDON)
        return None

    try:
        # 设置环境变量让 addon 知道 token 写入路径
        env = os.environ.copy()
        env["COUPON_TOKEN_FILE"] = str(_TOKEN_FILE)

        proc = subprocess.Popen(
            [
                "mitmdump",
                "-s", str(_MITM_ADDON),
                "-p", str(_PROXY_PORT),
                "--set", "block_global=false",
                "--quiet",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            preexec_fn=os.setsid,  # 创建进程组，方便整体清理
        )
        logger.info("mitmdump 已启动 (PID %d, 端口 %d)", proc.pid, _PROXY_PORT)
        return proc
    except FileNotFoundError:
        logger.error("mitmdump 未安装，请执行: pip install mitmproxy")
        return None
    except Exception as e:
        logger.error("启动 mitmdump 失败: %s", e)
        return None


def _kill_mitmdump(proc: Optional[subprocess.Popen]) -> None:
    """安全终止 mitmdump 进程及其进程组"""
    if proc is None:
        return
    try:
        # 终止整个进程组
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
        logger.info("mitmdump 已终止 (PID %d)", proc.pid)
    except (ProcessLookupError, ChildProcessError):
        pass
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, ChildProcessError):
            pass
    except Exception as e:
        logger.debug("清理 mitmdump 进程异常: %s", e)


# ── 小程序窗口管理 ─────────────────────────────────────

def _open_mini_program() -> bool:
    """通过 weixin:// URL Scheme 打开笔笔省小程序

    Returns:
        是否成功执行 open 命令
    """
    try:
        subprocess.run(
            ["open", _MINI_PROGRAM_URL],
            check=True, capture_output=True, timeout=10,
        )
        logger.info("已通过 URL Scheme 打开笔笔省小程序")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error("打开小程序失败: %s", e)
        return False


def _close_mini_program() -> None:
    """通过 AppleScript 关闭笔笔省小程序窗口

    搜索微信中包含"笔笔省"或"提现"的窗口并关闭。
    """
    apple_script = '''
    tell application "System Events"
        tell process "WeChat"
            set windowList to every window
            repeat with w in windowList
                set winName to name of w
                if winName contains "笔笔省" or winName contains "提现" then
                    click button 1 of w
                end if
            end repeat
        end tell
    end tell
    '''
    try:
        subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True, timeout=5,
        )
        logger.debug("已尝试关闭笔笔省小程序窗口")
    except Exception as e:
        logger.debug("关闭小程序窗口异常（可忽略）: %s", e)


# ── Token 提取 ─────────────────────────────────────────

def _extract_token() -> Optional[str]:
    """从 mitm addon 写入的临时文件中提取 session-token

    按优先级依次尝试多种正则模式，返回找到的第一个有效 token。

    Returns:
        session-token 字符串，未找到返回 None
    """
    if not _TOKEN_FILE.exists():
        logger.debug("token 文件不存在: %s", _TOKEN_FILE)
        return None

    try:
        content = _TOKEN_FILE.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("读取 token 文件失败: %s", e)
        return None

    if not content.strip():
        return None

    # 按优先级逐个模式匹配
    for pattern in _TOKEN_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            # 选最长的（通常更完整）
            token = max(matches, key=len)
            if len(token) >= 40:
                logger.info("提取到 session-token (长度 %d)", len(token))
                return token

    # 兜底：匹配任意 40+ 字符的 Base64 类字符串
    fallback = re.findall(r"[A-Za-z0-9_\-+/=]{40,300}", content)
    if fallback:
        token = max(fallback, key=len)
        logger.info("兜底提取到疑似 token (长度 %d)", len(token))
        return token

    logger.warning("token 文件中未找到有效 token")
    return None


# ── 领券 API 调用 ──────────────────────────────────────

async def _claim_coupon(token: str) -> dict:
    """调用微信领券 API

    发送 POST 请求到笔笔省后端，领取免费提现券。

    Args:
        token: 从微信流量中截获的 session-token

    Returns:
        API 响应的 JSON 字典，失败时包含 error 键
    """
    headers = {
        "session-token": token,
        "X-Track-Id": f"T{uuid.uuid4().hex.upper()}",
        "X-Appid": _APP_ID,
        "X-Page": "pages/gift/index",
        "X-Module-Name": "mmpaytxbbsmp",
        "xweb_xhr": "1",
        "Content-Type": "application/json",
        "Referer": f"https://servicewechat.com/{_APP_ID}/92/page-frame.html",
        "User-Agent": _USER_AGENT,
        "Accept": "*/*",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, verify=True) as client:
            resp = await client.post(_COUPON_API, json={}, headers=headers)
            data = resp.json()
            logger.info("领券 API 响应: errcode=%s", data.get("errcode", "unknown"))
            return data
    except httpx.TimeoutException:
        logger.error("领券 API 请求超时")
        return {"error": "请求超时"}
    except Exception as e:
        logger.error("领券 API 请求异常: %s", e)
        return {"error": str(e)}


# ── 结果解析 ──────────────────────────────────────────

def _parse_claim_result(response: dict) -> str:
    """解析领券 API 响应，返回中文结果消息

    Args:
        response: API 响应字典

    Returns:
        用户友好的结果消息
    """
    if "error" in response:
        return f"❌ 领券失败: {response['error']}"

    errcode = response.get("errcode", -1)
    msg = response.get("msg", "")

    # 成功领取
    if errcode == 0:
        coupon_info = response.get("data", {}).get("coupon_info", {})
        name = coupon_info.get("name", "免费提现券")
        face_value = coupon_info.get("face_value", 0)
        # face_value 单位是分，转换为元
        value_yuan = face_value / 100 if face_value else 0
        if value_yuan:
            return f"✅ 领券成功！获得「{name}」，面额 {value_yuan:.0f} 元，有效期365天"
        return f"✅ 领券成功！获得「{name}」，有效期365天"

    # 已经领过
    if "已在其它微信领取" in msg or "已经领取" in msg or "已领取" in msg:
        return "ℹ️ 今日已领取过，无需重复操作"

    # 登录失败
    if errcode == 268566816 or "登录" in msg or "鉴权" in msg:
        return f"❌ 登录鉴权失败，需要重新获取 token (errcode={errcode})"

    # 其他错误
    return f"❌ 领券失败: {msg or f'errcode={errcode}'}"


# ── 主编排函数 ─────────────────────────────────────────

async def auto_claim_coupon() -> str:
    """自动领券完整流程

    编排代理设置、mitmproxy 启动、小程序打开、token 提取、API 调用、
    清理恢复的完整生命周期。支持失败自动重试。

    Returns:
        中文结果消息，适合直接发送给用户
    """
    mitm_proc: Optional[subprocess.Popen] = None
    proxy_was_set = False

    try:
        # 清理旧的 token 文件
        if _TOKEN_FILE.exists():
            _TOKEN_FILE.unlink()
            logger.debug("已清理旧 token 文件")

        # 步骤1: 启动 mitmdump
        mitm_proc = await asyncio.to_thread(_start_mitmdump)
        if not mitm_proc:
            return "❌ 启动代理失败，请确认 mitmproxy 已安装 (pip install mitmproxy)"

        # 等待 mitmdump 启动
        await asyncio.sleep(2)

        # 步骤2: 设置系统代理
        proxy_was_set = await asyncio.to_thread(_set_macos_proxy, True)
        if not proxy_was_set:
            return "❌ 设置系统代理失败，请检查网络权限"

        # 重试循环
        for attempt in range(1, _MAX_RETRIES + 1):
            logger.info("领券尝试 %d/%d", attempt, _MAX_RETRIES)

            # 清理上一轮的 token 文件
            if attempt > 1:
                if _TOKEN_FILE.exists():
                    _TOKEN_FILE.unlink()
                await asyncio.to_thread(_close_mini_program)
                await asyncio.sleep(3)

            # 步骤3: 打开小程序
            opened = await asyncio.to_thread(_open_mini_program)
            if not opened:
                logger.warning("第 %d 次打开小程序失败", attempt)
                continue

            # 步骤4: 等待流量被截获
            await asyncio.sleep(8)

            # 步骤5: 提取 token
            token = await asyncio.to_thread(_extract_token)
            if not token:
                logger.warning("第 %d 次未能提取到 token", attempt)
                continue

            # 步骤5.5: 持久化保存 token（供后续有效期测试和云端使用）
            save_token_persistent(token)

            # 步骤6: 调用领券 API
            result = await _claim_coupon(token)
            result_msg = _parse_claim_result(result)

            # 判断是否需要重试
            if result_msg.startswith("✅") or result_msg.startswith("ℹ️"):
                # 成功或已领过，无需重试
                return result_msg

            # 登录失败等错误，可能 token 过期，重试获取新 token
            logger.warning("第 %d 次领券失败: %s", attempt, result_msg)

        # 所有重试都失败
        return "❌ 领券失败，已尝试 3 次。可能需要手动更新 mitmproxy 证书或重新登录微信"

    except Exception as e:
        logger.error("自动领券异常: %s", e)
        return f"❌ 领券过程出错: {e}"

    finally:
        # 必须恢复代理和清理进程
        if proxy_was_set:
            await asyncio.to_thread(_set_macos_proxy, False)
        _kill_mitmdump(mitm_proc)
        await asyncio.to_thread(_close_mini_program)
        logger.info("领券流程清理完毕")

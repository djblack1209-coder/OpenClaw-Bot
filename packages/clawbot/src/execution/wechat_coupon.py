"""微信「提现笔笔省」全平台自动领券模块

通过 mitmproxy 中间人代理截获微信小程序流量中的 session-token，
然后直接调用微信后端 API 领取所有可用优惠券，包括：
  - 免费提现券（365天有效期）
  - 美团外卖红包、京东购物券、滴滴出行券等平台优惠券

工作流:
  1. 设置 macOS 系统代理 → 127.0.0.1:8080
  2. 启动 mitmdump 监听，addon 截获 session-token
  3. 通过 weixin:// URL scheme 打开小程序触发流量
  4. 从截获的 token 文件中提取凭证
  5. 先领取免费提现券，再获取优惠券列表并逐个领取
  6. 恢复代理、清理进程

支持 token 持久化存储和有效期测试，为后续云端部署做准备。

参考:
  - https://github.com/whether1/txbbs-WxMiniProgramScript
  - https://github.com/LinYuanovo/AutoTaskScripts
"""

import asyncio
import fcntl
import json
import os
import re
import signal
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from src.http_client import ResilientHTTPClient

import logging

logger = logging.getLogger(__name__)

# 模块级别 HTTP 客户端（自动重试 + 熔断）
# verify_ssl=False: macOS Python 3.12 的 certifi 证书链不完整，调用微信 API 时会报 SSL 错误
_http = ResilientHTTPClient(timeout=15.0, name="wechat_coupon", verify_ssl=False)

# ── 常量 ──────────────────────────────────────────────

# API 基地址
_API_BASE = "https://discount.wxpapp.wechatpay.cn/txbbs-mall"

# 免费提现券 API（原有功能）
_COUPON_API = f"{_API_BASE}/coupon/deliveryfreewithdrawalcoupon"

# 全平台优惠券列表 API（美团/京东/滴滴等）
_LIST_GIFTS_API = f"{_API_BASE}/gift/listgifts"

# 领取指定优惠券 API
_REDEEM_GIFT_API = f"{_API_BASE}/gift/redeemgift"

# 查询提现免费额度 API
_BALANCE_API = f"{_API_BASE}/cashoutfree/getbalance"
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

# macOS 系统命令完整路径（LaunchAgent 启动时 PATH 不含 /usr/sbin）
_NETWORKSETUP = "/usr/sbin/networksetup"
# mitmdump 完整路径（优先使用 which 查找，降级到常见位置）
_MITMDUMP = None  # 延迟初始化


def _find_mitmdump() -> str:
    """查找 mitmdump 可执行文件的完整路径"""
    global _MITMDUMP
    if _MITMDUMP:
        return _MITMDUMP
    import shutil

    path = shutil.which("mitmdump")
    if path:
        _MITMDUMP = path
        return path
    # 常见 Homebrew / pip 安装路径
    for candidate in [
        "/opt/homebrew/bin/mitmdump",
        "/usr/local/bin/mitmdump",
        os.path.expanduser("~/.local/bin/mitmdump"),
    ]:
        if os.path.isfile(candidate):
            _MITMDUMP = candidate
            return candidate
    return "mitmdump"  # 降级，让后续报错更明确


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
    """使用已保存的 token 领取全平台优惠券（跳过 mitmproxy 流程）

    适用于 token 仍在有效期内的场景，可在任意平台运行（不依赖 macOS）。
    会依次领取提现券和所有平台优惠券（美团/京东/滴滴等）。
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

    # 调用全平台领券
    result_msg = await _claim_all_coupons(token)

    # 如果鉴权失败，提示用户刷新 token
    if "鉴权" in result_msg or "登录" in result_msg:
        return (
            f"{result_msg}\n\n⏰ 当前 token 是 {age_text} 获取的，已过期。\n请用 /coupon 重新获取，或手动提供新 token。"
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
                [_NETWORKSETUP, "-setwebproxy", _NETWORK_SERVICE, "127.0.0.1", str(_PROXY_PORT)],
                check=True,
                capture_output=True,
                timeout=10,
            )
            # 设置 HTTPS 代理
            subprocess.run(
                [_NETWORKSETUP, "-setsecurewebproxy", _NETWORK_SERVICE, "127.0.0.1", str(_PROXY_PORT)],
                check=True,
                capture_output=True,
                timeout=10,
            )
            logger.info("macOS 系统代理已开启 → 127.0.0.1:%d", _PROXY_PORT)
        else:
            # 关闭 HTTP 代理
            subprocess.run(
                [_NETWORKSETUP, "-setwebproxystate", _NETWORK_SERVICE, "off"],
                check=True,
                capture_output=True,
                timeout=10,
            )
            # 关闭 HTTPS 代理
            subprocess.run(
                [_NETWORKSETUP, "-setsecurewebproxystate", _NETWORK_SERVICE, "off"],
                check=True,
                capture_output=True,
                timeout=10,
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
                _find_mitmdump(),
                "-s",
                str(_MITM_ADDON),
                "-p",
                str(_PROXY_PORT),
                "--set",
                "block_global=false",
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
            check=True,
            capture_output=True,
            timeout=10,
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
    apple_script = """
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
    """
    try:
        subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True,
            timeout=5,
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


def _build_headers(token: str) -> dict:
    """构建笔笔省 API 通用请求头

    所有笔笔省 API 共用同一套认证头，只是 URL 不同。

    Args:
        token: 从微信流量中截获的 session-token

    Returns:
        请求头字典
    """
    return {
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


async def _claim_coupon(token: str) -> dict:
    """调用微信领券 API — 领取免费提现券

    发送 POST 请求到笔笔省后端，领取免费提现券。

    Args:
        token: 从微信流量中截获的 session-token

    Returns:
        API 响应的 JSON 字典，失败时包含 error 键
    """
    headers = _build_headers(token)

    try:
        resp = await _http.post(_COUPON_API, json={}, headers=headers)
        data = resp.json()
        logger.info("提现券 API 响应: errcode=%s", data.get("errcode", "unknown"))
        return data
    except httpx.TimeoutException:
        logger.error("提现券 API 请求超时")
        return {"error": "请求超时"}
    except Exception as e:
        logger.error("提现券 API 请求异常: %s", e)
        return {"error": str(e)}


async def _get_gifts_list(token: str) -> list[dict]:
    """获取笔笔省全平台优惠券列表

    调用 listgifts API 获取所有可领取的优惠券，包括美团外卖红包、
    京东购物券、滴滴出行券等。

    Args:
        token: session-token

    Returns:
        优惠券信息列表，每项包含 gift_id / gift_type / gift_status / coupon_info 等字段。
        请求失败返回空列表。
    """
    headers = _build_headers(token)
    # listgifts 是 GET 请求，带经纬度参数（传 0 表示不限地区）
    params = {"longitude": "0", "latitude": "0"}

    try:
        resp = await _http.get(_LIST_GIFTS_API, params=params, headers=headers)
        data = resp.json()
        errcode = data.get("errcode", -1)
        if errcode == 0:
            gifts = data.get("data", {}).get("gift_info_list", [])
            logger.info("获取到 %d 个优惠券条目", len(gifts))
            return gifts
        logger.warning("获取优惠券列表失败: errcode=%s, msg=%s", errcode, data.get("msg", ""))
        return []
    except httpx.TimeoutException:
        logger.error("获取优惠券列表超时")
        return []
    except Exception as e:
        logger.error("获取优惠券列表异常: %s", e)
        return []


async def _redeem_gift(token: str, gift_id: str) -> dict:
    """领取指定的平台优惠券

    通过 gift_id 调用 redeemgift API 领取单张优惠券。

    Args:
        token: session-token
        gift_id: 优惠券唯一标识（从 listgifts 返回）

    Returns:
        API 响应的 JSON 字典，失败时包含 error 键
    """
    headers = _build_headers(token)
    payload = {"gift_id": gift_id}

    try:
        resp = await _http.post(_REDEEM_GIFT_API, json=payload, headers=headers)
        data = resp.json()
        logger.info("领取优惠券 gift_id=%s 响应: errcode=%s", gift_id, data.get("errcode", "unknown"))
        return data
    except httpx.TimeoutException:
        logger.error("领取优惠券 gift_id=%s 超时", gift_id)
        return {"error": "请求超时"}
    except Exception as e:
        logger.error("领取优惠券 gift_id=%s 异常: %s", gift_id, e)
        return {"error": str(e)}


async def _get_balance(token: str) -> Optional[int]:
    """查询提现免费额度（单位：分）

    Args:
        token: session-token

    Returns:
        余额（分），失败返回 None
    """
    headers = _build_headers(token)

    try:
        resp = await _http.get(_BALANCE_API, headers=headers)
        data = resp.json()
        if data.get("errcode") == 0:
            balance = int(data.get("data", {}).get("balance", 0))
            logger.info("当前提现免费额度: %d 分 (%.2f 元)", balance, balance / 100)
            return balance
        logger.warning("查询余额失败: %s", data.get("msg", ""))
        return None
    except Exception as e:
        logger.error("查询余额异常: %s", e)
        return None


async def _claim_all_coupons(token: str) -> str:
    """全平台一键领券 — 提现券 + 美团/京东/滴滴等所有可领优惠券

    执行流程:
      1. 领取免费提现券
      2. 获取优惠券列表，筛选可领取的券
      3. 逐个领取平台优惠券
      4. 查询最终余额
      5. 汇总所有结果返回

    Args:
        token: session-token

    Returns:
        中文汇总消息，适合直接发送给用户
    """
    results: list[str] = []
    success_count = 0
    skip_count = 0
    fail_count = 0

    # ── 第一步：领取免费提现券 ──
    withdrawal_resp = await _claim_coupon(token)
    withdrawal_msg = _parse_single_claim_result(withdrawal_resp)
    results.append(f"📦 提现券: {withdrawal_msg}")
    if withdrawal_msg.startswith("✅"):
        success_count += 1
    elif withdrawal_msg.startswith("ℹ️"):
        skip_count += 1
    else:
        fail_count += 1

    # 如果提现券鉴权失败，说明 token 无效，直接返回不再继续
    if "鉴权" in withdrawal_msg or "登录" in withdrawal_msg:
        return withdrawal_msg

    # ── 第二步：获取全平台优惠券列表 ──
    gifts = await _get_gifts_list(token)

    # 筛选可领取的优惠券（类型为券 + 状态为可领取）
    available_gifts = [g for g in gifts if g.get("gift_type") == "GT_COUPON" and g.get("gift_status") == "GS_AVAILABLE"]

    if not available_gifts:
        results.append("🎁 平台优惠券: 暂无可领取的券")
    else:
        results.append(f"🎁 发现 {len(available_gifts)} 张可领平台优惠券:")

        for gift in available_gifts:
            gift_id = gift.get("gift_id", "")
            # 从 gift 中提取券名称（可能在 coupon_info 或 gift_name 字段）
            coupon_info = gift.get("coupon_info", {})
            gift_name = coupon_info.get("name", "") or gift.get("gift_name", "") or gift.get("name", "未知券")

            # 领取这张券
            redeem_resp = await _redeem_gift(token, gift_id)
            redeem_errcode = redeem_resp.get("errcode", -1)
            redeem_msg = redeem_resp.get("msg", "")

            if "error" in redeem_resp:
                # 网络/超时错误
                results.append(f"   ❌ {gift_name}: {redeem_resp['error']}")
                fail_count += 1
            elif redeem_errcode == 0:
                # 领取成功，尝试从响应中获取更详细的券名
                resp_gift_info = redeem_resp.get("data", {}).get("gift_info", {})
                resp_coupon_info = resp_gift_info.get("coupon_info", {})
                final_name = resp_coupon_info.get("name", gift_name)
                results.append(f"   ✅ {final_name}: 领取成功")
                success_count += 1
            elif "已" in redeem_msg and ("领" in redeem_msg or "兑" in redeem_msg):
                # 已经领过
                results.append(f"   ℹ️ {gift_name}: 已领取过")
                skip_count += 1
            else:
                results.append(f"   ❌ {gift_name}: {redeem_msg or f'errcode={redeem_errcode}'}")
                fail_count += 1

            # 每次领取间隔 1-2 秒，避免触发频率限制
            await asyncio.sleep(1 + (uuid.uuid4().int % 1000) / 1000)

    # ── 第三步：查询最终余额 ──
    balance = await _get_balance(token)
    if balance is not None:
        results.append(f"💰 当前提现免费额度: {balance / 100:.0f} 元")

    # ── 汇总 ──
    summary = f"📊 汇总: 成功 {success_count} | 已领 {skip_count} | 失败 {fail_count}"
    results.append(summary)

    return "\n".join(results)


# ── 结果解析 ──────────────────────────────────────────


def _parse_single_claim_result(response: dict) -> str:
    """解析单个领券 API 响应，返回中文结果消息

    仅用于解析提现券 API 的响应（deliveryfreewithdrawalcoupon）。

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
            return f"✅ 领取成功！获得「{name}」，面额 {value_yuan:.0f} 元，有效期365天"
        return f"✅ 领取成功！获得「{name}」，有效期365天"

    # 已经领过
    if "已在其它微信领取" in msg or "已经领取" in msg or "已领取" in msg:
        return "ℹ️ 今日已领取过，无需重复操作"

    # 登录失败
    if errcode == 268566816 or "登录" in msg or "鉴权" in msg:
        return f"❌ 登录鉴权失败，需要重新获取 token (errcode={errcode})"

    # 其他错误
    return f"❌ 领券失败: {msg or f'errcode={errcode}'}"


def _parse_claim_result(response: dict) -> str:
    """解析领券 API 响应（兼容旧调用方）

    保留此函数以兼容 test_saved_token 等使用旧接口的地方。

    Args:
        response: API 响应字典

    Returns:
        用户友好的结果消息
    """
    return _parse_single_claim_result(response)


# ── 主编排函数 ─────────────────────────────────────────


async def auto_claim_coupon() -> str:
    """自动领券完整流程

    编排代理设置、mitmproxy 启动、小程序打开、token 提取、API 调用、
    清理恢复的完整生命周期。支持失败自动重试。

    使用文件锁防止并发执行（历史上出现过 7 个 mitmdump 同时启动的问题）。

    Returns:
        中文结果消息，适合直接发送给用户
    """
    # ── 并发锁：防止多个领券流程同时运行 ──
    _LOCK_FILE = "/tmp/openclaw_coupon.lock"
    lock_fd = None
    try:
        lock_fd = open(_LOCK_FILE, "w")
        # 非阻塞方式获取排他锁，拿不到说明已有进程在执行
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # 获取锁失败 → 另一个领券流程正在运行
        logger.warning("领券文件锁获取失败，已有领券流程正在进行")
        if lock_fd:
            lock_fd.close()
        return "ℹ️ 领券正在进行中，请稍后"

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

            # 步骤6: 全平台一键领券（提现券 + 美团/京东/滴滴等）
            result_msg = await _claim_all_coupons(token)

            # 判断是否需要重试（只有 token 鉴权失败才重试）
            if "鉴权" not in result_msg and "登录" not in result_msg:
                # token 有效，领券流程完成（不管券是否已领过）
                return result_msg

            # 登录失败等错误，可能 token 过期，重试获取新 token
            logger.warning("第 %d 次领券失败（token 无效）: %s", attempt, result_msg)

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
        # 释放文件锁
        if lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass
        logger.info("领券流程清理完毕")

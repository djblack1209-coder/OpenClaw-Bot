"""
Execution Hub — 共享工具函数
从原 execution_hub.py 提取的通用工具方法
"""
import re
import subprocess
import logging
from dataclasses import dataclass
from email.header import decode_header

logger = logging.getLogger(__name__)


@dataclass
class ReminderItem:
    id: str = ""
    text: str = ""
    due_at: str = ""
    done: bool = False


def decode_mime(value=None):
    """解码 MIME 编码的邮件头"""
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for raw, enc in parts:
        if isinstance(raw, bytes):
            out.append(raw.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(str(raw))
    return "".join(out).strip()


def safe_int(raw=None, default=0):
    try:
        if raw is None:
            return default
        return int(raw)
    except (TypeError, ValueError) as e:  # noqa: F841
        return default


def safe_float(raw=None, default=0.0):
    try:
        if raw is None:
            return default
        return float(raw)
    except (TypeError, ValueError) as e:  # noqa: F841
        return default


def parse_hhmm(raw=None, fallback=(0, 0)):
    raw = raw or fallback
    text = str(raw or "").strip()
    if ":" not in text:
        return fallback
    left, right = text.split(":", 1)
    h = safe_int(left, fallback[0])
    m = safe_int(right, fallback[1])
    if h < 0 or h > 23 or m < 0 or m > 59:
        return fallback
    return (h, m)


def read_keychain_secret(service=None, account=None):
    """从 macOS Keychain 读取密码"""
    svc = str(service or "").strip()
    acc = str(account or "").strip() or "default"
    if not svc:
        return ""
    cp = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", svc, "-a", acc],
        check=False, capture_output=True, text=True, timeout=8,
    )
    if cp.returncode == 0:
        return str(cp.stdout or "").strip()
    return ""


def topic_slug(topic=None):
    """将话题转为 URL 安全的 slug"""
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", str(topic or "").strip()).strip("-")
    return text[:48] or "topic"


def normalize_monitor_text(text=None):
    """标准化文本用于去重比较"""
    value = re.sub(r"\s+", " ", str(text or "").strip()).lower()
    value = re.sub(r'["\'\`]+', "", value)
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)
    return value


def extract_json_object(text=None):
    """从文本中提取 JSON 对象（使用 json_repair 容错解析 LLM 输出）"""
    from json_repair import loads as jloads
    if not text:
        return None
    patterns = [r"```json\s*(\{.*?\})\s*```", r"```\s*(\{.*?\})\s*```"]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                payload = jloads(match.group(1))
                if isinstance(payload, dict):
                    return payload
            except Exception as e:  # noqa: F841
                continue
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            payload = jloads(text[start : end + 1])
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
    return None


def run_cmd(cmd, cwd=None, timeout=30):
    """运行外部命令并返回 stdout"""
    try:
        cp = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        return cp.stdout.strip() if cp.returncode == 0 else ""
    except Exception as e:
        logger.debug(f"[run_cmd] {cmd[0]} failed: {e}")
        return ""


def run_osascript(script):
    """运行 AppleScript 并返回结果"""
    try:
        cp = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15, check=False,
        )
        return cp.stdout.strip() if cp.returncode == 0 else ""
    except Exception as e:
        logger.debug(f"[run_osascript] failed: {e}")
        return ""

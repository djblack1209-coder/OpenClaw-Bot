"""
GLM-OCR 服务 — 生产级图片/文档文字识别

特性:
- ResilientHTTPClient（指数退避重试 + 熔断器 + 请求指标）
- 动态 API Key 读取（支持热重载）
- file_unique_id 去重缓存（避免重复调用）
- 文件大小校验（拒绝超限文件）
- 结构化错误返回（调用方可区分失败原因）
- 可观测性（成功率、延迟、调用量）
"""
import os
import time
import base64
import hashlib
import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Tuple

from src.http_client import ResilientHTTPClient, RetryConfig, CircuitBreaker, CircuitOpenError
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────

ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/layout_parsing"
OCR_MODEL = "glm-ocr"
MAX_FILE_SIZE = 10 * 1024 * 1024   # 10MB（智谱限制：图片≤10MB，PDF≤50MB）
MAX_PDF_SIZE = 50 * 1024 * 1024    # 50MB
OCR_TIMEOUT = int(os.getenv("GLM_OCR_TIMEOUT", "120"))

# ── 去重缓存 ─────────────────────────────────────────

_CACHE_MAX = 200
_CACHE_TTL = 3600  # 1 小时


class _LRUCache:
    """简易 LRU 缓存，带 TTL"""
    def __init__(self, maxsize: int = _CACHE_MAX, ttl: int = _CACHE_TTL):
        self._data: OrderedDict[str, Tuple[str, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: str) -> Optional[str]:
        if key not in self._data:
            return None
        text, ts = self._data[key]
        if time.time() - ts > self._ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return text

    def put(self, key: str, text: str):
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = (text, time.time())
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._data)


_cache = _LRUCache()

# ── 速率限制 ──────────────────────────────────────────

_OCR_RATE_WINDOW = 3600  # 1 小时
_OCR_RATE_LIMIT = 30     # 每用户每小时最多 30 次
_user_ocr_calls: dict[int, list[float]] = {}


def _check_rate_limit(user_id: int) -> Tuple[bool, str]:
    """检查用户 OCR 调用频率，返回 (allowed, reason)"""
    now = time.time()
    calls = _user_ocr_calls.get(user_id, [])
    calls = [t for t in calls if now - t < _OCR_RATE_WINDOW]
    _user_ocr_calls[user_id] = calls

    if len(calls) >= _OCR_RATE_LIMIT:
        remaining = int(_OCR_RATE_WINDOW - (now - calls[0]))
        return False, f"OCR 调用频率超限（{_OCR_RATE_LIMIT}次/小时），请 {remaining}s 后重试"
    return True, ""


def _record_ocr_call(user_id: int):
    calls = _user_ocr_calls.setdefault(user_id, [])
    calls.append(time.time())


# ── 错误类型 ──────────────────────────────────────────

@dataclass
class OcrResult:
    """OCR 结果，调用方可区分成功/失败/缓存命中"""
    ok: bool
    text: Optional[str] = None
    error: Optional[str] = None
    cached: bool = False
    tokens_used: int = 0


# ── HTTP 客户端（单例）────────────────────────────────

_client: Optional[ResilientHTTPClient] = None


def _get_client() -> ResilientHTTPClient:
    global _client
    if _client is None:
        _client = ResilientHTTPClient(
            timeout=OCR_TIMEOUT,
            retry_config=RetryConfig(
                max_retries=2,
                base_delay=1.0,
                max_delay=15.0,
                retryable_status_codes=(429, 500, 502, 503, 504),
            ),
            circuit_breaker=CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=120.0,
            ),
            name="glm-ocr",
        )
    return _client


def _get_api_key() -> str:
    """每次调用时动态读取，支持热重载"""
    return os.getenv("ZHIPU_API_KEY", "").strip()


# ── 核心 API ─────────────────────────────────────────

async def ocr_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    user_id: int = 0,
    file_unique_id: str = "",
) -> OcrResult:
    """
    调用 GLM-OCR API 识别图片/PDF 文字。

    Args:
        image_bytes: 文件二进制内容
        mime_type: MIME 类型
        user_id: 用户 ID（用于速率限制）
        file_unique_id: Telegram file_unique_id（用于去重缓存）

    Returns:
        OcrResult 结构化结果
    """
    api_key = _get_api_key()
    if not api_key:
        return OcrResult(ok=False, error="ZHIPU_API_KEY 未配置")

    # 文件大小校验
    is_pdf = mime_type == "application/pdf"
    limit = MAX_PDF_SIZE if is_pdf else MAX_FILE_SIZE
    if len(image_bytes) > limit:
        size_mb = len(image_bytes) / (1024 * 1024)
        limit_mb = limit / (1024 * 1024)
        return OcrResult(ok=False, error=f"文件过大（{size_mb:.1f}MB），限制 {limit_mb:.0f}MB")

    # 去重缓存
    cache_key = file_unique_id or hashlib.md5(image_bytes[:4096]).hexdigest()
    cached = _cache.get(cache_key)
    if cached is not None:
        logger.info(f"[OCR] 缓存命中: {cache_key[:16]}...")
        return OcrResult(ok=True, text=cached, cached=True)

    # 速率限制
    if user_id:
        allowed, reason = _check_rate_limit(user_id)
        if not allowed:
            return OcrResult(ok=False, error=reason)

    # 构建请求
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{mime_type};base64,{b64}"

    try:
        client = _get_client()
        resp = await client.post(
            ZHIPU_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": OCR_MODEL, "file": data_uri},
        )

        if resp.status_code == 401 or resp.status_code == 403:
            return OcrResult(ok=False, error="API Key 无效或已过期，请重新配置 ZHIPU_API_KEY")

        if resp.status_code == 429:
            return OcrResult(ok=False, error="智谱 API 配额用尽，请稍后重试")

        if resp.status_code != 200:
            body = resp.text[:200] if resp.text else ""
            return OcrResult(ok=False, error=f"API 错误 ({resp.status_code}): {body}")

        result = resp.json()
        text = result.get("md_results", "").strip()
        tokens = result.get("usage", {}).get("total_tokens", 0)

        if not text:
            return OcrResult(ok=True, text=None, tokens_used=tokens)

        # 写入缓存 & 记录调用
        _cache.put(cache_key, text)
        if user_id:
            _record_ocr_call(user_id)

        logger.info(f"[OCR] 成功: {len(text)} 字符, {tokens} tokens, user={user_id}")
        return OcrResult(ok=True, text=text, tokens_used=tokens)

    except CircuitOpenError as e:  # noqa: F841
        return OcrResult(ok=False, error="OCR 服务暂时不可用（熔断保护），请稍后重试")
    except Exception as e:
        logger.error(f"[OCR] 异常: {scrub_secrets(str(e))}", exc_info=True)
        return OcrResult(ok=False, error=f"OCR 请求异常: {type(e).__name__}")


# ── 可观测性 ──────────────────────────────────────────

def get_ocr_status() -> dict:
    """返回 OCR 服务状态，可接入 /cost 或 /status 命令"""
    client = _get_client()
    return {
        "api_key_configured": bool(_get_api_key()),
        "cache_size": _cache.size,
        "rate_limited_users": len(_user_ocr_calls),
        "http": client.get_status(),
    }

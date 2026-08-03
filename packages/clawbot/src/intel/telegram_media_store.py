"""基于 Telegram 私有素材会话的图片存储与 file_id 复用。"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.intel.db.store import (
    get_telegram_media_asset,
    invalidate_telegram_media_asset,
    put_telegram_media_asset,
)

MAX_PHOTO_BYTES = 10 * 1024 * 1024
_PHOTO_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class PhotoSender(Protocol):
    """Telegram 图片发送最小接口。"""

    def send_photo(
        self,
        chat_id: str,
        photo: str,
        *,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """上传图片并返回已脱敏的 Telegram 响应。"""


class TelegramMediaStoreError(RuntimeError):
    """素材上传或校验失败。"""


@dataclass(frozen=True)
class TelegramMediaRef:
    """同一 Bot 可安全复用的 Telegram 媒体引用。"""

    asset_key: str
    file_id: str
    file_unique_id: str
    mime_type: str
    byte_size: int
    content_hash: str


def _mime_type(path: Path) -> str:
    """按文件头识别受支持的图片类型。"""
    header = path.read_bytes()[:16]
    if any(header.startswith(signature) for signature in _PHOTO_SIGNATURES["image/jpeg"]):
        return "image/jpeg"
    if any(header.startswith(signature) for signature in _PHOTO_SIGNATURES["image/png"]):
        return "image/png"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    raise TelegramMediaStoreError("封面仅支持 JPEG、PNG 或 WEBP")


def _photo_metadata(path: Path) -> tuple[str, int, str]:
    """校验素材大小并返回 MIME、字节数和内容哈希。"""
    if not path.is_file():
        raise TelegramMediaStoreError("封面文件不存在")
    size = path.stat().st_size
    if size <= 0 or size > MAX_PHOTO_BYTES:
        raise TelegramMediaStoreError("封面大小必须在 1 字节到 10MB 之间")
    mime_type = _mime_type(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return mime_type, size, digest


def _row_to_ref(asset_key: str, row: dict[str, Any]) -> TelegramMediaRef | None:
    if not row:
        return None
    return TelegramMediaRef(
        asset_key=asset_key,
        file_id=str(row.get("file_id") or ""),
        file_unique_id=str(row.get("file_unique_id") or ""),
        mime_type=str(row.get("mime_type") or "image/jpeg"),
        byte_size=int(row.get("byte_size") or 0),
        content_hash=str(row.get("content_hash") or ""),
    )


class SqliteTelegramMediaStore:
    """搬运 tgNetDisc 的 Telegram 存储核心，不引入公开代理或第二轮询器。"""

    def __init__(
        self,
        *,
        db_path: str | Path,
        sender: PhotoSender,
        env: dict[str, str] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.sender = sender
        self.env = dict(os.environ if env is None else env)

    def get(self, asset_key: str) -> TelegramMediaRef | None:
        """读取可用媒体引用并更新最近使用时间。"""
        return _row_to_ref(asset_key, get_telegram_media_asset(self.db_path, asset_key))

    def put_photo(self, asset_key: str, source: str | Path) -> TelegramMediaRef:
        """上传一次图片到私有素材会话并持久化最大尺寸 file_id。"""
        media_chat_id = str(self.env.get("INTEL_BRIEF_TELEGRAM_MEDIA_CHAT_ID") or "").strip()
        if not media_chat_id:
            raise TelegramMediaStoreError("未配置 Telegram 私有素材会话")
        source_path = Path(source)
        mime_type, byte_size, content_hash = _photo_metadata(source_path)
        cached = self.get(asset_key)
        if cached is not None and cached.content_hash == content_hash:
            return cached
        result = self.sender.send_photo(media_chat_id, str(source_path))
        if not result.get("success"):
            raise TelegramMediaStoreError(str(result.get("error") or "Telegram 素材上传失败")[:300])
        file_id = str(result.get("photo_file_id") or "").strip()
        if not file_id:
            raise TelegramMediaStoreError("Telegram 未返回可复用的 photo file_id")
        file_unique_id = str(result.get("photo_file_unique_id") or "").strip()
        put_telegram_media_asset(
            self.db_path,
            asset_key=asset_key,
            file_id=file_id,
            file_unique_id=file_unique_id,
            mime_type=mime_type,
            byte_size=byte_size,
            content_hash=content_hash,
        )
        stored = self.get(asset_key)
        if stored is None:
            raise TelegramMediaStoreError("Telegram 媒体引用保存失败")
        return stored

    def touch(self, asset_key: str) -> None:
        """触碰素材引用；读取动作会原子更新最近使用时间。"""
        self.get(asset_key)

    def invalidate(self, asset_key: str) -> None:
        """使失效 file_id 下次重新上传。"""
        invalidate_telegram_media_asset(self.db_path, asset_key)

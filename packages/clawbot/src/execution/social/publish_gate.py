"""社媒发布授权门：审核快照绑定 + 短时一次性确认。"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

_CONTENT_FIELDS = ("platform", "title", "text", "content", "body", "images")
_CONFIRMATION_TTL_SECONDS = 10 * 60


def _lock_path() -> Path:
    """返回可配置的跨进程发布锁文件。"""
    configured = str(os.getenv("OPENCLAW_PUBLISH_LOCK_PATH") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".openclaw" / "locks" / "social-publish.lock"


def _acquire_file_lock(handle: BinaryIO) -> None:
    """使用操作系统原生能力阻塞获取独占文件锁。"""
    if os.name == "nt":
        import errno
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                time.sleep(0.05)

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_file_lock(handle: BinaryIO) -> None:
    """释放当前平台的独占文件锁。"""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class CrossProcessRLock:
    """同时串行化线程和进程，并允许同一线程嵌套进入。"""

    def __init__(self) -> None:
        self._thread_lock = threading.RLock()
        self._local = threading.local()

    def acquire(self) -> bool:
        """获取进程内锁；首次进入时再获取操作系统文件锁。"""
        self._thread_lock.acquire()
        depth = int(getattr(self._local, "depth", 0))
        if depth:
            self._local.depth = depth + 1
            return True

        descriptor: int | None = None
        handle: BinaryIO | None = None
        try:
            path = _lock_path()
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            handle = os.fdopen(descriptor, "r+b", buffering=0)
            descriptor = None
            _acquire_file_lock(handle)
            self._local.handle = handle
            self._local.depth = 1
            return True
        except Exception:
            if handle is not None:
                handle.close()
            elif descriptor is not None:
                os.close(descriptor)
            self._thread_lock.release()
            raise

    def release(self) -> None:
        """离开最外层临界区时释放文件锁和文件句柄。"""
        depth = int(getattr(self._local, "depth", 0))
        if depth <= 0:
            raise RuntimeError("不能释放未持有的社媒发布锁")

        try:
            if depth > 1:
                self._local.depth = depth - 1
                return

            handle = getattr(self._local, "handle", None)
            if handle is not None:
                try:
                    _release_file_lock(handle)
                finally:
                    handle.close()
            self._local.depth = 0
            self._local.handle = None
        finally:
            self._thread_lock.release()

    def __enter__(self) -> "CrossProcessRLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.release()


publish_state_lock = CrossProcessRLock()

def mutate_state_transaction[StateResult](
    load_state: Callable[[], dict[str, Any]],
    save_state: Callable[[dict[str, Any]], None],
    mutator: Callable[[dict[str, Any]], StateResult],
) -> StateResult:
    """在同一把跨进程锁内完成状态文件的读、改、写。"""
    with publish_state_lock:
        state = load_state()
        result = mutator(state)
        save_state(state)
        return result


def draft_content_hash(draft: dict[str, Any]) -> str:
    """计算用户实际审核内容的稳定指纹。"""
    snapshot = {key: draft.get(key) for key in _CONTENT_FIELDS if key in draft}
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def invalidate_publish_authorization(draft: dict[str, Any]) -> None:
    """内容变化后撤销旧审核和所有未使用确认。"""
    for key in (
        "approved_content_hash",
        "confirmation_token_hash",
        "confirmation_content_hash",
        "confirmation_expires_at",
        "confirmation_issued_at",
        "confirmation_used_at",
        "confirmation_used",
    ):
        draft.pop(key, None)


def seal_approved_draft(draft: dict[str, Any]) -> None:
    """把当前内容固化为唯一允许发布的审核快照。"""
    invalidate_publish_authorization(draft)
    draft["approved_content_hash"] = draft_content_hash(draft)


def issue_publish_confirmation(draft: dict[str, Any]) -> dict[str, Any]:
    """为未变更的已审核草稿签发短时一次性确认。"""
    if str(draft.get("status") or "").lower() in {
        "publishing",
        "published",
        "manual_reconciliation_required",
    }:
        return {
            "success": False,
            "requires_final_confirmation": False,
            "manual_reconciliation_required": str(draft.get("status") or "").lower()
            == "manual_reconciliation_required",
            "error": "草稿正在发布、已经发布或等待人工对账，不能重复签发确认",
        }
    current_hash = draft_content_hash(draft)
    if draft.get("review_status") != "approved":
        return {
            "success": False,
            "requires_review": True,
            "error": "草稿尚未审核通过",
        }
    if not draft.get("approved_content_hash") or not hmac.compare_digest(
        str(draft.get("approved_content_hash")),
        current_hash,
    ):
        invalidate_publish_authorization(draft)
        draft["review_status"] = "pending"
        draft["status"] = "needs_review"
        return {
            "success": False,
            "requires_review": True,
            "error": "草稿内容已变化，需要重新审核",
        }

    token = secrets.token_urlsafe(32)
    now = time.time()
    draft["confirmation_token_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
    draft["confirmation_content_hash"] = current_hash
    draft["confirmation_issued_at"] = now
    draft["confirmation_expires_at"] = now + _CONFIRMATION_TTL_SECONDS
    draft["confirmation_used"] = False
    draft.pop("confirmation_used_at", None)
    return {
        "success": True,
        "confirmation_token": token,
        "expires_at": draft["confirmation_expires_at"],
    }


def consume_publish_confirmation(
    draft: dict[str, Any],
    confirmation_token: str,
) -> dict[str, Any]:
    """原子消费一次性确认；失败时不允许调用任何外部发布器。"""
    if draft.get("review_status") != "approved":
        return {
            "success": False,
            "requires_review": True,
            "error": "草稿尚未审核通过",
        }

    current_hash = draft_content_hash(draft)
    approved_hash = str(draft.get("approved_content_hash") or "")
    confirmed_hash = str(draft.get("confirmation_content_hash") or "")
    if not approved_hash or not hmac.compare_digest(approved_hash, current_hash):
        invalidate_publish_authorization(draft)
        draft["review_status"] = "pending"
        draft["status"] = "needs_review"
        return {
            "success": False,
            "requires_review": True,
            "error": "草稿内容与审核快照不一致，需要重新审核",
        }
    if not confirmed_hash:
        return {
            "success": False,
            "requires_final_confirmation": True,
            "error": "发布前需要一次性最终确认",
        }
    if not hmac.compare_digest(confirmed_hash, current_hash):
        invalidate_publish_authorization(draft)
        draft["review_status"] = "pending"
        draft["status"] = "needs_review"
        return {
            "success": False,
            "requires_review": True,
            "error": "最终确认对应的草稿内容已变化，需要重新审核",
        }

    if draft.get("confirmation_used"):
        return {
            "success": False,
            "requires_final_confirmation": True,
            "error": "发布确认已使用，请重新确认",
        }
    if float(draft.get("confirmation_expires_at") or 0) < time.time():
        return {
            "success": False,
            "requires_final_confirmation": True,
            "error": "发布确认已过期，请重新确认",
        }

    expected_hash = str(draft.get("confirmation_token_hash") or "")
    supplied_hash = hashlib.sha256(str(confirmation_token or "").encode("utf-8")).hexdigest()
    if not expected_hash or not hmac.compare_digest(expected_hash, supplied_hash):
        return {
            "success": False,
            "requires_final_confirmation": True,
            "error": "缺少或无效的一次性发布确认",
        }

    draft["confirmation_used"] = True
    draft["confirmation_used_at"] = time.time()
    return {"success": True}

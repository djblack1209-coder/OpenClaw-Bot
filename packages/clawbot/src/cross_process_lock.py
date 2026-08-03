"""跨平台、跨线程和跨进程的可重入文件锁。"""

import os
import threading
import time
from pathlib import Path
from typing import BinaryIO


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


class CrossProcessFileRLock:
    """串行化同一路径的线程和进程，并允许同线程嵌套进入。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._thread_lock = threading.RLock()
        self._local = threading.local()

    def acquire(self) -> bool:
        """首次进入时获取文件锁，嵌套进入只增加引用计数。"""
        self._thread_lock.acquire()
        depth = int(getattr(self._local, "depth", 0))
        if depth:
            self._local.depth = depth + 1
            return True

        descriptor: int | None = None
        handle: BinaryIO | None = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
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
        """最外层事务结束时释放文件锁和句柄。"""
        depth = int(getattr(self._local, "depth", 0))
        if depth <= 0:
            raise RuntimeError("不能释放未持有的跨进程文件锁")

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

    def __enter__(self) -> "CrossProcessFileRLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.release()


_FILE_LOCKS: dict[Path, CrossProcessFileRLock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def cross_process_file_lock(path: str | Path) -> CrossProcessFileRLock:
    """让同一进程内所有调用者复用指定路径的可重入文件锁。"""
    normalized = Path(path).expanduser().resolve()
    with _FILE_LOCKS_GUARD:
        lock = _FILE_LOCKS.get(normalized)
        if lock is None:
            lock = CrossProcessFileRLock(normalized)
            _FILE_LOCKS[normalized] = lock
        return lock

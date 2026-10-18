"""
core/file_lock.py
─────────────────────────────────────────────────────────────────
Cross-platform inter-process file lock (Windows msvcrt / Unix fcntl)
combined with in-process threading.RLock for thread-safe and
multi-worker-safe file synchronization.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from types import TracebackType
from typing import ClassVar

from typing_extensions import Self

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class _LockContext:
    def __init__(self) -> None:
        self.thread_lock: threading.RLock = threading.RLock()
        self.depth: int = 0
        self.fd: int | None = None


class InterProcessFileLock:
    """
    Re-entrant, inter-process file lock.
    Combines per-path threading.RLock with kernel-level file locking
    (msvcrt on Windows, fcntl on POSIX).
    """

    _registry: ClassVar[dict[str, _LockContext]] = {}
    _registry_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, lock_file: Path | str, timeout: float = 10.0) -> None:
        self.lock_file: Path = Path(lock_file)
        self.timeout: float = timeout
        self._abs_path: str = str(self.lock_file.resolve())

        with self._registry_lock:
            if self._abs_path not in self._registry:
                self._registry[self._abs_path] = _LockContext()
            self._ctx: _LockContext = self._registry[self._abs_path]

    def acquire(self) -> None:
        self._ctx.thread_lock.acquire()
        if self._ctx.depth > 0:
            self._ctx.depth += 1
            return

        start = time.monotonic()
        fd: int | None = None
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR)
            # Ensure file has at least 1 byte for msvcrt locking
            if os.path.getsize(str(self.lock_file)) == 0:
                os.write(fd, b"\x00")
                os.lseek(fd, 0, os.SEEK_SET)

            while True:
                try:
                    if sys.platform == "win32":
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._ctx.fd = fd
                    self._ctx.depth = 1
                    return
                except OSError:
                    if time.monotonic() - start > self.timeout:
                        os.close(fd)
                        raise TimeoutError(
                            f"Could not acquire file lock on {self.lock_file} within {self.timeout}s"
                        )
                    time.sleep(0.02)
        except Exception:
            self._ctx.thread_lock.release()
            raise

    def release(self) -> None:
        try:
            if self._ctx.depth > 1:
                self._ctx.depth -= 1
                return

            if self._ctx.depth == 1:
                fd = self._ctx.fd
                self._ctx.fd = None
                self._ctx.depth = 0
                if fd is not None:
                    try:
                        if sys.platform == "win32":
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)
        finally:
            self._ctx.thread_lock.release()

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()

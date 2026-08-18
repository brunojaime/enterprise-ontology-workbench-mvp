"""Atomic, process-safe structured audit records for controlled MCP writes."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

if os.name == "nt":  # pragma: no cover - exercised by the PowerShell gate host
    import msvcrt
else:
    import fcntl


class AuditWriteError(OSError):
    """An audit record could not be published atomically."""

    def __init__(self, message: str, *, rollback_failed: bool = False) -> None:
        super().__init__(message)
        # Kept for the public error contract. Atomic replacement never publishes
        # a record that subsequently needs a compensating truncate.
        self.rollback_failed = rollback_failed


class RepositoryFileLock:
    """Advisory lock shared by threads and independent local MCP processes."""

    def __init__(self, repository_root: Path, path: Path) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.path = path.absolute()
        self._thread_lock = threading.RLock()
        self._descriptor: int | None = None

    def __enter__(self) -> RepositoryFileLock:
        self._thread_lock.acquire()
        try:
            self._prepare_parent()
            flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.path, flags, 0o600)
            try:
                if os.name == "nt":  # pragma: no cover - requires Windows
                    if os.fstat(descriptor).st_size == 0:
                        os.write(descriptor, b"\0")
                        os.fsync(descriptor)
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
            except Exception:
                os.close(descriptor)
                raise
            self._descriptor = descriptor
            return self
        except Exception:
            self._thread_lock.release()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        descriptor = self._descriptor
        self._descriptor = None
        try:
            if descriptor is not None:
                if os.name == "nt":  # pragma: no cover - requires Windows
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
        finally:
            self._thread_lock.release()

    def _prepare_parent(self) -> None:
        if not self.path.is_relative_to(self.repository_root):
            raise ValueError("lock file must remain inside the repository")
        current = self.repository_root
        for component in self.path.relative_to(self.repository_root).parts[:-1]:
            current /= component
            if current.is_symlink():
                raise ValueError("lock parent cannot be a symbolic link")
            if current.exists() and not current.is_dir():
                raise ValueError("lock parent must be a directory")
            current.mkdir(mode=0o700, exist_ok=True)
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ValueError("lock must be a regular local file")


class WriteAuditLog:
    def __init__(self, repository_root: Path, path: Path) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.path = path.absolute()
        self._lock = RepositoryFileLock(
            self.repository_root,
            self.path.with_name(f"{self.path.name}.lock"),
        )
        self._prepare_parent()

    def preflight(self) -> None:
        """Prove that the sink directory can durably hold a new audit image."""

        with self._lock:
            self._prepare_parent()
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.preflight-",
                dir=self.path.parent,
            )
            try:
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
                Path(temporary_name).unlink(missing_ok=True)

    def record(
        self,
        *,
        agent: str,
        tool: str,
        files: tuple[str, ...],
        result: str,
        code: str | None = None,
        invocation_id: str | None = None,
    ) -> None:
        entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "agent": agent,
            "tool": tool,
            "files": list(files),
            "result": result,
        }
        if invocation_id is not None:
            entry["invocation_id"] = invocation_id
        if code is not None:
            entry["code"] = code
        encoded = (
            json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with self._lock:
            self._prepare_parent()
            previous = self.path.read_bytes() if self.path.exists() else b""
            self._replace(previous + encoded)

    def _replace(self, content: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=self.path.parent,
        )
        temporary = Path(temporary_name)
        published = False
        try:
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(content):
                offset += os.write(descriptor, content[offset:])
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, self.path)
            published = True
            # The record is already the single visible terminal state. A parent
            # directory fsync improves crash durability but cannot be treated as
            # a reversible append after the atomic replacement has succeeded.
            with suppress(OSError):
                directory = os.open(self.path.parent, os.O_RDONLY)
                try:
                    with suppress(OSError):
                        os.fsync(directory)
                finally:
                    with suppress(OSError):
                        os.close(directory)
        except OSError as error:
            raise AuditWriteError("audit record was not published atomically") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if not published:
                temporary.unlink(missing_ok=True)

    def _prepare_parent(self) -> None:
        if not self.path.is_relative_to(self.repository_root):
            raise ValueError("audit log must remain inside the repository")
        current = self.repository_root
        for component in self.path.relative_to(self.repository_root).parts[:-1]:
            current /= component
            if current.is_symlink():
                raise ValueError("audit log parent cannot be a symbolic link")
            if current.exists() and not current.is_dir():
                raise ValueError("audit log parent must be a directory")
            current.mkdir(mode=0o700, exist_ok=True)
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ValueError("audit log must be a regular local file")

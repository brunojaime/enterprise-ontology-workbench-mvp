"""Read-only Git history for canonical RDF source files."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitHistoryEntry:
    """One real commit touching a canonical RDF source file."""

    commit: str
    author: str
    date: str
    subject: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "commit": self.commit,
            "author": self.author,
            "date": self.date,
            "subject": self.subject,
            "path": self.path,
        }


class GitHistoryService:
    """Inspect Git without changing the repository or exposing P07 mutations."""

    def __init__(
        self,
        repository_root: Path,
        knowledge_root: Path,
        *,
        max_entries: int = 50,
        timeout_seconds: float = 5.0,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.repository_root = repository_root.resolve()
        self.knowledge_root = knowledge_root.resolve()
        if not self.knowledge_root.is_relative_to(self.repository_root):
            raise ValueError("knowledge root must be within the repository")
        self.max_entries = max_entries
        self.timeout_seconds = timeout_seconds

    def read(
        self,
        source_paths: tuple[Path, ...],
        *,
        revision: str | None = None,
    ) -> tuple[GitHistoryEntry, ...]:
        """Return real commits, or an empty result for unversioned sources."""

        entries: dict[tuple[str, str], GitHistoryEntry] = {}
        for source_path in source_paths:
            relative = self._relative_source_path(source_path)
            if relative is None:
                continue
            command = [
                "git",
                "log",
                "--follow",
                "-z",
                "--format=%H%x00%an%x00%aI%x00%s%x00",
            ]
            if revision is not None:
                command.append(revision)
            command.extend(("--", relative))
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.repository_root,
                    check=False,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if completed.returncode != 0:
                continue
            for record in completed.stdout.split(b"\x00\x00"):
                fields = record.strip(b"\n").split(b"\x00")
                if len(fields) != 4 or not fields[0]:
                    continue
                commit, author, date, subject = (
                    field.decode("utf-8", errors="replace") for field in fields
                )
                entry = GitHistoryEntry(
                    commit=commit,
                    author=author,
                    date=date,
                    subject=subject,
                    path=relative,
                )
                entries[(entry.commit, entry.path)] = entry
        return tuple(
            sorted(
                entries.values(),
                key=lambda entry: (
                    entry.date,
                    entry.commit,
                    entry.path,
                ),
                reverse=True,
            )[: self.max_entries]
        )

    def _relative_source_path(self, source_path: Path) -> str | None:
        # Source paths are captured by FilesystemRdfStore when the immutable
        # runtime snapshot is built. Git history must remain queryable if the
        # working tree later deletes or renames that file, so do not resolve it
        # against the mutable filesystem here.
        absolute = Path(os.path.abspath(source_path))
        if not absolute.is_relative_to(self.knowledge_root):
            return None
        if not absolute.is_relative_to(self.repository_root):
            return None
        return absolute.relative_to(self.repository_root).as_posix()

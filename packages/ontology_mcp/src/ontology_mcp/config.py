"""Confined configuration for the local stdio MCP server."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class McpSettings:
    repository_root: Path
    knowledge_root: Path
    namespace_config: Path
    audit_log: Path
    write_enabled: bool = False

    @classmethod
    def from_repository(
        cls,
        repository: Path,
        *,
        audit_log: Path | None = None,
        write_enabled: bool = False,
    ) -> McpSettings:
        try:
            root = repository.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError("repository path is unavailable") from error
        if not root.is_dir():
            raise ValueError("repository path must be a directory")
        knowledge = _regular_directory(root / "knowledge", root)
        namespace = _regular_file(root / "config/namespace.yaml", root)
        requested_log = audit_log or Path(".eow/audit/mcp-write.jsonl")
        candidate = requested_log if requested_log.is_absolute() else root / requested_log
        confined_log = _confined_missing(candidate, root)
        return cls(root, knowledge, namespace, confined_log, write_enabled)


def _regular_directory(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"configured directory cannot be a symbolic link: {path.name}")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"configured directory is unavailable: {path.name}") from error
    if not resolved.is_relative_to(root) or not resolved.is_dir():
        raise ValueError(f"configured directory escapes the repository: {path.name}")
    return resolved


def _regular_file(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"configured file cannot be a symbolic link: {path.name}")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"configured file is unavailable: {path.name}") from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"configured file escapes the repository: {path.name}")
    return resolved


def _confined_missing(path: Path, root: Path) -> Path:
    lexical = path.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise ValueError("audit log must remain inside the repository") from error
    if ".." in relative.parts:
        raise ValueError("audit log must remain inside the repository")
    current = root
    for component in relative.parts[:-1]:
        current /= component
        if current.is_symlink():
            raise ValueError("audit log parent cannot be a symbolic link")
        if current.exists() and not current.is_dir():
            raise ValueError("audit log parent must be a directory")
    candidate = lexical.resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ValueError("audit log must remain inside the repository")
    if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
        raise ValueError("audit log must be a regular local file")
    return candidate


def parse_settings(argv: list[str] | None = None) -> McpSettings:
    parser = argparse.ArgumentParser(prog="ontology-mcp")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--audit-log", type=Path)
    parser.add_argument("--write-enabled", action="store_true")
    arguments = parser.parse_args(argv)
    return McpSettings.from_repository(
        arguments.repository,
        audit_log=arguments.audit_log,
        write_enabled=arguments.write_enabled,
    )

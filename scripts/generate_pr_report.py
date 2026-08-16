"""Generate deterministic semantic artifacts and GitHub job-summary Markdown."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ontology_core import FilesystemRdfStore, PullRequestGovernanceService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Git command failed")
    return completed.stdout.strip()


def _changed_paths(root: Path, base: str) -> tuple[str, ...]:
    output = subprocess.run(
        ("git", "diff", "--name-only", "-z", base, "--", "knowledge", "config"),
        cwd=root,
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout
    untracked = subprocess.run(
        ("git", "ls-files", "--others", "--exclude-standard", "-z", "--", "knowledge", "config"),
        cwd=root,
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout
    return tuple(
        sorted(
            {
                path.decode("utf-8")
                for payload in (output, untracked)
                for path in payload.split(b"\0")
                if path
            }
        )
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    arguments = _parser().parse_args()
    root = arguments.repository.resolve(strict=True)
    output = arguments.output.resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    head = arguments.head or _git(root, "rev-parse", "HEAD")
    store = FilesystemRdfStore(root / "knowledge", root / "config/namespace.yaml")
    report = PullRequestGovernanceService(root, store).build(
        base_ref=arguments.base,
        head_ref=head,
        changed_paths=_changed_paths(root, arguments.base),
    )
    _write_json(output / "governance-report.json", report.to_dict())
    _write_json(output / "validation.json", report.validation.to_dict())
    _write_json(
        output / "semantic-diff.json",
        (
            report.semantic_diff.to_dict()
            if report.semantic_diff is not None
            else {"status": "not_executable"}
        ),
    )
    _write_json(
        output / "deprecated-usages.json",
        {
            "count": len(report.deprecated_usages),
            "items": [item.to_dict() for item in report.deprecated_usages],
        },
    )
    (output / "pr-summary.md").write_text(report.to_markdown(), encoding="utf-8")
    for warning in report.warnings:
        safe = warning.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::warning title=Gobernanza semántica::{safe}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

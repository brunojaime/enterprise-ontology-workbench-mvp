"""Run the repository governance gate locally and retain an auditable bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ontology_core import content_fingerprint


@dataclass(frozen=True)
class GateCommand:
    command_id: str
    argv: tuple[str, ...]


class GateError(RuntimeError):
    """Raised when the local gate cannot safely run."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="main")
    parser.add_argument(
        "--include-smoke",
        action="store_true",
        help="Include the container package smoke required by the P12 publication gate.",
    )
    parser.add_argument(
        "--record-git-note",
        action="store_true",
        help="Append the passed receipt digest to refs/notes/eow-local-gates.",
    )
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
        raise GateError(completed.stderr.strip() or "Git command failed")
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _snapshot(root: Path) -> dict[str, str]:
    branch = _git(root, "branch", "--show-current")
    if not branch.startswith("proposal/"):
        raise GateError("The local gate only runs from a proposal/* branch.")
    dirty = _git(root, "status", "--porcelain")
    if dirty:
        raise GateError("The local gate requires a clean worktree and index.")
    return {
        "branch": branch,
        "head": _git(root, "rev-parse", "HEAD"),
    }


def _assert_stable(root: Path, expected: dict[str, str]) -> None:
    current = _snapshot(root)
    if current != expected:
        raise GateError("Branch or HEAD changed while the local gate was running.")


def gate_commands(root: Path, base: str, include_smoke: bool) -> tuple[GateCommand, ...]:
    if platform.system() == "Windows":
        shell_commands = (
            GateCommand("tests", ("pwsh", "-File", "scripts/test.ps1")),
            GateCommand("validation", ("pwsh", "-File", "scripts/validate.ps1")),
            GateCommand("build", ("pwsh", "-File", "scripts/build.ps1")),
        )
    else:
        shell_commands = (
            GateCommand("tests", ("bash", "scripts/test.sh")),
            GateCommand("validation", ("bash", "scripts/validate.sh")),
            GateCommand("build", ("bash", "scripts/build.sh")),
        )
    commands = [*shell_commands]
    if include_smoke:
        commands.append(GateCommand("package_smoke", (sys.executable, "scripts/smoke_package.py")))
    commands.append(
        GateCommand(
            "semantic_governance",
            (
                sys.executable,
                "scripts/generate_pr_report.py",
                "--base",
                base,
                "--head",
                "HEAD",
                "--output",
                "__GOVERNANCE_OUTPUT__",
            ),
        )
    )
    return tuple(commands)


def _run_command(
    root: Path,
    run_root: Path,
    command: GateCommand,
    environment: dict[str, str],
) -> dict[str, object]:
    stdout_path = run_root / f"{command.command_id}.stdout.log"
    stderr_path = run_root / f"{command.command_id}.stderr.log"
    argv = tuple(
        str(run_root / "semantic-governance") if item == "__GOVERNANCE_OUTPUT__" else item
        for item in command.argv
    )
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            argv,
            cwd=root,
            check=False,
            stdout=stdout,
            stderr=stderr,
            env=environment,
        )
    return {
        "argv": list(argv),
        "id": command.command_id,
        "return_code": completed.returncode,
        "stderr": {
            "path": stderr_path.relative_to(run_root).as_posix(),
            "sha256": _sha256(stderr_path),
        },
        "stdout": {
            "path": stdout_path.relative_to(run_root).as_posix(),
            "sha256": _sha256(stdout_path),
        },
    }


def _artifact_hashes(run_root: Path) -> list[dict[str, str]]:
    return [
        {"path": path.relative_to(run_root).as_posix(), "sha256": _sha256(path)}
        for path in sorted(run_root.rglob("*"))
        if path.is_file() and path.name != "receipt.json"
    ]


def run_gate(root: Path, base: str, include_smoke: bool) -> tuple[Path, dict[str, object]]:
    root = root.resolve(strict=True)
    expected = _snapshot(root)
    base_commit = _git(root, "rev-parse", f"{base}^{{commit}}")
    recorded_at = datetime.now(UTC).replace(microsecond=0)
    run_id = f"{expected['head'][:12]}-{recorded_at.strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    run_root = root / ".eow" / "local-gates" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ)
    environment.update({"CI": "1", "PYTHONHASHSEED": "0", "TZ": "UTC"})
    results: list[dict[str, object]] = []
    failure: str | None = None
    try:
        for command in gate_commands(root, base, include_smoke):
            result = _run_command(root, run_root, command, environment)
            results.append(result)
            _assert_stable(root, expected)
            if result["return_code"] != 0:
                failure = f"Command {command.command_id} failed."
                break
    except (GateError, OSError) as error:
        failure = str(error)
    passed = failure is None and len(results) == len(gate_commands(root, base, include_smoke))
    receipt: dict[str, object] = {
        "artifacts": _artifact_hashes(run_root),
        "base": {"commit": base_commit, "ref": base},
        "commands": results,
        "evidence_scope": "technical_gate_only_not_human_approval",
        "failure": failure,
        "include_smoke": include_smoke,
        "knowledge_config_fingerprint": content_fingerprint(root / "knowledge", root / "config"),
        "passed": passed,
        "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
        "repository": {**expected, "dirty": False},
        "schema_version": "1.0.0",
    }
    receipt_path = run_root / "receipt.json"
    _write_json(receipt_path, receipt)
    return receipt_path, receipt


def record_git_note(root: Path, receipt_path: Path, receipt: dict[str, object]) -> None:
    if receipt["passed"] is not True:
        raise GateError("A failed local gate cannot be recorded as a passed Git note.")
    root = root.resolve(strict=True)
    repository = receipt.get("repository")
    if not isinstance(repository, dict) or not isinstance(repository.get("head"), str):
        raise GateError("The local gate receipt has no valid repository HEAD.")
    payload = {
        "evidence_scope": "technical_gate_only_not_human_approval",
        "receipt": receipt_path.relative_to(root).as_posix(),
        "receipt_sha256": _sha256(receipt_path),
        "schema_version": "1.0.0",
    }
    _git(
        root,
        "notes",
        "--ref=eow-local-gates",
        "append",
        "-m",
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        repository["head"],
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        receipt_path, receipt = run_gate(
            arguments.repository,
            arguments.base,
            arguments.include_smoke,
        )
        if arguments.record_git_note and receipt["passed"] is True:
            record_git_note(arguments.repository, receipt_path, receipt)
    except GateError as error:
        print(str(error), file=sys.stderr)
        return 2
    output = {
        "git_note_ref": "refs/notes/eow-local-gates" if arguments.record_git_note else None,
        "passed": receipt["passed"],
        "receipt": str(receipt_path),
        "receipt_sha256": _sha256(receipt_path),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[1]


def _load_runner() -> ModuleType:
    path = ROOT / "scripts" / "run_local_gate.py"
    spec = importlib.util.spec_from_file_location("eow_run_local_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path, branch: str = "proposal/test-local-gate") -> Path:
    _git(tmp_path, "init", "--initial-branch", "main")
    _git(tmp_path, "config", "user.name", "Local Gate Test")
    _git(tmp_path, "config", "user.email", "local-gate@example.invalid")
    (tmp_path / ".gitignore").write_text(".eow/\n", encoding="utf-8")
    (tmp_path / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    if branch != "main":
        _git(tmp_path, "switch", "-c", branch)
    return tmp_path


def test_local_gate_refuses_main_and_dirty_proposals(tmp_path: Path) -> None:
    runner = _load_runner()
    repository = _repository(tmp_path, branch="main")

    with pytest.raises(runner.GateError, match=r"proposal/\*"):
        runner._snapshot(repository)

    _git(repository, "switch", "-c", "proposal/dirty")
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(runner.GateError, match="clean worktree"):
        runner._snapshot(repository)


def test_local_gate_receipt_is_bound_to_git_and_is_not_human_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_runner()
    repository = _repository(tmp_path)
    command = runner.GateCommand(
        "fixture_check",
        (sys.executable, "-c", "print('fixture passed')"),
    )
    monkeypatch.setattr(runner, "gate_commands", lambda *_: (command,))
    monkeypatch.setattr(runner, "content_fingerprint", lambda *_: "f" * 64)

    receipt_path, receipt = runner.run_gate(repository, "main", include_smoke=False)

    assert receipt["passed"] is True
    assert receipt["evidence_scope"] == "technical_gate_only_not_human_approval"
    assert receipt["repository"] == {
        "branch": "proposal/test-local-gate",
        "dirty": False,
        "head": _git(repository, "rev-parse", "HEAD"),
    }
    assert receipt["base"] == {
        "commit": _git(repository, "rev-parse", "main"),
        "ref": "main",
    }
    assert receipt["knowledge_config_fingerprint"] == "f" * 64
    assert receipt["commands"][0]["return_code"] == 0
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt


def test_local_gate_records_and_rejects_a_failed_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_runner()
    repository = _repository(tmp_path)
    command = runner.GateCommand(
        "invalid_rdf_fixture",
        (sys.executable, "-c", "raise SystemExit(7)"),
    )
    monkeypatch.setattr(runner, "gate_commands", lambda *_: (command,))
    monkeypatch.setattr(runner, "content_fingerprint", lambda *_: "a" * 64)

    receipt_path, receipt = runner.run_gate(repository, "main", include_smoke=False)

    assert receipt["passed"] is False
    assert receipt["failure"] == "Command invalid_rdf_fixture failed."
    assert receipt["commands"][0]["return_code"] == 7
    assert receipt_path.is_file()


def test_passed_gate_can_be_recorded_as_a_technical_git_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_runner()
    repository = _repository(tmp_path)
    receipt_path = repository / ".eow" / "local-gates" / "fixture" / "receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text('{"passed":true}\n', encoding="utf-8")
    head = _git(repository, "rev-parse", "HEAD")
    receipt = {"passed": True, "repository": {"head": head}}

    runner.record_git_note(repository, receipt_path, receipt)

    note = json.loads(_git(repository, "notes", "--ref=eow-local-gates", "show", head))
    assert note["evidence_scope"] == "technical_gate_only_not_human_approval"
    assert note["receipt"] == ".eow/local-gates/fixture/receipt.json"
    assert note["receipt_sha256"] == runner._sha256(receipt_path)
    assert _git(repository, "status", "--porcelain") == ""

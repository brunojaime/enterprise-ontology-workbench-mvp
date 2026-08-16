from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from ontology_cli.cli import main
from ontology_core import AgentContractService

ROOT = Path(__file__).parents[3]
APPLICATION = "https://knowledge.example.com/ontology/software#Application"


def _run_git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    for relative in ("knowledge", "config", "agent_contract"):
        shutil.copytree(ROOT / relative, root / relative)
    AgentContractService(root).sync()
    _run_git(root, "init", "--initial-branch=main")
    _run_git(root, "config", "user.name", "CLI Test")
    _run_git(root, "config", "user.email", "cli@example.test")
    _run_git(root, "add", ".")
    _run_git(root, "commit", "-m", "base")
    _run_git(root, "switch", "-c", "proposal/cli")
    term = root / "knowledge/ontology/software/terms/Application.ttl"
    term.write_text(
        term.read_text(encoding="utf-8").replace('Aplicación"@es', 'Aplicación empresarial"@es'),
        encoding="utf-8",
    )
    return root


def _invoke(
    capsys: pytest.CaptureFixture[str], root: Path, arguments: list[str], json_mode: bool
) -> object:
    argv = ["--repository", str(root), *arguments]
    if json_mode:
        argv.append("--json")
    assert main(argv) == 0
    output = capsys.readouterr().out
    return json.loads(output) if json_mode else yaml.safe_load(output)


@pytest.mark.parametrize("json_mode", [False, True])
def test_every_section_20_read_command_supports_text_and_json(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    json_mode: bool,
) -> None:
    commands = (
        ["status"],
        ["modules"],
        ["search", "aplicación"],
        ["describe", APPLICATION],
        ["context", "--task", "revisar aplicación", "--term", "aplicación"],
        ["validate"],
        ["diff", "--base", "main"],
        ["impact", APPLICATION],
        ["query", "knowledge/competency_questions/queries/applications_exist.rq"],
    )

    payloads = [_invoke(capsys, repository, command, json_mode) for command in commands]

    assert all(isinstance(payload, dict) for payload in payloads)
    assert payloads[2]["search_id"].startswith("eow-search-v2:")
    assert payloads[4]["task"] == "revisar aplicación"
    assert payloads[5]["conforms"] is True
    assert len(payloads[6]["added_quads"]) + len(payloads[6]["removed_quads"]) > 0


@pytest.mark.parametrize("json_mode", [False, True])
def test_agent_sync_repairs_generated_files_in_both_formats(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    json_mode: bool,
) -> None:
    generated = repository / "CLAUDE.md"
    generated.write_text("stale\n", encoding="utf-8")

    payload = _invoke(capsys, repository, ["agent_sync"], json_mode)

    assert payload["synchronized"] is True
    assert AgentContractService(repository).status().synchronized


def test_query_rejects_symlinks_and_update_queries(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_root = repository / "knowledge/competency_questions/queries"
    symlink = query_root / "linked.rq"
    symlink.symlink_to(query_root / "applications_exist.rq")

    assert main(["--repository", str(repository), "query", str(symlink), "--json"]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "query.unsafe_path"

    update = query_root / "unsafe.rq"
    update.write_text("DELETE WHERE { ?s ?p ?o }\n", encoding="utf-8")
    assert main(["--repository", str(repository), "query", str(update), "--json"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)

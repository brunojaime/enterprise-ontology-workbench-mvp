from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from ontology_core import FilesystemRdfStore, GitWorkspaceError, PullRequestGovernanceService
from rdflib import Dataset, Literal, URIRef

REPOSITORY_ROOT = Path(__file__).parents[3]
APPLICATION = "https://knowledge.example.com/ontology/software#Application"


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(("git", *arguments), cwd=repository, check=True, capture_output=True)


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copytree(REPOSITORY_ROOT / "knowledge", repository / "knowledge")
    shutil.copytree(REPOSITORY_ROOT / "config", repository / "config")
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "CI Fixture")
    _git(repository, "config", "user.email", "ci@example.invalid")
    _git(repository, "add", "knowledge", "config")
    _git(repository, "commit", "--quiet", "-m", "baseline")
    return repository


def _initial_import_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "initial-import"
    repository.mkdir()
    (repository / "README.md").write_text("# Empty base before EOW\n", encoding="utf-8")
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "CI Fixture")
    _git(repository, "config", "user.email", "ci@example.invalid")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "--quiet", "-m", "base without knowledge")
    shutil.copytree(REPOSITORY_ROOT / "knowledge", repository / "knowledge")
    shutil.copytree(REPOSITORY_ROOT / "config", repository / "config")
    return repository


def _service(repository: Path) -> PullRequestGovernanceService:
    store = FilesystemRdfStore(
        repository / "knowledge",
        repository / "config/namespace.yaml",
    )
    return PullRequestGovernanceService(repository, store)


def test_semantically_empty_rdf_reformat_is_reported_as_warning(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    application = repository / "knowledge/ontology/software/terms/Application.ttl"
    application.write_text(application.read_text() + "\n# cambio exclusivamente textual\n")

    report = _service(repository).build(
        base_ref="main",
        head_ref="HEAD",
        changed_paths=("knowledge/ontology/software/terms/Application.ttl",),
    )

    assert report.passed
    assert report.semantic_empty
    assert report.affected_resources == ()
    assert report.warnings == (
        "Hay archivos RDF modificados, pero el Dataset no cambió semánticamente.",
    )


def test_semantic_change_lists_module_and_resource_deterministically(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    application = repository / "knowledge/ontology/software/terms/Application.ttl"
    application.write_text(
        application.read_text().replace(
            '    skos:prefLabel "Aplicación"@es ;',
            '    skos:prefLabel "Aplicación"@es ;\n    skos:altLabel "Sistema"@es ;',
        )
    )

    report = _service(repository).build(
        base_ref="main",
        head_ref="proposal/test",
        changed_paths=("knowledge/ontology/software/terms/Application.ttl",),
    )

    assert report.passed
    assert not report.semantic_empty
    assert report.affected_modules == ("https://knowledge.example.com/id/module/software",)
    assert report.affected_resources == (APPLICATION,)
    assert APPLICATION in report.to_markdown()
    assert report.to_json() == report.to_json()


def test_deprecated_usage_report_covers_predicate_and_object_references() -> None:
    store = FilesystemRdfStore(
        REPOSITORY_ROOT / "knowledge",
        REPOSITORY_ROOT / "config/namespace.yaml",
    )
    service = PullRequestGovernanceService(REPOSITORY_ROOT, store)
    dataset = Dataset()
    graph = dataset.graph(URIRef("https://knowledge.example.com/graph/test"))
    status = URIRef("https://knowledge.example.com/ontology/core#status")
    term = URIRef("https://knowledge.example.com/ontology/test#old_property")
    subject = URIRef("https://knowledge.example.com/id/test/subject")
    graph.add((term, status, Literal("deprecated")))
    graph.add((subject, term, Literal("predicate use")))
    graph.add((subject, URIRef("https://example.com/rel"), term))

    usages = service.find_deprecated_usages(dataset)

    assert len(usages) == 2
    assert {usage.term.value for usage in usages} == {str(term)}
    assert [usage.to_dict() for usage in usages] == [usage.to_dict() for usage in usages]


def test_script_writes_downloadable_artifacts_and_github_warning(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    application = repository / "knowledge/ontology/software/terms/Application.ttl"
    application.write_text(application.read_text() + "\n# reformat\n")
    output = tmp_path / "artifacts"

    result = subprocess.run(
        (
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/generate_pr_report.py"),
            "--repository",
            str(repository),
            "--base",
            "main",
            "--head",
            "fixture-head",
            "--output",
            str(output),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "::warning title=Gobernanza semántica::" in result.stdout
    assert {path.name for path in output.iterdir()} == {
        "deprecated-usages.json",
        "governance-report.json",
        "pr-summary.md",
        "semantic-diff.json",
        "validation.json",
    }
    payload = json.loads((output / "governance-report.json").read_text())
    assert payload["semantic_empty"] is True
    assert payload["rdf_changed_paths"] == ["knowledge/ontology/software/terms/Application.ttl"]


def test_parser_failure_still_produces_report_and_fails_check(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    application = repository / "knowledge/ontology/software/terms/Application.ttl"
    application.write_text("this is not Turtle")
    output = tmp_path / "artifacts"

    result = subprocess.run(
        (
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/generate_pr_report.py"),
            "--repository",
            str(repository),
            "--base",
            "main",
            "--output",
            str(output),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    validation = json.loads((output / "validation.json").read_text())
    semantic_diff = json.loads((output / "semantic-diff.json").read_text())
    assert validation["conforms"] is False
    assert semantic_diff == {"status": "not_executable"}


def test_initial_import_from_valid_empty_base_writes_all_artifacts_deterministically(
    tmp_path: Path,
) -> None:
    repository = _initial_import_repository(tmp_path)
    outputs = (tmp_path / "artifacts-one", tmp_path / "artifacts-two")

    for output in outputs:
        result = subprocess.run(
            (
                sys.executable,
                str(REPOSITORY_ROOT / "scripts/generate_pr_report.py"),
                "--repository",
                str(repository),
                "--base",
                "main",
                "--head",
                "initial-import-fixture",
                "--output",
                str(output),
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    expected_artifacts = {
        "deprecated-usages.json",
        "governance-report.json",
        "pr-summary.md",
        "semantic-diff.json",
        "validation.json",
    }
    assert {path.name for path in outputs[0].iterdir()} == expected_artifacts
    assert {path.name for path in outputs[1].iterdir()} == expected_artifacts
    assert {path.name: path.read_bytes() for path in outputs[0].iterdir()} == {
        path.name: path.read_bytes() for path in outputs[1].iterdir()
    }

    payload = json.loads((outputs[0] / "governance-report.json").read_text())
    summary = (outputs[0] / "pr-summary.md").read_text()
    assert payload["passed"] is True
    assert payload["initial_import"] is True
    assert payload["semantic_diff_status"] == "completed"
    assert payload["semantic_empty"] is False
    assert payload["affected_modules"] == [
        "https://knowledge.example.com/id/module/competency",
        "https://knowledge.example.com/id/module/core",
        "https://knowledge.example.com/id/module/knowledge_governance",
        "https://knowledge.example.com/id/module/organization",
        "https://knowledge.example.com/id/module/software",
    ]
    assert payload["rdf_changed_paths"]
    assert all(path.startswith("knowledge/") for path in payload["rdf_changed_paths"])
    assert "Dataset base: **vacío (importación inicial)**" in summary


def test_missing_revision_is_not_treated_as_an_initial_import(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with pytest.raises(GitWorkspaceError, match="does not exist"):
        _service(repository).build(
            base_ref="missing-base",
            head_ref="HEAD",
            changed_paths=(),
        )


def test_invalid_rdf_on_initial_import_still_writes_five_failure_artifacts(tmp_path: Path) -> None:
    repository = _initial_import_repository(tmp_path)
    (repository / "knowledge/ontology/software/terms/Application.ttl").write_text(
        "this is not Turtle",
        encoding="utf-8",
    )
    output = tmp_path / "invalid-initial-import"

    result = subprocess.run(
        (
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/generate_pr_report.py"),
            "--repository",
            str(repository),
            "--base",
            "main",
            "--head",
            "invalid-initial-import-fixture",
            "--output",
            str(output),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert {path.name for path in output.iterdir()} == {
        "deprecated-usages.json",
        "governance-report.json",
        "pr-summary.md",
        "semantic-diff.json",
        "validation.json",
    }
    payload = json.loads((output / "governance-report.json").read_text())
    assert payload["initial_import"] is True
    assert payload["passed"] is False
    assert payload["semantic_diff_status"] == "not_executable"
    assert json.loads((output / "semantic-diff.json").read_text()) == {"status": "not_executable"}
    assert json.loads((output / "validation.json").read_text())["conforms"] is False


def test_base_with_knowledge_but_without_config_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "incomplete-base"
    repository.mkdir()
    (repository / "knowledge").mkdir()
    (repository / "knowledge/manifest.ttl").write_text("# incomplete base\n", encoding="utf-8")
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "CI Fixture")
    _git(repository, "config", "user.email", "ci@example.invalid")
    _git(repository, "add", "knowledge")
    _git(repository, "commit", "--quiet", "-m", "incomplete RDF base")
    shutil.rmtree(repository / "knowledge")
    shutil.copytree(REPOSITORY_ROOT / "knowledge", repository / "knowledge")
    shutil.copytree(REPOSITORY_ROOT / "config", repository / "config")

    with pytest.raises(GitWorkspaceError, match="no config"):
        _service(repository).build(
            base_ref="main",
            head_ref="HEAD",
            changed_paths=(),
        )

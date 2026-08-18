from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from ontology_core.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    ValidationSource,
)
from ontology_core.workspace import GitWorkspaceError, GitWorkspaceService


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Test Author")
    git(root, "config", "user.email", "test@example.com")
    (root / "knowledge").mkdir()
    (root / "knowledge" / "manifest.ttl").write_text("# fixture\n", encoding="utf-8")
    git(root, "add", "knowledge/manifest.ttl")
    git(root, "commit", "-m", "chore: seed fixture")
    return root


def test_workspace_reads_branch_status_base_and_proposal_commits(repository: Path) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    initial = service.status()
    assert initial.branch == "main"
    assert initial.head == initial.base_commit
    assert initial.editable is False
    assert initial.dirty is False

    proposal = service.switch_proposal("proposal/add-pump", create=True)
    assert proposal.branch == "proposal/add-pump"
    assert proposal.editable is True
    (repository / "knowledge" / "manifest.ttl").write_text("# changed\n", encoding="utf-8")
    dirty = service.status()
    assert dirty.dirty is True
    assert dirty.changed_paths == ("knowledge/manifest.ttl",)
    git(repository, "add", "knowledge/manifest.ttl")
    git(repository, "commit", "-m", "ontology(core): change fixture")
    committed = service.status()
    assert [item.subject for item in committed.proposal_commits] == [
        "ontology(core): change fixture"
    ]


def test_workspace_protects_main_and_validates_proposal_names(repository: Path) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    with pytest.raises(GitWorkspaceError, match="prohibited") as protected:
        service.require_proposal_branch()
    assert protected.value.code == "git.protected_branch"

    with pytest.raises(GitWorkspaceError) as invalid:
        service.switch_proposal("feature/Unsafe Branch", create=True)
    assert invalid.value.code == "git.invalid_proposal_branch"


@pytest.mark.parametrize("branch", ["feature/unsafe", "hotfix/unsafe"])
def test_only_proposal_namespace_is_editable(repository: Path, branch: str) -> None:
    git(repository, "switch", "--create", branch)
    service = GitWorkspaceService(repository, repository / "knowledge")
    assert service.status().editable is False
    with pytest.raises(GitWorkspaceError) as rejected:
        service.require_proposal_branch()
    assert rejected.value.code == "git.invalid_proposal_branch"


def test_detached_head_is_not_editable(repository: Path) -> None:
    git(repository, "switch", "--detach")
    service = GitWorkspaceService(repository, repository / "knowledge")
    assert service.status().editable is False
    with pytest.raises(GitWorkspaceError) as rejected:
        service.require_proposal_branch()
    assert rejected.value.code == "git.detached_head"


def test_base_file_reads_published_content_not_proposal_edits(repository: Path) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    service.switch_proposal("proposal/base-snapshot", create=True)
    path = repository / "knowledge/manifest.ttl"
    path.write_text("# proposal\n", encoding="utf-8")
    assert service.base_file(path) == b"# fixture\n"
    assert service.base_file(repository / "knowledge/missing.ttl") is None


def test_workspace_refuses_branch_switch_with_dirty_changes(repository: Path) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    (repository / "knowledge" / "manifest.ttl").write_text("# dirty\n", encoding="utf-8")
    with pytest.raises(GitWorkspaceError) as captured:
        service.switch_proposal("proposal/no-loss", create=True)
    assert captured.value.code == "git.dirty_worktree"
    assert git(repository, "branch", "--show-current") == "main"


def test_workspace_rejects_a_non_repository(tmp_path: Path) -> None:
    root = tmp_path / "not-git"
    (root / "knowledge").mkdir(parents=True)
    with pytest.raises(GitWorkspaceError) as captured:
        GitWorkspaceService(root, root / "knowledge")
    assert captured.value.code == "git.not_repository"


def test_structured_commit_requires_validation_or_explicit_exception(repository: Path) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    service.switch_proposal("proposal/commit", create=True)
    (repository / "knowledge/manifest.ttl").write_text("# proposal\n", encoding="utf-8")
    invalid = ValidationReport.from_issues(
        [
            ValidationIssue(
                source=ValidationSource.LINT,
                rule_id="fixture.invalid",
                severity=ValidationSeverity.ERROR,
                message="fixture",
            )
        ]
    )
    with pytest.raises(GitWorkspaceError) as blocked:
        service.commit(module="core", summary="update manifest", validation=invalid)
    assert blocked.value.code == "git.validation_failed"

    committed = service.commit(
        module="core",
        summary="update manifest",
        validation=invalid,
        exception_reason="Excepción aprobada para verificar el contrato de prueba.",
    )
    assert committed.subject == "ontology(core): update manifest"
    assert committed.validation_conforms is False
    assert git(repository, "show", "--format=%B", "--no-patch").splitlines()[0] == committed.subject


def test_commit_rejects_changes_outside_knowledge(repository: Path) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    service.switch_proposal("proposal/scoped", create=True)
    (repository / "README.md").write_text("outside\n", encoding="utf-8")
    with pytest.raises(GitWorkspaceError) as blocked:
        service.commit(
            module="core",
            summary="unsafe scope",
            validation=ValidationReport.from_issues([]),
        )
    assert blocked.value.code == "git.out_of_scope_changes"


def test_status_and_commit_preserve_both_sides_of_an_internal_rename(
    repository: Path,
) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    service.switch_proposal("proposal/rename", create=True)
    git(repository, "mv", "knowledge/manifest.ttl", "knowledge/renamed.ttl")

    assert service.status().changed_paths == (
        "knowledge/manifest.ttl",
        "knowledge/renamed.ttl",
    )
    result = service.commit(
        module="core",
        summary="rename manifest fixture",
        validation=ValidationReport.from_issues([]),
    )
    assert result.paths == ("knowledge/manifest.ttl", "knowledge/renamed.ttl")
    assert git(repository, "ls-tree", "--name-only", "HEAD", "knowledge/renamed.ttl")


def test_rename_from_knowledge_to_outside_is_rejected(repository: Path) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    service.switch_proposal("proposal/escape", create=True)
    git(repository, "mv", "knowledge/manifest.ttl", "escaped.ttl")

    assert service.status().changed_paths == ("escaped.ttl", "knowledge/manifest.ttl")
    with pytest.raises(GitWorkspaceError) as blocked:
        service.commit(
            module="core",
            summary="escape manifest fixture",
            validation=ValidationReport.from_issues([]),
        )
    assert blocked.value.code == "git.out_of_scope_changes"


def test_copy_porcelain_keeps_source_and_destination() -> None:
    assert GitWorkspaceService._parse_status_paths(
        "C  knowledge/copied.ttl\x00knowledge/original.ttl\x00"
    ) == ("knowledge/copied.ttl", "knowledge/original.ttl")


def test_commit_aborts_if_content_changes_after_validation(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    service.switch_proposal("proposal/concurrent", create=True)
    path = repository / "knowledge/manifest.ttl"
    path.write_text("# validated\n", encoding="utf-8")
    expected = service.content_fingerprint()
    original_run = service._run

    def mutate_after_stage(*arguments: str, check: bool = True) -> str:
        result = original_run(*arguments, check=check)
        if arguments[0] == "add":
            path.write_text("# changed concurrently\n", encoding="utf-8")
        return result

    monkeypatch.setattr(service, "_run", mutate_after_stage)
    with pytest.raises(GitWorkspaceError) as blocked:
        service.commit(
            module="core",
            summary="concurrent manifest edit",
            validation=ValidationReport.from_issues([]),
            expected_head=git(repository, "rev-parse", "HEAD"),
            expected_fingerprint=expected,
        )
    assert blocked.value.code == "git.concurrent_change"
    assert git(repository, "log", "-1", "--format=%s") == "chore: seed fixture"


def test_pull_request_is_optional_without_github_configuration(repository: Path) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    service.switch_proposal("proposal/no-github", create=True)
    result = service.create_pull_request(title="Ontology proposal", body="Review evidence")
    assert result.status == "not_configured"
    assert result.url is None


def test_pull_request_uses_github_only_when_cli_and_credentials_are_configured(
    repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GitWorkspaceService(repository, repository / "knowledge")
    service.switch_proposal("proposal/github", create=True)
    git(repository, "remote", "add", "origin", "https://github.com/example/workbench.git")
    binary_root = tmp_path / "bin"
    binary_root.mkdir()
    gh = binary_root / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = auth ]; then exit 0; fi\n'
        'if [ "$1" = pr ]; then\n'
        "  printf '%s\\n' 'https://github.com/example/workbench/pull/7'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binary_root}:{os.environ['PATH']}")
    result = service.create_pull_request(
        title="Ontology proposal",
        body="Evidence and validation are attached.",
    )
    assert result.status == "created"
    assert result.url == "https://github.com/example/workbench/pull/7"

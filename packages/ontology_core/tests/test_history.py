from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ontology_core import GitHistoryService


def git(repository: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed.stdout.strip()


def test_git_history_reads_real_commits_without_mutating_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source = repository / "knowledge/ontology/example/terms/Example.ttl"
    source.parent.mkdir(parents=True)
    source.write_text("<https://example.test/Example> a <https://example.test/Class> .\n")
    git(repository, "init", "--quiet")
    git(repository, "config", "user.name", "Ontology Author")
    git(repository, "config", "user.email", "ontology@example.test")
    git(repository, "add", source.relative_to(repository).as_posix())
    commit_env = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-08-10T12:34:56-03:00",
        "GIT_COMMITTER_DATE": "2026-08-10T12:34:56-03:00",
    }
    git(repository, "commit", "--quiet", "-m", "Add canonical example", env=commit_env)
    revision = git(repository, "rev-parse", "HEAD")
    status_before = git(repository, "status", "--porcelain")

    entries = GitHistoryService(repository, repository / "knowledge").read(
        (source,), revision=revision
    )

    assert [entry.to_dict() for entry in entries] == [
        {
            "commit": revision,
            "author": "Ontology Author",
            "date": "2026-08-10T12:34:56-03:00",
            "subject": "Add canonical example",
            "path": "knowledge/ontology/example/terms/Example.ttl",
        }
    ]
    assert git(repository, "status", "--porcelain") == status_before


def test_git_history_is_empty_for_untracked_or_outside_sources(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    knowledge = repository / "knowledge"
    untracked = knowledge / "untracked.ttl"
    outside = tmp_path / "outside.ttl"
    knowledge.mkdir(parents=True)
    untracked.write_text("untracked\n")
    outside.write_text("outside\n")
    git(repository, "init", "--quiet")

    history = GitHistoryService(repository, knowledge)

    assert history.read((untracked, outside)) == ()


def test_git_history_is_fixed_to_revision_after_source_is_deleted_or_renamed(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "knowledge/ontology/example/terms/Example.ttl"
    renamed = source.with_name("Renamed.ttl")
    source.parent.mkdir(parents=True)
    source.write_text("<https://example.test/Example> a <https://example.test/Class> .\n")
    git(repository, "init", "--quiet")
    git(repository, "config", "user.name", "Snapshot Author")
    git(repository, "config", "user.email", "snapshot@example.test")
    git(repository, "add", source.relative_to(repository).as_posix())
    git(repository, "commit", "--quiet", "-m", "Publish example")
    revision = git(repository, "rev-parse", "HEAD")
    history = GitHistoryService(repository, repository / "knowledge")

    before = history.read((source,), revision=revision)
    source.rename(renamed)
    after_rename = history.read((source,), revision=revision)
    renamed.unlink()
    after_delete = history.read((source,), revision=revision)

    assert before == after_rename == after_delete
    assert len(before) == 1
    assert before[0].path == "knowledge/ontology/example/terms/Example.ttl"

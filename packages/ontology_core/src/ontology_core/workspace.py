"""Safe Git workspace operations for ontology proposals."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ontology_core.validation import ValidationReport

PROPOSAL_BRANCH = re.compile(r"^proposal/[a-z0-9](?:[a-z0-9._-]{0,62})$")


def content_fingerprint(*roots: Path) -> str:
    """Hash path, kind and bytes without following symlinks outside a root."""

    digest = sha256()
    for root in sorted((root.resolve(strict=False) for root in roots), key=str):
        digest.update(b"root\0")
        digest.update(root.name.encode())
        digest.update(b"\0")
        if not root.exists():
            digest.update(b"missing\0")
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix().encode()
            digest.update(relative)
            digest.update(b"\0")
            if path.is_symlink():
                digest.update(b"symlink\0")
                digest.update(path.readlink().as_posix().encode())
            elif path.is_file():
                digest.update(b"file\0")
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
            elif path.is_dir():
                digest.update(b"directory\0")
            else:
                digest.update(b"other\0")
            digest.update(b"\0")
    return digest.hexdigest()


class GitWorkspaceError(RuntimeError):
    """A controlled Git operation could not be completed safely."""

    def __init__(self, code: str, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class GitCommit:
    commit: str
    author: str
    date: str
    subject: str

    def to_dict(self) -> dict[str, str]:
        return {
            "commit": self.commit,
            "author": self.author,
            "date": self.date,
            "subject": self.subject,
        }


@dataclass(frozen=True)
class GitWorkspaceStatus:
    repository_root: str
    branch: str | None
    head: str | None
    base_branch: str
    base_commit: str | None
    dirty: bool
    changed_paths: tuple[str, ...]
    proposal_commits: tuple[GitCommit, ...]
    proposal_branches: tuple[str, ...]
    editable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "repository_root": self.repository_root,
            "branch": self.branch,
            "head": self.head,
            "base_branch": self.base_branch,
            "base_commit": self.base_commit,
            "dirty": self.dirty,
            "changed_paths": list(self.changed_paths),
            "proposal_commits": [commit.to_dict() for commit in self.proposal_commits],
            "proposal_branches": list(self.proposal_branches),
            "editable": self.editable,
        }


@dataclass(frozen=True)
class GitCommitResult:
    commit: str
    subject: str
    paths: tuple[str, ...]
    validation_conforms: bool
    exception_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "commit": self.commit,
            "subject": self.subject,
            "paths": list(self.paths),
            "validation_conforms": self.validation_conforms,
            "exception_reason": self.exception_reason,
        }


@dataclass(frozen=True)
class PullRequestResult:
    status: str
    url: str | None
    reason: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {"status": self.status, "url": self.url, "reason": self.reason}


class GitWorkspaceService:
    """Read and mutate Git through a small, argument-safe proposal workflow."""

    def __init__(
        self,
        repository_root: Path,
        knowledge_root: Path,
        *,
        base_branch: str = "main",
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.repository_root = repository_root.resolve()
        self.knowledge_root = knowledge_root.resolve()
        if not self.knowledge_root.is_relative_to(self.repository_root):
            raise ValueError("knowledge root must be inside repository root")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", base_branch):
            raise ValueError("base_branch is invalid")
        self.base_branch = base_branch
        self.timeout_seconds = timeout_seconds
        discovered = self._run("rev-parse", "--show-toplevel", check=False).strip()
        if not discovered or Path(discovered).resolve() != self.repository_root:
            raise GitWorkspaceError(
                "git.not_repository",
                "The configured repository root is not a Git working tree.",
            )

    def status(self) -> GitWorkspaceStatus:
        branch = self._optional("branch", "--show-current") or None
        head = self._optional("rev-parse", "HEAD") or None
        base_commit = self._optional("rev-parse", self.base_branch) or None
        porcelain = self._run("status", "--porcelain=v1", "-z")
        changed_paths = self._parse_status_paths(porcelain)
        commits: tuple[GitCommit, ...] = ()
        if (
            head is not None
            and base_commit is not None
            and branch
            and PROPOSAL_BRANCH.fullmatch(branch)
        ):
            commits = self._proposal_commits()
        proposal_branches = tuple(
            sorted(
                branch
                for branch in self._run(
                    "for-each-ref",
                    "--format=%(refname:short)",
                    "refs/heads/proposal/",
                ).splitlines()
                if PROPOSAL_BRANCH.fullmatch(branch)
            )
        )
        return GitWorkspaceStatus(
            repository_root=str(self.repository_root),
            branch=branch,
            head=head,
            base_branch=self.base_branch,
            base_commit=base_commit,
            dirty=bool(changed_paths),
            changed_paths=changed_paths,
            proposal_commits=commits,
            proposal_branches=proposal_branches,
            editable=bool(branch and PROPOSAL_BRANCH.fullmatch(branch)),
        )

    def require_proposal_branch(self) -> GitWorkspaceStatus:
        status = self.status()
        if status.branch is None:
            raise GitWorkspaceError(
                "git.detached_head",
                "Editing requires a named proposal branch.",
            )
        if status.branch == self.base_branch:
            raise GitWorkspaceError(
                "git.protected_branch",
                f"Editing is prohibited on protected branch {self.base_branch}.",
                details={"branch": status.branch},
            )
        if not PROPOSAL_BRANCH.fullmatch(status.branch):
            raise GitWorkspaceError(
                "git.invalid_proposal_branch",
                "Editing requires a branch named proposal/<lowercase-name>.",
                details={"branch": status.branch},
            )
        return status

    def content_fingerprint(self) -> str:
        config_root = self.repository_root / "config"
        return content_fingerprint(self.knowledge_root, config_root)

    def base_file(self, path: Path) -> bytes | None:
        """Read one repository-confined file from the published base revision."""

        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(self.repository_root):
            raise GitWorkspaceError("git.unsafe_path", "Git paths must stay in the repository.")
        relative = resolved.relative_to(self.repository_root).as_posix()
        base_commit = self.status().base_commit
        if base_commit is None:
            raise GitWorkspaceError("git.base_unavailable", "The published base is unavailable.")
        try:
            completed = subprocess.run(
                ("git", "show", f"{base_commit}:{relative}"),
                cwd=self.repository_root,
                check=False,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise GitWorkspaceError("git.execution_failed", str(error)) from error
        if completed.returncode != 0:
            return None
        return completed.stdout

    def switch_proposal(self, branch: str, *, create: bool = False) -> GitWorkspaceStatus:
        if not PROPOSAL_BRANCH.fullmatch(branch):
            raise GitWorkspaceError(
                "git.invalid_proposal_branch",
                "Proposal branches must use proposal/<lowercase-name>.",
                details={"branch": branch},
            )
        current = self.status()
        if current.dirty:
            raise GitWorkspaceError(
                "git.dirty_worktree",
                "Switching branches is blocked while the working tree has changes.",
            )
        exists = bool(self._optional("show-ref", "--verify", f"refs/heads/{branch}"))
        if create:
            if exists:
                raise GitWorkspaceError(
                    "git.branch_exists",
                    "The proposal branch already exists.",
                    details={"branch": branch},
                )
            self._run("switch", "--create", branch, self.base_branch)
        else:
            if not exists:
                raise GitWorkspaceError(
                    "git.branch_not_found",
                    "The proposal branch does not exist.",
                    details={"branch": branch},
                )
            self._run("switch", branch)
        return self.status()

    def commit(
        self,
        *,
        module: str,
        summary: str,
        validation: ValidationReport,
        exception_reason: str | None = None,
        expected_head: str | None = None,
        expected_fingerprint: str | None = None,
    ) -> GitCommitResult:
        status = self.require_proposal_branch()
        if expected_head is not None and status.head != expected_head:
            raise GitWorkspaceError(
                "git.concurrent_change",
                "HEAD changed after the proposal snapshot was loaded.",
            )
        if expected_fingerprint is not None and self.content_fingerprint() != expected_fingerprint:
            raise GitWorkspaceError(
                "git.concurrent_change",
                "Repository content changed after validation; reload and review again.",
            )
        safe_module = module.strip().lower()
        clean_summary = " ".join(summary.split())
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", safe_module):
            raise GitWorkspaceError("git.invalid_commit_module", "Commit module is invalid.")
        if not 5 <= len(clean_summary) <= 72 or "\n" in clean_summary:
            raise GitWorkspaceError(
                "git.invalid_commit_summary",
                "Commit summary must contain 5 to 72 characters on one line.",
            )
        reason = exception_reason.strip() if exception_reason else None
        if not validation.conforms and not reason:
            raise GitWorkspaceError(
                "git.validation_failed",
                "A non-conforming proposal requires an explicit exception reason.",
            )
        if reason is not None and len(reason) < 12:
            raise GitWorkspaceError(
                "git.invalid_exception",
                "The validation exception reason must be explicit.",
            )
        knowledge_prefix = self.knowledge_root.relative_to(self.repository_root).as_posix() + "/"
        paths = tuple(path for path in status.changed_paths if path.startswith(knowledge_prefix))
        outside = tuple(
            path for path in status.changed_paths if not path.startswith(knowledge_prefix)
        )
        if outside:
            raise GitWorkspaceError(
                "git.out_of_scope_changes",
                "Commit is blocked while changes exist outside knowledge/.",
                details={"paths": ",".join(outside)},
            )
        if not paths:
            raise GitWorkspaceError("git.nothing_to_commit", "No knowledge changes are pending.")
        knowledge_path = self.knowledge_root.relative_to(self.repository_root).as_posix()
        subject = f"ontology({safe_module}): {clean_summary}"
        body = [
            f"Validation-Conforms: {'yes' if validation.conforms else 'no'}",
            f"Validation-Issues: {len(validation.issues)}",
        ]
        if reason:
            body.append(f"Validation-Exception: {reason}")
        try:
            self._run("add", "--all", "--", knowledge_path)
            if (
                expected_fingerprint is not None
                and self.content_fingerprint() != expected_fingerprint
            ):
                raise GitWorkspaceError(
                    "git.concurrent_change",
                    "Repository content changed while the validated tree was staged.",
                )
            staged_tree = self._run("write-tree").strip()
            if not staged_tree:
                raise GitWorkspaceError(
                    "git.stage_failed", "Git did not produce a staged proposal tree."
                )
            message = f"{subject}\n\n{'\n'.join(body)}\n"
            parent = status.head
            if parent is None:
                raise GitWorkspaceError("git.head_unavailable", "Proposal HEAD is unavailable.")
            commit = self._run_with_input(
                ("commit-tree", staged_tree, "-p", parent), message
            ).strip()
            if self._run("write-tree").strip() != staged_tree:
                raise GitWorkspaceError(
                    "git.concurrent_change",
                    "The Git index changed while the validated commit was prepared.",
                )
            branch_ref = f"refs/heads/{status.branch}"
            self._run("update-ref", branch_ref, commit, parent)
        except GitWorkspaceError:
            self._run("reset", "--quiet", "HEAD", "--", knowledge_path, check=False)
            raise
        return GitCommitResult(commit, subject, paths, validation.conforms, reason)

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        draft: bool = True,
    ) -> PullRequestResult:
        status = self.require_proposal_branch()
        remote = self._optional("remote", "get-url", "origin")
        if "github.com" not in remote:
            return PullRequestResult("not_configured", None, "origin is not a GitHub remote")
        if shutil.which("gh") is None:
            return PullRequestResult("not_configured", None, "GitHub CLI is not available")
        auth = subprocess.run(
            ("gh", "auth", "status", "--hostname", "github.com"),
            cwd=self.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if auth.returncode != 0:
            return PullRequestResult("not_configured", None, "GitHub credentials are unavailable")
        arguments = [
            "gh",
            "pr",
            "create",
            "--base",
            status.base_branch,
            "--head",
            status.branch or "",
            "--title",
            title.strip(),
            "--body",
            body.strip(),
        ]
        if draft:
            arguments.append("--draft")
        completed = subprocess.run(
            arguments,
            cwd=self.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise GitWorkspaceError(
                "git.pull_request_failed",
                "GitHub could not create the pull request.",
                details={"detail": completed.stderr.strip()},
            )
        return PullRequestResult("created", completed.stdout.strip(), None)

    def _proposal_commits(self) -> tuple[GitCommit, ...]:
        output = self._run(
            "log",
            "--format=%H%x00%an%x00%aI%x00%s",
            "-z",
            f"{self.base_branch}..HEAD",
        )
        fields = output.split("\x00")
        commits: list[GitCommit] = []
        for index in range(0, len(fields) - 3, 4):
            if not fields[index]:
                continue
            commits.append(GitCommit(*fields[index : index + 4]))
        return tuple(commits)

    @staticmethod
    def _parse_status_paths(output: str) -> tuple[str, ...]:
        records = output.split("\x00")
        paths: list[str] = []
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            code = record[:2]
            path = record[3:]
            paths.append(path)
            if ("R" in code or "C" in code) and index < len(records) and records[index]:
                paths.append(records[index])
                index += 1
        return tuple(sorted(set(paths)))

    def _run_with_input(self, arguments: tuple[str, ...], payload: str) -> str:
        try:
            completed = subprocess.run(
                ("git", *arguments),
                cwd=self.repository_root,
                check=False,
                capture_output=True,
                text=True,
                input=payload,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise GitWorkspaceError("git.execution_failed", str(error)) from error
        if completed.returncode != 0:
            raise GitWorkspaceError(
                "git.command_failed",
                "Git could not complete the controlled operation.",
                details={
                    "operation": arguments[0],
                    "detail": completed.stderr.strip() or completed.stdout.strip(),
                },
            )
        return completed.stdout

    def _optional(self, *arguments: str) -> str:
        return self._run(*arguments, check=False).strip()

    def _run(self, *arguments: str, check: bool = True) -> str:
        if shutil.which("git") is None:
            raise GitWorkspaceError("git.unavailable", "Git is not available.")
        try:
            completed = subprocess.run(
                ("git", *arguments),
                cwd=self.repository_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise GitWorkspaceError("git.execution_failed", str(error)) from error
        if check and completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise GitWorkspaceError(
                "git.command_failed",
                "Git could not complete the controlled operation.",
                details={"operation": arguments[0], "detail": detail},
            )
        return completed.stdout

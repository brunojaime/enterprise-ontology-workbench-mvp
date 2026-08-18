"""Snapshot-aware adapter from MCP operations to ontology_core services."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from ontology_core import (
    AgentContextService,
    AgentContractService,
    ContextBudget,
    ContextRequest,
    DeprecationDraft,
    FilesystemRdfStore,
    GitWorkspaceError,
    GitWorkspaceService,
    IndividualDraft,
    NeighborhoodLimits,
    ProposalReviewService,
    RelationDraft,
    SearchConfirmation,
    TermDraft,
    TermWriter,
    ValidationService,
    WriteResult,
    content_fingerprint,
)
from ontology_core.search_receipts import SearchReceiptAuthority

from ontology_mcp.audit import AuditWriteError, RepositoryFileLock, WriteAuditLog
from ontology_mcp.config import McpSettings
from ontology_mcp.models import (
    ContextInput,
    DeprecateInput,
    DescribeInput,
    DiffInput,
    RelationInput,
    SearchInput,
    TermInput,
)

T = TypeVar("T")


class McpRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Snapshot:
    marker: str
    store: FilesystemRdfStore
    context: AgentContextService
    writer: TermWriter


@dataclass(frozen=True)
class _FileState:
    content: bytes
    mode: int
    atime_ns: int
    mtime_ns: int


@dataclass(frozen=True)
class _PublishedFile:
    path: Path
    previous: _FileState | None
    current: _FileState
    created_directories: tuple[Path, ...]


class OntologyMcpRuntime:
    """Keep search receipts and every operation tied to one local RDF/Git snapshot."""

    def __init__(self, settings: McpSettings) -> None:
        self.settings = settings
        self.workspace = GitWorkspaceService(settings.repository_root, settings.knowledge_root)
        self.audit = WriteAuditLog(settings.repository_root, settings.audit_log)
        self._write_lock = RepositoryFileLock(
            settings.repository_root,
            settings.repository_root / ".eow/locks/mcp-write.lock",
        )
        self._receipts = SearchReceiptAuthority()
        self._lock = threading.RLock()
        self._protocol_audited: ContextVar[bool] = ContextVar(
            "ontology_mcp_protocol_audited",
            default=False,
        )
        self._snapshot = self._build_snapshot()

    def begin_protocol_write(self) -> Token[bool]:
        return self._protocol_audited.set(False)

    def end_protocol_write(self, token: Token[bool]) -> None:
        self._protocol_audited.reset(token)

    @property
    def protocol_write_audited(self) -> bool:
        return self._protocol_audited.get()

    def audit_protocol_rejection(
        self,
        *,
        agent: str,
        tool: str,
        code: str,
    ) -> None:
        self.audit.record(
            agent=agent,
            tool=tool,
            files=(),
            result="rejected",
            code=code,
            invocation_id=uuid4().hex,
        )
        self._protocol_audited.set(True)

    def list_modules(self) -> dict[str, object]:
        with self._lock:
            snapshot = self._refresh()
            return {
                "items": [
                    item.to_dict()
                    for item in snapshot.context.query.modules(snapshot.store.discover_modules())
                ],
                "snapshot": snapshot.marker,
            }

    def search(self, request: SearchInput) -> dict[str, object]:
        with self._lock:
            snapshot = self._refresh()
            return snapshot.context.query.search_page(
                request.text,
                limit=request.limit,
                offset=request.offset,
                rdf_types=frozenset(request.rdf_types),
                modules=frozenset(request.modules),
            ).to_dict()

    def describe(self, request: DescribeInput) -> dict[str, object]:
        with self._lock:
            snapshot = self._refresh()
            description = snapshot.context.query.describe(request.iri)
            if description is None:
                raise McpRuntimeError("resource.not_found", "requested RDF resource does not exist")
            neighborhood = snapshot.context.query.neighborhood(
                request.iri,
                depth=request.depth,
                limits=NeighborhoodLimits(
                    max_depth=request.depth,
                    max_nodes=request.max_nodes,
                    max_edges=request.max_edges,
                ),
            )
            return {
                "description": description.to_dict(),
                "neighborhood": neighborhood.to_dict(),
                "impact": snapshot.context.impact.analyze(request.iri).to_dict(),
            }

    def get_context(self, request: ContextInput) -> dict[str, object]:
        with self._lock:
            snapshot = self._refresh()
            pack = snapshot.context.generate(
                ContextRequest(
                    task=request.task,
                    terms=tuple(request.terms),
                    modules=tuple(request.modules),
                    budget=ContextBudget(
                        max_terms=request.max_terms,
                        depth=request.depth,
                        max_bytes=request.max_bytes,
                    ),
                )
            )
            return {
                "payload": pack.payload,
                "json": pack.json,
                "markdown": pack.markdown,
                "truncated": pack.truncated,
            }

    def validate(self) -> dict[str, object]:
        with self._lock:
            snapshot = self._refresh()
            return (
                ValidationService(snapshot.store)
                .validate_dataset(snapshot.context.dataset)
                .to_dict()
            )

    def diff(self, request: DiffInput) -> dict[str, object]:
        with self._lock:
            snapshot = self._refresh()
            return (
                ProposalReviewService(snapshot.store, self.workspace)
                .review(base_ref=request.base)
                .to_dict()
            )

    def governance_rules(self) -> dict[str, object]:
        contract = AgentContractService(self.settings.repository_root)
        return {
            "contract": contract.status().to_dict(),
            "rules": [document.to_dict() for document in contract.rules],
        }

    def competency_questions(self) -> dict[str, object]:
        with self._lock:
            snapshot = self._refresh()
            return {"items": [item.to_dict() for item in snapshot.context.questions.list()]}

    def relevant_ontology(self, iri: str) -> dict[str, object]:
        return self.describe(DescribeInput(iri=iri, depth=1, max_nodes=100, max_edges=300))

    def propose_term(self, request: TermInput) -> dict[str, object]:
        def action(snapshot: _Snapshot) -> WriteResult:
            confirmation = SearchConfirmation(
                query=request.search_query,
                confirmed=request.search_confirmed,
                search_id=request.search_id,
            )
            form_values = tuple(
                (key, tuple(values)) for key, values in sorted(request.form_values.items())
            )
            if request.kind == "individual":
                if request.class_iri is None or request.source_id is None:
                    raise McpRuntimeError(
                        "mcp.individual_fields",
                        "individual proposals require class_iri and source_id",
                    )
                return snapshot.writer.save_individual(
                    IndividualDraft(
                        iri=request.iri,
                        class_iri=request.class_iri,
                        source_id=request.source_id,
                        preferred_label_es=request.preferred_label_es,
                        evidence=request.evidence,
                        author=request.author,
                        search=confirmation,
                        alternative_labels_es=tuple(request.alternative_labels_es),
                        status=request.status,
                        form_values=form_values,
                    )
                )
            return snapshot.writer.save_term(
                TermDraft(
                    iri=request.iri,
                    module_id=request.module_id,
                    kind=request.kind,
                    preferred_label_es=request.preferred_label_es,
                    definition_es=request.definition_es,
                    evidence=request.evidence,
                    author=request.author,
                    search=confirmation,
                    alternative_labels_es=tuple(request.alternative_labels_es),
                    status=request.status,
                    reading_direction_es=request.reading_direction_es,
                    valid_example=request.valid_example,
                    domain=request.domain,
                    range=request.range,
                    question_text_es=request.question_text_es,
                    acceptance_criterion_es=request.acceptance_criterion_es,
                    form_values=form_values,
                )
            )

        return self._write(request.agent, "ontology_propose_term", action)

    def propose_relation(self, request: RelationInput) -> dict[str, object]:
        return self._write(
            request.agent,
            "ontology_propose_relation",
            lambda snapshot: snapshot.writer.save_relation(
                RelationDraft(
                    subject=request.subject,
                    predicate=request.predicate,
                    object_iri=request.object_iri,
                    literal=request.literal,
                    datatype=request.datatype,
                    language=request.language,
                    evidence=request.evidence,
                    status=request.status,
                )
            ),
        )

    def deprecate_term(self, request: DeprecateInput) -> dict[str, object]:
        return self._write(
            request.agent,
            "ontology_deprecate_term",
            lambda snapshot: snapshot.writer.deprecate(
                DeprecationDraft(
                    iri=request.iri,
                    reason=request.reason,
                    replacement_iri=request.replacement_iri,
                )
            ),
        )

    def _write(
        self,
        agent: str,
        tool: str,
        action: Callable[[_Snapshot], WriteResult],
    ) -> dict[str, object]:
        with self._lock, self._write_lock:
            invocation_id = uuid4().hex
            files: tuple[str, ...] = ()
            published: _PublishedFile | None = None
            try:
                if not self.settings.write_enabled:
                    raise McpRuntimeError(
                        "mcp.write_disabled", "controlled write tools are disabled"
                    )
                workspace_status = self.workspace.require_proposal_branch()
                proposal_branch = workspace_status.branch
                if proposal_branch is None:  # pragma: no cover - guarded by the workspace
                    raise McpRuntimeError(
                        "mcp.concurrent_workspace",
                        "controlled writes require a named proposal branch",
                    )
                proposal_head = workspace_status.head
                snapshot = self._refresh()
                self._require_workspace_revision(proposal_branch, proposal_head)
                if self._marker() != snapshot.marker:
                    raise McpRuntimeError(
                        "mcp.concurrent_snapshot",
                        "Git revision or knowledge changed before controlled staging",
                    )
                self.audit.preflight()
                with self._staged_snapshot(snapshot, proposal_branch) as (staged, baseline):
                    result = action(staged)
                    staged_path = staged.store.knowledge_root.parent / result.path
                    resolved_staged = staged_path.resolve(strict=True)
                    if not resolved_staged.is_relative_to(staged.store.knowledge_root):
                        raise McpRuntimeError(
                            "mcp.write_escape", "writer returned a path outside knowledge/"
                        )
                    relative = resolved_staged.relative_to(staged.store.knowledge_root)
                    target = self.settings.knowledge_root / relative
                    files = (result.path,)
                    self._require_workspace_revision(proposal_branch, proposal_head)
                    if self._marker() != snapshot.marker:
                        raise McpRuntimeError(
                            "mcp.concurrent_snapshot",
                            "Git revision or knowledge changed while the controlled write "
                            "was staged",
                        )
                    published = self._publish_staged_file(
                        target,
                        resolved_staged,
                        baseline.get(relative.as_posix()),
                    )
                    self._require_workspace_revision(proposal_branch, proposal_head)
                next_snapshot = self._build_snapshot()
                self._require_workspace_revision(proposal_branch, proposal_head)
                payload = result.to_dict()
                payload["snapshot"] = next_snapshot.marker
                self._require_file_state(published.path, published.current)
                self.audit.record(
                    agent=agent,
                    tool=tool,
                    files=files,
                    result="success",
                    invocation_id=invocation_id,
                )
                self._protocol_audited.set(True)
                self._snapshot = next_snapshot
                return payload
            except Exception as error:
                rollback_error: Exception | None = None
                if published is not None:
                    try:
                        self._restore_published_file(published)
                        self._snapshot = self._build_snapshot()
                    except Exception as restore_error:  # noqa: BLE001 - report exact state
                        rollback_error = restore_error
                code = str(getattr(error, "code", "mcp.write_failed"))
                if rollback_error is not None:
                    code = "mcp.rollback_failed"
                try:
                    self.audit.record(
                        agent=agent,
                        tool=tool,
                        files=files,
                        result="rejected",
                        code=code,
                        invocation_id=invocation_id,
                    )
                    self._protocol_audited.set(True)
                except Exception as audit_error:
                    raise McpRuntimeError(
                        "mcp.audit_unavailable",
                        "controlled write aborted because its audit record was unavailable",
                    ) from audit_error
                if rollback_error is not None:
                    raise McpRuntimeError(
                        "mcp.rollback_failed",
                        "controlled write failed and its target could not be restored safely",
                    ) from rollback_error
                if isinstance(error, AuditWriteError):
                    raise McpRuntimeError(
                        "mcp.audit_unavailable",
                        "controlled write was restored because its success audit was unavailable",
                    ) from error
                raise

    def _capture_tree(self, root: Path) -> dict[str, _FileState]:
        captured: dict[str, _FileState] = {}
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise McpRuntimeError("mcp.write_symlink", "staged roots cannot contain symlinks")
            if path.is_file():
                metadata = path.stat()
                captured[path.relative_to(root).as_posix()] = _FileState(
                    content=path.read_bytes(),
                    mode=metadata.st_mode & 0o7777,
                    atime_ns=metadata.st_atime_ns,
                    mtime_ns=metadata.st_mtime_ns,
                )
        return captured

    @contextmanager
    def _staged_snapshot(
        self, snapshot: _Snapshot, proposal_branch: str
    ) -> Iterator[tuple[_Snapshot, dict[str, _FileState]]]:
        knowledge = self._capture_tree(self.settings.knowledge_root)
        configuration_root = self.settings.namespace_config.parent
        configuration = self._capture_tree(configuration_root)
        with tempfile.TemporaryDirectory(prefix="eow-mcp-stage-") as directory:
            repository = Path(directory)
            staged_knowledge = repository / "knowledge"
            staged_config = repository / "config"
            self._materialize_tree(staged_knowledge, knowledge)
            self._materialize_tree(staged_config, configuration)
            self._initialize_staged_git(repository, proposal_branch)
            store = FilesystemRdfStore(
                staged_knowledge,
                staged_config / self.settings.namespace_config.name,
            )
            context = AgentContextService(
                store,
                receipt_authority=self._receipts,
                snapshot_id=snapshot.marker,
            )
            workspace = GitWorkspaceService(repository, staged_knowledge)
            yield (
                _Snapshot(
                    snapshot.marker,
                    store,
                    context,
                    TermWriter(store, workspace, context.query),
                ),
                knowledge,
            )

    @staticmethod
    def _materialize_tree(root: Path, files: dict[str, _FileState]) -> None:
        root.mkdir(parents=True)
        for relative, state in files.items():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(state.content)
            destination.chmod(state.mode)
            os.utime(destination, ns=(state.atime_ns, state.mtime_ns))

    @staticmethod
    def _initialize_staged_git(repository: Path, proposal_branch: str) -> None:
        commands = (
            ("init", "--quiet", "--initial-branch=main"),
            ("config", "user.name", "MCP Staging"),
            ("config", "user.email", "mcp-staging@example.invalid"),
            ("add", "knowledge", "config"),
            ("commit", "--quiet", "-m", "chore: stage controlled MCP write"),
            ("switch", "--quiet", "--create", proposal_branch),
        )
        for arguments in commands:
            subprocess.run(("git", *arguments), cwd=repository, check=True, capture_output=True)

    def _require_workspace_revision(
        self,
        expected_branch: str,
        expected_head: str | None,
    ) -> None:
        """Fail closed when Git moves while one controlled write is in flight."""

        try:
            status = self.workspace.require_proposal_branch()
        except GitWorkspaceError as error:
            raise McpRuntimeError(
                "mcp.concurrent_workspace",
                "proposal branch or HEAD changed during the controlled write",
            ) from error
        if status.branch != expected_branch or status.head != expected_head:
            raise McpRuntimeError(
                "mcp.concurrent_workspace",
                "proposal branch or HEAD changed during the controlled write",
            )

    def _publish_staged_file(
        self,
        target: Path,
        staged: Path,
        expected: _FileState | None,
    ) -> _PublishedFile:
        if target.resolve(strict=False).parent != target.parent.resolve(strict=False):
            raise McpRuntimeError("mcp.write_symlink", "target parent cannot traverse symlinks")
        if not target.resolve(strict=False).is_relative_to(self.settings.knowledge_root):
            raise McpRuntimeError("mcp.write_escape", "target must remain inside knowledge/")
        created_directories = self._create_target_parents(target.parent)
        mode = expected.mode if expected is not None else 0o644
        temporary = self._materialize_temporary(target, staged.read_bytes(), mode)
        candidate = self._file_state(temporary)
        if candidate is None:  # pragma: no cover - materialization either creates or raises
            raise McpRuntimeError("mcp.write_failed", "staged candidate disappeared")
        if expected is None:
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as error:
                temporary.unlink(missing_ok=True)
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "responsible RDF file was created outside the staged write",
                ) from error
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            current = self._file_state(target)
            temporary.unlink(missing_ok=True)
            if not self._same_file_state(current, candidate):
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "new target changed immediately after atomic publication",
                )
        else:
            try:
                self._exchange_paths(temporary, target)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            observed = self._file_state(temporary)
            if not self._same_file_state(observed, expected):
                try:
                    self._compensate_exchange(temporary, target, candidate)
                except McpRuntimeError:
                    raise
                except Exception as error:
                    raise McpRuntimeError(
                        "mcp.concurrent_restore",
                        f"concurrent target is preserved at {temporary}",
                    ) from error
                temporary.unlink(missing_ok=True)
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "responsible RDF file changed outside the staged write",
                )
            current = self._file_state(target)
            temporary.unlink(missing_ok=True)
            if not self._same_file_state(current, candidate):
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "responsible RDF file changed immediately after atomic publication",
                )
        if current is None:  # pragma: no cover - atomic publication either publishes or raises
            raise McpRuntimeError("mcp.write_failed", "target disappeared after publication")
        return _PublishedFile(target, expected, current, created_directories)

    def _compensate_exchange(
        self,
        temporary: Path,
        target: Path,
        expected_target: _FileState,
    ) -> None:
        """Undo an exchange without overwriting a newer target-side edit."""

        self._exchange_paths(temporary, target)
        displaced = self._file_state(temporary)
        if self._same_file_state(displaced, expected_target):
            return
        # Do not chase an unbounded stream of target-side edits with another
        # exchange. The target keeps its current state and the state displaced
        # by this compensation becomes an explicit durable recovery artifact.
        recovery = self._preserve_recovery_file(
            temporary,
            target,
            reason="compensation",
        )
        raise McpRuntimeError(
            "mcp.concurrent_target",
            "target changed during compensating exchange; displaced state was preserved at "
            f"{recovery}",
        )

    def _restore_published_file(self, published: _PublishedFile) -> None:
        if published.previous is None:
            temporary = self._materialize_temporary(published.path, b"", 0o600)
            rollback_candidate = self._file_state(temporary)
            if rollback_candidate is None:  # pragma: no cover - materialization is strict
                raise McpRuntimeError("mcp.rollback_failed", "rollback marker disappeared")
            try:
                self._exchange_paths(temporary, published.path)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            observed = self._file_state(temporary)
            if not self._same_file_state(observed, published.current):
                self._compensate_exchange(
                    temporary,
                    published.path,
                    rollback_candidate,
                )
                temporary.unlink(missing_ok=True)
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "new target changed before rollback and was preserved",
                )
            temporary.unlink(missing_ok=True)
            detached = published.path.parent / (f".{published.path.name}.rollback-{uuid4().hex}")
            try:
                os.replace(published.path, detached)
            except FileNotFoundError as error:
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "new target disappeared during rollback",
                ) from error
            detached_state = self._file_state(detached)
            if not self._same_file_state(detached_state, rollback_candidate):
                recovery = self._preserve_recovery_file(
                    detached,
                    published.path,
                    reason="new-target-rollback",
                )
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "new target changed during rollback; detached state was preserved at "
                    f"{recovery}",
                )
            detached.unlink()
        else:
            temporary = self._materialize_temporary(
                published.path,
                published.previous.content,
                published.previous.mode,
            )
            os.utime(
                temporary,
                ns=(published.previous.atime_ns, published.previous.mtime_ns),
            )
            rollback_candidate = self._file_state(temporary)
            if rollback_candidate is None:  # pragma: no cover - materialization is strict
                raise McpRuntimeError("mcp.rollback_failed", "rollback candidate disappeared")
            try:
                self._exchange_paths(temporary, published.path)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            observed = self._file_state(temporary)
            if not self._same_file_state(observed, published.current):
                self._compensate_exchange(
                    temporary,
                    published.path,
                    rollback_candidate,
                )
                temporary.unlink(missing_ok=True)
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "target changed before rollback and was preserved",
                )
            restored = self._file_state(published.path)
            temporary.unlink(missing_ok=True)
            if not self._same_file_state(restored, rollback_candidate):
                raise McpRuntimeError(
                    "mcp.concurrent_target",
                    "target changed immediately after rollback exchange and was preserved",
                )
        for directory in published.created_directories:
            try:
                directory.rmdir()
            except OSError:
                break

    def _preserve_recovery_file(self, source: Path, target: Path, *, reason: str) -> str:
        """Move an unexpected displaced state to durable repository-local recovery."""

        recovery_root = self.settings.repository_root / ".eow/recovery"
        current = self.settings.repository_root
        for component in recovery_root.relative_to(self.settings.repository_root).parts:
            current /= component
            if current.is_symlink():
                raise McpRuntimeError(
                    "mcp.concurrent_restore",
                    f"displaced state remains at {source}",
                )
            current.mkdir(mode=0o700, exist_ok=True)
            if not current.is_dir():
                raise McpRuntimeError(
                    "mcp.concurrent_restore",
                    f"displaced state remains at {source}",
                )
        destination = recovery_root / (f"{target.name}.{reason}.{uuid4().hex}.recovery")
        try:
            os.replace(source, destination)
            descriptor = os.open(recovery_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except Exception as error:
            raise McpRuntimeError(
                "mcp.concurrent_restore",
                f"displaced state remains at {source}",
            ) from error
        return destination.relative_to(self.settings.repository_root).as_posix()

    def _create_target_parents(self, parent: Path) -> tuple[Path, ...]:
        missing: list[Path] = []
        current = parent
        while current != self.settings.knowledge_root and not current.exists():
            missing.append(current)
            current = current.parent
        if current.is_symlink() or not current.resolve(strict=True).is_relative_to(
            self.settings.knowledge_root
        ):
            raise McpRuntimeError("mcp.write_symlink", "target parent is not confined")
        created: list[Path] = []
        for directory in reversed(missing):
            directory.mkdir()
            created.insert(0, directory)
        return tuple(created)

    @staticmethod
    def _materialize_temporary(path: Path, content: bytes, mode: int) -> Path:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            return Path(temporary_name)
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            Path(temporary_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _exchange_paths(left: Path, right: Path) -> None:
        """Atomically exchange two paths, failing closed when unsupported."""

        system = platform.system()
        if system == "Linux":
            OntologyMcpRuntime._linux_exchange_paths(left, right)
            return
        if system == "Darwin":  # pragma: no cover - requires macOS
            OntologyMcpRuntime._macos_exchange_paths(left, right)
            return
        if system == "Windows":  # pragma: no cover - requires Windows
            OntologyMcpRuntime._windows_exchange_paths(left, right)
            return
        raise McpRuntimeError(
            "mcp.atomic_exchange_unavailable",
            f"safe controlled writes have no atomic exchange backend for {system}",
        )

    @staticmethod
    def _linux_exchange_paths(left: Path, right: Path) -> None:
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:  # pragma: no cover - Linux CI exposes renameat2
            raise McpRuntimeError(
                "mcp.atomic_exchange_unavailable",
                "safe controlled writes require renameat2(RENAME_EXCHANGE)",
            )
        renameat2.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        result = renameat2(
            -100,
            os.fsencode(left),
            -100,
            os.fsencode(right),
            2,
        )
        if result != 0:
            error_number = ctypes.get_errno()
            if error_number in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
                raise McpRuntimeError(
                    "mcp.atomic_exchange_unavailable",
                    "filesystem does not support atomic path exchange",
                )
            raise OSError(error_number, os.strerror(error_number), right)

    @staticmethod
    def _macos_exchange_paths(left: Path, right: Path) -> None:
        library = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(library, "renamex_np", None)
        if renamex_np is None:
            raise McpRuntimeError(
                "mcp.atomic_exchange_unavailable",
                "safe controlled writes require renamex_np(RENAME_SWAP)",
            )
        renamex_np.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        renamex_np.restype = ctypes.c_int
        if renamex_np(os.fsencode(left), os.fsencode(right), 2) != 0:
            error_number = ctypes.get_errno()
            if error_number in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
                raise McpRuntimeError(
                    "mcp.atomic_exchange_unavailable",
                    "filesystem does not support renamex_np(RENAME_SWAP)",
                )
            raise OSError(error_number, os.strerror(error_number), right)

    @staticmethod
    def _windows_exchange_paths(left: Path, right: Path) -> None:
        backup_descriptor, backup_name = tempfile.mkstemp(
            prefix=f".{right.name}.exchange-",
            dir=right.parent,
        )
        os.close(backup_descriptor)
        backup = Path(backup_name)
        backup.unlink()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        replace_file = kernel32.ReplaceFileW
        replace_file.argtypes = (
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        replace_file.restype = ctypes.c_int
        replaced = replace_file(str(right), str(left), str(backup), 1, None, None)
        if not replaced:
            error_number = ctypes.get_last_error()  # type: ignore[attr-defined]
            message = ctypes.FormatError(error_number)  # type: ignore[attr-defined]
            raise OSError(error_number, message, right)
        try:
            os.rename(backup, left)
        except Exception as error:
            restored = replace_file(str(right), str(backup), str(left), 1, None, None)
            if restored:
                raise McpRuntimeError(
                    "mcp.atomic_exchange_unavailable",
                    "Windows exchange bookkeeping failed and was atomically reverted",
                ) from error
            raise McpRuntimeError(
                "mcp.concurrent_restore",
                f"Windows exchange preserved the displaced target at {backup}",
            ) from error

    @staticmethod
    def _file_state(path: Path) -> _FileState | None:
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise McpRuntimeError("mcp.concurrent_target", "target is not a regular file")
        metadata = path.stat()
        return _FileState(
            content=path.read_bytes(),
            mode=metadata.st_mode & 0o7777,
            atime_ns=metadata.st_atime_ns,
            mtime_ns=metadata.st_mtime_ns,
        )

    @classmethod
    def _require_file_state(cls, path: Path, expected: _FileState | None) -> None:
        actual = cls._file_state(path)
        if not cls._same_file_state(actual, expected):
            raise McpRuntimeError(
                "mcp.concurrent_target",
                "responsible RDF file changed outside the staged write",
            )

    @staticmethod
    def _same_file_state(left: _FileState | None, right: _FileState | None) -> bool:
        if left is None or right is None:
            return left is right
        return (
            left.content == right.content
            and left.mode == right.mode
            and left.mtime_ns == right.mtime_ns
        )

    def _refresh(self) -> _Snapshot:
        marker = self._marker()
        if marker != self._snapshot.marker:
            self._snapshot = self._build_snapshot(marker)
        return self._snapshot

    def _build_snapshot(self, marker: str | None = None) -> _Snapshot:
        selected_marker = marker or self._marker()
        store = FilesystemRdfStore(self.settings.knowledge_root, self.settings.namespace_config)
        context = AgentContextService(
            store,
            receipt_authority=self._receipts,
            snapshot_id=selected_marker,
        )
        writer = TermWriter(store, self.workspace, context.query)
        return _Snapshot(selected_marker, store, context, writer)

    def _marker(self) -> str:
        status = self.workspace.status()
        fingerprint = content_fingerprint(
            self.settings.knowledge_root,
            self.settings.namespace_config.parent,
        )
        return "|".join((status.branch or "", status.head or "", fingerprint))

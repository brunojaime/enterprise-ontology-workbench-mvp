"""Atomic, commit-aware runtime snapshots for the FastAPI adapter."""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ontology_core import (
    AgentContextService,
    CompetencyQuestionRepository,
    CompetencyQuestionService,
    FilesystemRdfStore,
    GitCommitResult,
    GitHistoryService,
    GitWorkspaceService,
    ImpactService,
    OntologyQueryService,
    ReadOnlySparqlService,
    ResourceDetailService,
    ValidationReport,
    ValidationService,
    content_fingerprint,
)
from ontology_core.search_receipts import SearchReceiptAuthority
from rdflib import Dataset

from enterprise_ontology_api.config import ApiSettings


@dataclass(frozen=True)
class RepositoryRevision:
    branch: str | None
    commit: str | None
    dirty: bool
    fingerprint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"branch": self.branch, "commit": self.commit, "dirty": self.dirty}


@dataclass(frozen=True)
class RuntimeSnapshot:
    store: FilesystemRdfStore
    dataset: Dataset
    query: OntologyQueryService
    impact: ImpactService
    validation: ValidationService
    questions: CompetencyQuestionRepository
    competency: CompetencyQuestionService
    sparql: ReadOnlySparqlService
    context: AgentContextService
    detail: ResourceDetailService
    history: GitHistoryService
    validation_report: ValidationReport
    revision: RepositoryRevision
    generation: int
    loaded_at: str


@dataclass(frozen=True)
class OperationMetric:
    count: int
    failures: int
    total_duration_ms: float
    last_duration_ms: float | None

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "count": self.count,
            "failures": self.failures,
            "total_duration_ms": self.total_duration_ms,
            "last_duration_ms": self.last_duration_ms,
        }


@dataclass(frozen=True)
class RuntimeReadiness:
    snapshot: RuntimeSnapshot | None
    quads: int
    conforms: bool
    worktree_ready: bool
    dataset_detail: str
    worktree_detail: str


@dataclass
class _MutableMetric:
    count: int = 0
    failures: int = 0
    total_duration_ms: float = 0.0
    last_duration_ms: float | None = None


class RuntimeMetrics:
    """Thread-safe basic load, validation and query measurements."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, _MutableMetric] = {
            name: _MutableMetric() for name in ("load", "validation", "query")
        }

    def record(self, operation: str, duration_ms: float, *, failed: bool = False) -> None:
        with self._lock:
            value = self._values[operation]
            value.count += 1
            value.failures += int(failed)
            value.total_duration_ms = round(value.total_duration_ms + duration_ms, 3)
            value.last_duration_ms = round(duration_ms, 3)

    def snapshot(self) -> dict[str, dict[str, int | float | None]]:
        with self._lock:
            return {
                operation: OperationMetric(
                    count=value.count,
                    failures=value.failures,
                    total_duration_ms=value.total_duration_ms,
                    last_duration_ms=value.last_duration_ms,
                ).to_dict()
                for operation, value in self._values.items()
            }


def read_repository_revision(settings: ApiSettings) -> RepositoryRevision:
    def git(*arguments: str) -> str | None:
        try:
            completed = subprocess.run(
                ("git", *arguments),
                cwd=settings.repository_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return completed.stdout.strip()

    return RepositoryRevision(
        branch=git("branch", "--show-current"),
        commit=git("rev-parse", "HEAD"),
        dirty=bool(git("status", "--porcelain")),
        fingerprint=content_fingerprint(
            settings.knowledge_root, settings.repository_root / "config"
        ),
    )


class RuntimeManager:
    """Own one internally consistent snapshot and swap it only after a full reload."""

    def __init__(
        self,
        settings: ApiSettings,
        *,
        revision_provider: Callable[[], RepositoryRevision] | None = None,
    ) -> None:
        self.settings = settings
        self._revision_provider = revision_provider or (lambda: read_repository_revision(settings))
        self._lock = threading.RLock()
        self._metrics = RuntimeMetrics()
        self._search_receipts = SearchReceiptAuthority()
        revision = self._revision_provider()
        self._snapshot = self._build_snapshot(1, revision)

    def snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            revision = self._revision_provider()
            if revision != self._snapshot.revision:
                self._snapshot = self._build_snapshot(self._snapshot.generation + 1, revision)
            return self._snapshot

    def current(self) -> RuntimeSnapshot:
        """Return the published snapshot without probing Git or triggering reload."""

        with self._lock:
            return self._snapshot

    def metrics(self) -> dict[str, dict[str, int | float | None]]:
        return self._metrics.snapshot()

    def record_query(self, duration_ms: float, *, failed: bool) -> None:
        self._metrics.record("query", duration_ms, failed=failed)

    def probe_readiness(self) -> RuntimeReadiness:
        """Probe current Git and RDF from disk without trusting a cached snapshot."""

        with self._lock:
            try:
                revision = self._revision_provider()
            except Exception:  # noqa: BLE001 - readiness must fail closed at its boundary
                return RuntimeReadiness(
                    snapshot=None,
                    quads=0,
                    conforms=False,
                    worktree_ready=False,
                    dataset_detail="The current RDF repository could not be probed.",
                    worktree_detail="The Git worktree probe failed.",
                )
            worktree_ready = revision.commit is not None
            generation = (
                self._snapshot.generation + 1
                if revision != self._snapshot.revision
                else self._snapshot.generation
            )
            try:
                candidate = self._build_snapshot(generation, revision)
                stats = candidate.query.stats(candidate.context.modules)
            except Exception:  # noqa: BLE001 - operational probe normalizes load failures
                return RuntimeReadiness(
                    snapshot=None,
                    quads=0,
                    conforms=False,
                    worktree_ready=worktree_ready,
                    dataset_detail="The current RDF repository could not be loaded and validated.",
                    worktree_detail=(
                        f"Git revision {revision.commit} is available."
                        if worktree_ready
                        else "A readable Git worktree and revision are required."
                    ),
                )
            try:
                confirmed_revision = self._revision_provider()
            except Exception:  # noqa: BLE001 - readiness must fail closed
                return RuntimeReadiness(
                    snapshot=None,
                    quads=stats.quads,
                    conforms=False,
                    worktree_ready=False,
                    dataset_detail="The repository changed while readiness was probing it.",
                    worktree_detail="The Git worktree could not be confirmed after the RDF probe.",
                )
            if confirmed_revision != revision:
                return RuntimeReadiness(
                    snapshot=None,
                    quads=stats.quads,
                    conforms=False,
                    worktree_ready=confirmed_revision.commit is not None,
                    dataset_detail="The repository changed while readiness was probing it.",
                    worktree_detail="The Git revision changed during the readiness probe.",
                )
            dataset_ready = stats.quads > 0 and candidate.validation_report.conforms
            if dataset_ready and worktree_ready and revision != self._snapshot.revision:
                self._snapshot = candidate
            return RuntimeReadiness(
                snapshot=candidate,
                quads=stats.quads,
                conforms=candidate.validation_report.conforms,
                worktree_ready=worktree_ready,
                dataset_detail=(
                    f"{stats.quads} quads loaded; validation conforms."
                    if dataset_ready
                    else f"{stats.quads} quads loaded; validation is not conforming."
                ),
                worktree_detail=(
                    f"Git revision {revision.commit} is available."
                    if worktree_ready
                    else "A readable Git worktree and revision are required."
                ),
            )

    def reload(self) -> RuntimeSnapshot:
        with self._lock:
            revision = self._revision_provider()
            replacement = self._build_snapshot(self._snapshot.generation + 1, revision)
            self._snapshot = replacement
            return replacement

    def update_validation(
        self,
        source: RuntimeSnapshot,
        report: ValidationReport,
    ) -> bool:
        with self._lock:
            current = self._snapshot
            if current is not source:
                return False
            self._snapshot = RuntimeSnapshot(
                store=current.store,
                dataset=current.dataset,
                query=current.query,
                impact=current.impact,
                validation=current.validation,
                questions=current.questions,
                competency=current.competency,
                sparql=current.sparql,
                context=current.context,
                detail=current.detail,
                history=current.history,
                validation_report=report,
                revision=current.revision,
                generation=current.generation,
                loaded_at=current.loaded_at,
            )
            return True

    def validate_current(self) -> ValidationReport:
        """Validate and update one generation while excluding concurrent reloads."""

        with self._lock:
            current = self._snapshot
            report = current.validation.validate_dataset(current.dataset)
            updated = self.update_validation(current, report)
            if not updated:  # pragma: no cover - the re-entrant lock makes this unreachable
                raise RuntimeError("runtime changed during locked validation")
            return report

    def commit_proposal(
        self,
        workspace: GitWorkspaceService,
        *,
        module: str,
        summary: str,
        exception_reason: str | None,
    ) -> GitCommitResult:
        """Reload, validate and commit one exact content fingerprint under one lock."""

        with self._lock:
            revision = self._revision_provider()
            candidate = self._build_snapshot(self._snapshot.generation + 1, revision)
            result = workspace.commit(
                module=module,
                summary=summary,
                validation=candidate.validation_report,
                exception_reason=exception_reason,
                expected_head=revision.commit,
                expected_fingerprint=revision.fingerprint,
            )
            replacement_revision = self._revision_provider()
            self._snapshot = self._build_snapshot(candidate.generation + 1, replacement_revision)
            return result

    def _build_snapshot(self, generation: int, revision: RepositoryRevision) -> RuntimeSnapshot:
        store = FilesystemRdfStore(self.settings.knowledge_root, self.settings.namespace_config)
        snapshot_id = "|".join(
            (
                str(generation),
                revision.branch or "",
                revision.commit or "",
                "dirty" if revision.dirty else "clean",
                revision.fingerprint or "",
            )
        )
        load_started = time.perf_counter()
        try:
            context = AgentContextService(
                store,
                receipt_authority=self._search_receipts,
                snapshot_id=snapshot_id,
            )
        except Exception:
            self._metrics.record("load", (time.perf_counter() - load_started) * 1000, failed=True)
            raise
        self._metrics.record("load", (time.perf_counter() - load_started) * 1000)
        dataset = context.dataset
        validation = ValidationService(store)
        validation_started = time.perf_counter()
        try:
            validation_report = validation.validate_dataset(dataset)
        except Exception:
            self._metrics.record(
                "validation", (time.perf_counter() - validation_started) * 1000, failed=True
            )
            raise
        self._metrics.record(
            "validation",
            (time.perf_counter() - validation_started) * 1000,
            failed=not validation_report.conforms,
        )
        sparql = ReadOnlySparqlService(dataset, store.prefixes)
        competency = CompetencyQuestionService(
            context.questions,
            sparql,
            store.knowledge_root,
        )
        detail = ResourceDetailService(context.query, context.impact)
        history = GitHistoryService(self.settings.repository_root, store.knowledge_root)
        return RuntimeSnapshot(
            store=store,
            dataset=dataset,
            query=context.query,
            impact=context.impact,
            validation=validation,
            questions=context.questions,
            competency=competency,
            sparql=sparql,
            context=context,
            detail=detail,
            history=history,
            validation_report=validation_report,
            revision=revision,
            generation=generation,
            loaded_at=datetime.now(UTC).isoformat(),
        )

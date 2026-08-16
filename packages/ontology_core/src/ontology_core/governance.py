"""Deterministic pull-request governance reports over canonical RDF and Git."""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import OWL
from rdflib.term import IdentifiedNode

from ontology_core.diff import SemanticDiffReport, SemanticDiffService
from ontology_core.query import RdfValue
from ontology_core.store import FilesystemRdfStore
from ontology_core.validation import ValidationReport, ValidationService, ValidationSource
from ontology_core.workspace import GitWorkspaceError


@dataclass(frozen=True)
class DeprecatedUsage:
    """One live reference to a term whose governed status is deprecated."""

    term: RdfValue
    subject: RdfValue
    predicate: RdfValue
    object: RdfValue
    graph: RdfValue

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term.to_dict(),
            "subject": self.subject.to_dict(),
            "predicate": self.predicate.to_dict(),
            "object": self.object.to_dict(),
            "graph": self.graph.to_dict(),
        }


@dataclass(frozen=True)
class PullRequestGovernanceReport:
    """Portable artifact and Markdown source for a pull-request check."""

    base: str
    head: str
    initial_import: bool
    validation: ValidationReport
    semantic_diff: SemanticDiffReport | None
    rdf_changed_paths: tuple[str, ...]
    semantic_empty: bool
    deprecated_usages: tuple[DeprecatedUsage, ...]
    warnings: tuple[str, ...]

    @property
    def affected_resources(self) -> tuple[str, ...]:
        if self.semantic_diff is None:
            return ()
        return tuple(sorted(change.resource.value for change in self.semantic_diff.changes))

    @property
    def affected_modules(self) -> tuple[str, ...]:
        return self.semantic_diff.affected_modules if self.semantic_diff is not None else ()

    @property
    def semantic_diff_status(self) -> str:
        return "completed" if self.semantic_diff is not None else "not_executable"

    @property
    def passed(self) -> bool:
        return self.validation.conforms and self.semantic_diff is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "base": self.base,
            "head": self.head,
            "initial_import": self.initial_import,
            "passed": self.passed,
            "validation": self.validation.to_dict(),
            "semantic_diff_status": self.semantic_diff_status,
            "semantic_diff": self.semantic_diff.to_dict() if self.semantic_diff else None,
            "rdf_changed_paths": list(self.rdf_changed_paths),
            "semantic_empty": self.semantic_empty,
            "affected_modules": list(self.affected_modules),
            "affected_resources": list(self.affected_resources),
            "deprecated_usages": [usage.to_dict() for usage in self.deprecated_usages],
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def to_markdown(self) -> str:
        counts = self.validation.to_dict()["counts"]
        assert isinstance(counts, dict)
        lines = [
            "## Enterprise Ontology Workbench — gobernanza semántica",
            "",
            f"- Base: `{_markdown(self.base)}`",
            f"- Head: `{_markdown(self.head)}`",
            (
                "- Dataset base: **vacío (importación inicial)**"
                if self.initial_import
                else "- Dataset base: **cargado desde Git**"
            ),
            f"- Validación: **{'conforme' if self.validation.conforms else 'no conforme'}**",
            f"- Diff semántico: **{self.semantic_diff_status}**",
            (
                "- Hallazgos: "
                f"{counts.get('error', 0)} errores, {counts.get('warning', 0)} warnings, "
                f"{counts.get('info', 0)} informativos"
            ),
            f"- Usos de términos deprecados: **{len(self.deprecated_usages)}**",
            "",
            "### Módulos afectados",
            "",
            *_markdown_items(self.affected_modules),
            "",
            "### Recursos afectados",
            "",
            *_markdown_items(self.affected_resources),
        ]
        if self.warnings:
            lines.extend(("", "### Advertencias", ""))
            lines.extend(f"- ⚠️ {_markdown(warning)}" for warning in self.warnings)
        if self.deprecated_usages:
            lines.extend(("", "### Referencias a términos deprecados", ""))
            for usage in self.deprecated_usages[:100]:
                lines.append(
                    f"- `{_markdown(usage.term.value)}` en `{_markdown(usage.graph.value)}`"
                )
            if len(self.deprecated_usages) > 100:
                lines.append(
                    f"- … {len(self.deprecated_usages) - 100} referencias adicionales "
                    "en el artifact"
                )
        return "\n".join(lines) + "\n"


class PullRequestGovernanceService:
    """Compute CI governance without moving semantic rules into GitHub YAML."""

    def __init__(self, repository_root: Path, store: FilesystemRdfStore) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        self.store = store
        if not store.knowledge_root.is_relative_to(self.repository_root):
            raise ValueError("knowledge root must remain inside the repository")

    def build(
        self,
        *,
        base_ref: str,
        head_ref: str,
        changed_paths: tuple[str, ...],
    ) -> PullRequestGovernanceReport:
        base_dataset, initial_import = self._dataset_at_revision(base_ref)
        validation = ValidationService(self.store).validate_repository(baseline=base_dataset)
        rdf_paths = tuple(
            sorted(
                {
                    path
                    for path in changed_paths
                    if path.startswith("knowledge/")
                    and Path(path).suffix.lower() in {".ttl", ".trig"}
                }
            )
        )
        parser_failed = any(issue.source is ValidationSource.PARSER for issue in validation.issues)
        semantic_diff: SemanticDiffReport | None = None
        deprecated_usages: tuple[DeprecatedUsage, ...] = ()
        if not parser_failed:
            head_dataset = self.store.load()
            semantic_diff = SemanticDiffService(self.store.prefixes).compare(
                base_dataset,
                head_dataset,
                base_ref=base_ref,
                head_ref=head_ref,
            )
            deprecated_usages = self.find_deprecated_usages(head_dataset)
        semantic_empty = (
            bool(rdf_paths)
            and semantic_diff is not None
            and not (semantic_diff.added_quads or semantic_diff.removed_quads)
        )
        warnings: list[str] = []
        if semantic_empty:
            warnings.append(
                "Hay archivos RDF modificados, pero el Dataset no cambió semánticamente."
            )
        if deprecated_usages:
            warnings.append(
                f"Se detectaron {len(deprecated_usages)} referencias a términos deprecados."
            )
        if semantic_diff is None:
            warnings.append("El diff semántico no pudo ejecutarse porque el RDF actual no parsea.")
        return PullRequestGovernanceReport(
            base=base_ref,
            head=head_ref,
            initial_import=initial_import,
            validation=validation,
            semantic_diff=semantic_diff,
            rdf_changed_paths=rdf_paths,
            semantic_empty=semantic_empty,
            deprecated_usages=deprecated_usages,
            warnings=tuple(warnings),
        )

    def find_deprecated_usages(self, dataset: Dataset) -> tuple[DeprecatedUsage, ...]:
        status = URIRef(f"{self.store.prefixes.configuration.base}ontology/core#status")
        deprecated = {
            subject
            for subject, predicate, obj, _ in dataset.quads((None, None, None, None))
            if isinstance(subject, URIRef)
            and (
                (predicate == status and obj == Literal("deprecated"))
                or (predicate == OWL.deprecated and obj == Literal(True))
            )
        }
        usages: list[DeprecatedUsage] = []
        for subject, predicate, obj, graph in dataset.quads((None, None, None, None)):
            referenced = tuple(
                sorted(
                    {term for term in deprecated if predicate == term or obj == term},
                    key=str,
                )
            )
            if not isinstance(graph, IdentifiedNode):
                continue
            for term in referenced:
                usages.append(
                    DeprecatedUsage(
                        term=RdfValue.from_node(term, self.store.prefixes),
                        subject=RdfValue.from_node(subject, self.store.prefixes),
                        predicate=RdfValue.from_node(predicate, self.store.prefixes),
                        object=RdfValue.from_node(obj, self.store.prefixes),
                        graph=RdfValue.from_node(graph, self.store.prefixes),
                    )
                )
        return tuple(
            sorted(
                usages,
                key=lambda item: (
                    item.term.value,
                    item.graph.value,
                    item.subject.value,
                    item.predicate.value,
                    item.object.value,
                ),
            )
        )

    def _dataset_at_revision(self, revision: str) -> tuple[Dataset, bool]:
        if not revision or revision.startswith("-") or "\x00" in revision:
            raise GitWorkspaceError("git.invalid_revision", "The base revision is invalid.")
        revision_exists = subprocess.run(
            ("git", "cat-file", "-e", f"{revision}^{{commit}}"),
            cwd=self.repository_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
        if revision_exists.returncode != 0:
            raise GitWorkspaceError(
                "git.base_unavailable",
                "The selected Git base revision does not exist.",
            )
        tree = subprocess.run(
            ("git", "ls-tree", "-z", "--name-only", revision, "--", "knowledge", "config"),
            cwd=self.repository_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
        if tree.returncode != 0:
            raise GitWorkspaceError(
                "git.base_unavailable",
                "The selected Git base tree could not be inspected.",
            )
        roots = {item.decode("utf-8") for item in tree.stdout.split(b"\0") if item}
        if "knowledge" not in roots:
            return Dataset(), True
        if "config" not in roots:
            raise GitWorkspaceError(
                "git.base_unavailable",
                "The published RDF base contains knowledge/ but no config/ directory.",
            )
        completed = subprocess.run(
            ("git", "archive", "--format=tar", revision, "knowledge", "config"),
            cwd=self.repository_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise GitWorkspaceError(
                "git.base_unavailable",
                "The published RDF base is not available at the selected revision.",
            )
        temporary = tempfile.TemporaryDirectory(prefix="eow-ci-base-")
        root = Path(temporary.name)
        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
            archive.extractall(root, filter="data")
        store = FilesystemRdfStore(root / "knowledge", root / "config/namespace.yaml")
        store._pull_request_governance_temporary = temporary  # type: ignore[attr-defined]
        return store.load(), False


def _markdown(value: str) -> str:
    return value.replace("`", "\\`").replace("\r", " ").replace("\n", " ")


def _markdown_items(values: tuple[str, ...]) -> list[str]:
    if not values:
        return ["- Ninguno"]
    limit = 200
    items = [f"- `{_markdown(value)}`" for value in values[:limit]]
    if len(values) > limit:
        items.append(f"- … {len(values) - limit} adicionales en el artifact")
    return items

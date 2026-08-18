"""Order-independent semantic diff and proposal review contracts."""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from typing import Literal as TypingLiteral

from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.compare import to_canonical_graph
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS
from rdflib.term import IdentifiedNode, Node

from ontology_core.impact import ImpactService
from ontology_core.prefixes import PrefixResolver
from ontology_core.query import OntologyQueryService, RdfValue
from ontology_core.store import FilesystemRdfStore
from ontology_core.validation import ValidationReport, ValidationService
from ontology_core.workspace import GitWorkspaceError, GitWorkspaceService

ChangeCategory = TypingLiteral[
    "type",
    "label",
    "definition",
    "hierarchy",
    "domain_range",
    "status",
    "evidence",
    "relation",
    "other",
]


@dataclass(frozen=True)
class SemanticQuad:
    subject: RdfValue
    predicate: RdfValue
    object: RdfValue
    graph: RdfValue
    category: ChangeCategory

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject.to_dict(),
            "predicate": self.predicate.to_dict(),
            "object": self.object.to_dict(),
            "graph": self.graph.to_dict(),
            "category": self.category,
        }


@dataclass(frozen=True)
class ResourceChange:
    resource: RdfValue
    categories: tuple[ChangeCategory, ...]
    added: tuple[SemanticQuad, ...]
    removed: tuple[SemanticQuad, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "resource": self.resource.to_dict(),
            "categories": list(self.categories),
            "added": [quad.to_dict() for quad in self.added],
            "removed": [quad.to_dict() for quad in self.removed],
        }


@dataclass(frozen=True)
class SemanticDiffReport:
    base: str
    head: str
    added_resources: tuple[RdfValue, ...]
    modified_resources: tuple[RdfValue, ...]
    deprecated_resources: tuple[RdfValue, ...]
    added_quads: tuple[SemanticQuad, ...]
    removed_quads: tuple[SemanticQuad, ...]
    changes: tuple[ResourceChange, ...]
    affected_modules: tuple[str, ...]
    potentially_impacted_questions: tuple[RdfValue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "base": self.base,
            "head": self.head,
            "added_resources": [value.to_dict() for value in self.added_resources],
            "modified_resources": [value.to_dict() for value in self.modified_resources],
            "deprecated_resources": [value.to_dict() for value in self.deprecated_resources],
            "added_quads": [quad.to_dict() for quad in self.added_quads],
            "removed_quads": [quad.to_dict() for quad in self.removed_quads],
            "changes": [change.to_dict() for change in self.changes],
            "affected_modules": list(self.affected_modules),
            "potentially_impacted_questions": [
                value.to_dict() for value in self.potentially_impacted_questions
            ],
        }


@dataclass(frozen=True)
class ProposalReview:
    diff: SemanticDiffReport
    validation: ValidationReport
    impact: dict[str, dict[str, object]]
    evidence: tuple[SemanticQuad, ...]
    ready_to_commit: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "diff": self.diff.to_dict(),
            "validation": self.validation.to_dict(),
            "impact": self.impact,
            "evidence": [quad.to_dict() for quad in self.evidence],
            "ready_to_commit": self.ready_to_commit,
        }


CanonicalQuad = tuple[Node, Node, Node, IdentifiedNode]

ENCODED_QUAD = URIRef("urn:eow:canonical:Quad")
ENCODED_SUBJECT = URIRef("urn:eow:canonical:subject")
ENCODED_PREDICATE = URIRef("urn:eow:canonical:predicate")
ENCODED_OBJECT = URIRef("urn:eow:canonical:object")
ENCODED_GRAPH = URIRef("urn:eow:canonical:graph")


class SemanticDiffService:
    """Compare RDF datasets as canonical quad sets, never serialized text."""

    def __init__(self, prefixes: PrefixResolver) -> None:
        self.prefixes = prefixes
        base = prefixes.configuration.base
        self.status_predicate = URIRef(f"{base}ontology/core#status")
        self.competency_type = URIRef(f"{base}ontology/competency#CompetencyQuestion")

    def compare(
        self,
        base_dataset: Dataset,
        head_dataset: Dataset,
        *,
        base_ref: str,
        head_ref: str,
    ) -> SemanticDiffReport:
        base_quads = self._canonical_quads(base_dataset)
        head_quads = self._canonical_quads(head_dataset)
        added_raw = tuple(sorted(head_quads - base_quads, key=self._quad_key))
        removed_raw = tuple(sorted(base_quads - head_quads, key=self._quad_key))
        added = tuple(self._view(quad) for quad in added_raw)
        removed = tuple(self._view(quad) for quad in removed_raw)

        base_subjects = {quad[0] for quad in base_quads if isinstance(quad[0], URIRef)}
        head_subjects = {quad[0] for quad in head_quads if isinstance(quad[0], URIRef)}
        added_groups = tuple(self._change_owner(quad[0], head_quads, quad[3]) for quad in added_raw)
        removed_groups = tuple(
            self._change_owner(quad[0], base_quads, quad[3]) for quad in removed_raw
        )
        changed_subjects = set((*added_groups, *removed_groups))
        directly_changed_iris = {
            quad[0] for quad in (*added_raw, *removed_raw) if isinstance(quad[0], URIRef)
        }
        added_subjects = directly_changed_iris & (head_subjects - base_subjects)
        modified_subjects = changed_subjects - added_subjects
        deprecated_subjects = {
            subject
            for subject, predicate, obj, _ in head_quads
            if isinstance(subject, URIRef)
            and (
                (predicate == self.status_predicate and str(obj) == "deprecated")
                or (predicate == OWL.deprecated and obj == Literal(True))
            )
            and subject in changed_subjects
        }
        head_query = OntologyQueryService(head_dataset, self.prefixes)
        base_query = OntologyQueryService(base_dataset, self.prefixes)
        affected_modules = sorted(
            {
                str(module)
                for resource in changed_subjects
                for module in (
                    *head_query.resource_modules(resource),
                    *base_query.resource_modules(resource),
                )
            }
        )
        question_subjects = {
            subject
            for subject, predicate, obj, _ in head_quads
            if predicate == RDF.type and obj == self.competency_type and isinstance(subject, URIRef)
        }
        impacted_questions: set[URIRef] = set()
        for subject, _, obj, _ in head_quads:
            if (
                isinstance(subject, URIRef)
                and subject in question_subjects
                and obj in changed_subjects
            ):
                impacted_questions.add(subject)

        changes: list[ResourceChange] = []
        for resource in sorted(changed_subjects, key=str):
            resource_added = tuple(
                quad for quad, owner in zip(added, added_groups, strict=True) if owner == resource
            )
            resource_removed = tuple(
                quad
                for quad, owner in zip(removed, removed_groups, strict=True)
                if owner == resource
            )
            categories = tuple(
                sorted(
                    {quad.category for quad in (*resource_added, *resource_removed)},
                    key=self._category_order,
                )
            )
            changes.append(
                ResourceChange(
                    resource=RdfValue.from_node(resource, self.prefixes),
                    categories=categories,
                    added=resource_added,
                    removed=resource_removed,
                )
            )
        return SemanticDiffReport(
            base=base_ref,
            head=head_ref,
            added_resources=self._values(added_subjects),
            modified_resources=self._values(modified_subjects),
            deprecated_resources=self._values(deprecated_subjects),
            added_quads=added,
            removed_quads=removed,
            changes=tuple(changes),
            affected_modules=tuple(affected_modules),
            potentially_impacted_questions=self._values(impacted_questions),
        )

    def _canonical_quads(self, dataset: Dataset) -> set[CanonicalQuad]:
        encoded = Graph()
        original_bnodes = {
            node
            for quad in dataset.quads((None, None, None, None))
            for node in quad
            if isinstance(node, BNode)
        }
        for subject, predicate, obj, graph_iri in dataset.quads((None, None, None, None)):
            if graph_iri is None:
                continue
            assertion = BNode()
            while assertion in original_bnodes:
                assertion = BNode()
            encoded.add((assertion, RDF.type, ENCODED_QUAD))
            encoded.add((assertion, ENCODED_SUBJECT, subject))
            encoded.add((assertion, ENCODED_PREDICATE, predicate))
            encoded.add((assertion, ENCODED_OBJECT, obj))
            encoded.add((assertion, ENCODED_GRAPH, graph_iri))
        canonical = to_canonical_graph(encoded)
        result: set[CanonicalQuad] = set()
        for assertion_node in canonical.subjects(RDF.type, ENCODED_QUAD):
            subject = self._encoded_value(canonical, assertion_node, ENCODED_SUBJECT)
            predicate = self._encoded_value(canonical, assertion_node, ENCODED_PREDICATE)
            obj = self._encoded_value(canonical, assertion_node, ENCODED_OBJECT)
            canonical_graph_iri = self._encoded_value(canonical, assertion_node, ENCODED_GRAPH)
            if not isinstance(canonical_graph_iri, IdentifiedNode):
                raise ValueError("canonical quad graph must be identified")
            result.add((subject, predicate, obj, canonical_graph_iri))
        return result

    @staticmethod
    def _encoded_value(graph: Graph, subject: Node, predicate: URIRef) -> Node:
        values = tuple(graph.objects(subject, predicate))
        if len(values) != 1:
            raise ValueError("canonical quad encoding is incomplete")
        return values[0]

    @staticmethod
    def _change_owner(
        subject: Node,
        quads: set[CanonicalQuad],
        graph_iri: IdentifiedNode,
    ) -> URIRef:
        if isinstance(subject, URIRef):
            return subject
        if isinstance(subject, BNode):
            visited = {subject}
            frontier = {subject}
            while frontier:
                owners = sorted(
                    {
                        candidate
                        for candidate, _, obj, _ in quads
                        if obj in frontier and isinstance(candidate, URIRef)
                    },
                    key=str,
                )
                if owners:
                    return owners[0]
                connected: set[BNode] = set()
                for candidate, _, obj, _ in quads:
                    if candidate in frontier and isinstance(obj, BNode):
                        connected.add(obj)
                    if obj in frontier and isinstance(candidate, BNode):
                        connected.add(candidate)
                frontier = connected - visited
                visited.update(frontier)
        identifier = sha256(str(graph_iri).encode()).hexdigest()[:24]
        return URIRef(f"urn:eow:technical-change:{identifier}")

    def _view(self, quad: CanonicalQuad) -> SemanticQuad:
        subject, predicate, obj, graph = quad
        return SemanticQuad(
            subject=RdfValue.from_node(subject, self.prefixes),
            predicate=RdfValue.from_node(predicate, self.prefixes),
            object=RdfValue.from_node(obj, self.prefixes),
            graph=RdfValue.from_node(graph, self.prefixes),
            category=self._category(predicate),
        )

    def _category(self, predicate: Node) -> ChangeCategory:
        if predicate == RDF.type:
            return "type"
        if predicate in (SKOS.prefLabel, SKOS.altLabel):
            return "label"
        if predicate == SKOS.definition:
            return "definition"
        if predicate in (RDFS.subClassOf, RDFS.subPropertyOf):
            return "hierarchy"
        if predicate in (RDFS.domain, RDFS.range):
            return "domain_range"
        if predicate in (self.status_predicate, OWL.deprecated, DCTERMS.isReplacedBy):
            return "status"
        if predicate in (DCTERMS.source, DCTERMS.creator, DCTERMS.created, DCTERMS.modified):
            return "evidence"
        if isinstance(predicate, URIRef):
            return "relation"
        return "other"

    @staticmethod
    def _quad_key(quad: CanonicalQuad) -> tuple[str, str, str, str]:
        return tuple(str(node) for node in quad)  # type: ignore[return-value]

    @staticmethod
    def _category_order(category: ChangeCategory) -> int:
        return (
            "type",
            "label",
            "definition",
            "hierarchy",
            "domain_range",
            "status",
            "evidence",
            "relation",
            "other",
        ).index(category)

    def _values(self, resources: set[URIRef]) -> tuple[RdfValue, ...]:
        return tuple(
            RdfValue.from_node(resource, self.prefixes) for resource in sorted(resources, key=str)
        )


class ProposalReviewService:
    """Build one deterministic reviewer view from current Git and RDF state."""

    def __init__(self, store: FilesystemRdfStore, workspace: GitWorkspaceService) -> None:
        if store.knowledge_root != workspace.knowledge_root:
            raise ValueError("review and workspace require the same knowledge root")
        self.store = store
        self.workspace = workspace

    def review(self, *, base_ref: str | None = None) -> ProposalReview:
        status = self.workspace.require_proposal_branch()
        selected_base = base_ref or status.base_branch
        base_dataset = self._dataset_at_revision(selected_base)
        head_dataset = self.store.load()
        diff = SemanticDiffService(self.store.prefixes).compare(
            base_dataset,
            head_dataset,
            base_ref=selected_base,
            head_ref=status.branch or "HEAD",
        )
        validation = ValidationService(self.store).validate_dataset(
            head_dataset, baseline=base_dataset
        )
        impact_service = ImpactService(
            head_dataset,
            self.store.prefixes,
            store=self.store,
        )
        impact: dict[str, dict[str, object]] = {}
        for change in diff.changes:
            impact[change.resource.value] = impact_service.analyze(change.resource.value).to_dict()
        evidence = tuple(
            quad for quad in diff.added_quads if quad.predicate.value == str(DCTERMS.source)
        )
        return ProposalReview(
            diff=diff,
            validation=validation,
            impact=impact,
            evidence=evidence,
            ready_to_commit=validation.conforms and bool(diff.added_quads or diff.removed_quads),
        )

    def _dataset_at_revision(self, revision: str) -> Dataset:
        """Load a published base, treating a valid pre-RDF commit as an empty Dataset."""

        if not revision or revision.startswith("-") or "\x00" in revision:
            raise GitWorkspaceError("git.invalid_revision", "The base revision is invalid.")
        try:
            revision_exists = subprocess.run(
                ("git", "cat-file", "-e", f"{revision}^{{commit}}"),
                cwd=self.workspace.repository_root,
                check=False,
                capture_output=True,
                timeout=self.workspace.timeout_seconds,
            )
            tree = subprocess.run(
                ("git", "ls-tree", "-z", "--name-only", revision, "--", "knowledge", "config"),
                cwd=self.workspace.repository_root,
                check=False,
                capture_output=True,
                timeout=self.workspace.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise GitWorkspaceError("git.archive_failed", str(error)) from error
        if revision_exists.returncode != 0 or tree.returncode != 0:
            raise GitWorkspaceError(
                "git.base_unavailable",
                "The selected Git base revision is not available.",
            )
        roots = {item.decode("utf-8") for item in tree.stdout.split(b"\0") if item}
        if "knowledge" not in roots:
            return Dataset()
        if "config" not in roots:
            raise GitWorkspaceError(
                "git.base_unavailable",
                "The published RDF base contains knowledge/ but no config/ directory.",
            )
        try:
            completed = subprocess.run(
                ("git", "archive", "--format=tar", revision, "knowledge", "config"),
                cwd=self.workspace.repository_root,
                check=False,
                capture_output=True,
                timeout=self.workspace.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise GitWorkspaceError("git.archive_failed", str(error)) from error
        if completed.returncode != 0:
            raise GitWorkspaceError(
                "git.base_unavailable",
                "The published RDF base is not available at the selected revision.",
            )
        temporary = tempfile.TemporaryDirectory(prefix="eow-review-")
        root = Path(temporary.name)
        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
            archive.extractall(root, filter="data")
        store = FilesystemRdfStore(root / "knowledge", root / "config/namespace.yaml")
        # Keep the TemporaryDirectory alive for the store's complete use in review().
        store._proposal_review_temporary = temporary  # type: ignore[attr-defined]
        return store.load()

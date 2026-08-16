"""Deterministic SHACL and governance validation for repository RDF."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from pyshacl import validate as pyshacl_validate
from pyshacl.errors import ReportableRuntimeError
from rdflib import BNode, Dataset, Graph, Literal, Namespace, URIRef
from rdflib.compare import to_canonical_graph
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SH, SKOS, XSD
from rdflib.term import Node

from ontology_core.store import FilesystemRdfStore, RdfLoadError

TERM_TYPES = frozenset(
    {
        OWL.Class,
        OWL.ObjectProperty,
        OWL.DatatypeProperty,
        OWL.AnnotationProperty,
        SKOS.Concept,
    }
)
PROPERTY_TYPES = frozenset({OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty})
COLLISION_TYPES = TERM_TYPES | {OWL.Ontology, OWL.NamedIndividual, SH.NodeShape}
STRUCTURAL_RESOURCE_TYPES = TERM_TYPES | {
    OWL.Ontology,
    RDF.List,
    RDF.Property,
    RDF.Statement,
    RDFS.Class,
    RDFS.Datatype,
    SH.NodeShape,
    SH.PropertyShape,
}
GENERIC_PROPERTY_NAMES = frozenset(
    {"associatedwith", "contains", "has", "related", "relatedto", "relation", "uses"}
)


class ValidationSeverity(StrEnum):
    """Portable severity used by API, CLI, MCP and CI adapters."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationSource(StrEnum):
    """Pipeline stage that produced an issue."""

    PARSER = "parser"
    SHACL = "shacl"
    LINT = "lint"


class ValidationResourceType(StrEnum):
    """RDF node kind retained for a report focus resource."""

    IRI = "iri"
    BNODE = "bnode"


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic validation finding."""

    source: ValidationSource
    rule_id: str
    severity: ValidationSeverity
    message: str
    resource: str | None = None
    resource_type: ValidationResourceType | None = None
    path: str | None = None
    graph: str | None = None
    details: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.resource is not None and self.resource_type is None:
            object.__setattr__(self, "resource_type", ValidationResourceType.IRI)
        if self.resource is None and self.resource_type is not None:
            raise ValueError("resource_type requires resource")

    def sort_key(self) -> tuple[str, ...]:
        return (
            self.severity.value,
            self.source.value,
            self.rule_id,
            self.resource_type.value if self.resource_type is not None else "",
            self.resource or "",
            self.path or "",
            self.graph or "",
            self.message,
            json.dumps(dict(self.details), ensure_ascii=False, sort_keys=True),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "details": dict(self.details),
            "graph": self.graph,
            "message": self.message,
            "path": self.path,
            "resource": self.resource,
            "resource_type": (self.resource_type.value if self.resource_type is not None else None),
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "source": self.source.value,
        }


@dataclass(frozen=True)
class ValidationReport:
    """Common parser, SHACL and lint report with stable JSON and RDF forms."""

    issues: tuple[ValidationIssue, ...]

    @classmethod
    def from_issues(cls, issues: Iterable[ValidationIssue]) -> ValidationReport:
        return cls(tuple(sorted(set(issues), key=ValidationIssue.sort_key)))

    @property
    def conforms(self) -> bool:
        return all(issue.severity is not ValidationSeverity.ERROR for issue in self.issues)

    def to_dict(self) -> dict[str, object]:
        counts = {
            severity.value: sum(issue.severity is severity for issue in self.issues)
            for severity in ValidationSeverity
        }
        return {
            "conforms": self.conforms,
            "counts": counts,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def to_rdf(self) -> str:
        """Return deterministic N-Triples using SHACL report vocabulary."""

        report_namespace = Namespace("urn:eow:validation:report:")
        vocabulary = Namespace("urn:eow:validation:vocabulary:")
        report_digest = hashlib.sha256(self.to_json().encode()).hexdigest()
        report_iri = report_namespace[f"report-{report_digest}"]
        graph = Graph()
        graph.add((report_iri, RDF.type, SH.ValidationReport))
        graph.add((report_iri, SH.conforms, Literal(self.conforms)))

        severity_iris = {
            ValidationSeverity.ERROR: SH.Violation,
            ValidationSeverity.WARNING: SH.Warning,
            ValidationSeverity.INFO: SH.Info,
        }
        for issue in self.issues:
            payload = json.dumps(issue.to_dict(), ensure_ascii=False, sort_keys=True)
            issue_digest = hashlib.sha256(payload.encode()).hexdigest()
            result_iri = report_namespace[f"result-{issue_digest}"]
            graph.add((report_iri, SH.result, result_iri))
            graph.add((result_iri, RDF.type, SH.ValidationResult))
            graph.add((result_iri, SH.resultSeverity, severity_iris[issue.severity]))
            graph.add((result_iri, SH.resultMessage, Literal(issue.message, lang="es")))
            graph.add((result_iri, vocabulary.ruleId, Literal(issue.rule_id)))
            graph.add((result_iri, vocabulary.source, Literal(issue.source.value)))
            if issue.resource is not None:
                if issue.resource_type is ValidationResourceType.BNODE:
                    focus_digest = hashlib.sha256(issue.resource.encode()).hexdigest()
                    focus_node: Node = BNode(f"focus-{focus_digest}")
                else:
                    focus_node = URIRef(issue.resource)
                graph.add((result_iri, SH.focusNode, focus_node))
            if issue.path is not None:
                graph.add((result_iri, vocabulary.file, Literal(issue.path)))
            if issue.graph is not None:
                graph.add((result_iri, vocabulary.graph, URIRef(issue.graph)))
            if issue.details:
                graph.add(
                    (
                        result_iri,
                        vocabulary.details,
                        Literal(
                            json.dumps(dict(issue.details), ensure_ascii=False, sort_keys=True)
                        ),
                    )
                )
        serialized = graph.serialize(format="nt")
        return "\n".join(sorted(line for line in serialized.splitlines() if line)) + "\n"


@dataclass(frozen=True)
class ValidationContext:
    """Repository facts needed by deterministic governance rules."""

    base: str
    graph_modules: Mapping[str, str]
    module_iris: frozenset[str]
    locations: Mapping[str, tuple[str, ...]]

    def location_for(self, resource: Node | None) -> str | None:
        if resource is None:
            return None
        locations = self.locations.get(str(resource), ())
        return locations[0] if locations else None


def _union_graph(dataset: Dataset) -> Graph:
    graph = Graph()
    for subject, predicate, obj, _ in dataset.quads((None, None, None, None)):
        graph.add((subject, predicate, obj))
    return graph


def _canonical_union_graph(dataset: Dataset) -> Graph:
    graph = Graph()
    for triple in to_canonical_graph(_union_graph(dataset)):
        graph.add(triple)
    return graph


def _term_subjects(graph: Graph) -> set[URIRef]:
    return {
        subject
        for term_type in TERM_TYPES
        for subject in graph.subjects(RDF.type, term_type)
        if isinstance(subject, URIRef)
    }


def _normalized_label(value: Literal) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _local_name(iri: URIRef) -> str:
    value = str(iri).rstrip("/#")
    return re.split(r"[/#]", value)[-1]


def _is_enterprise_instance_type(resource_type: Node) -> bool:
    """Classify explicit instance types without reasoning or remote lookups."""

    if resource_type == OWL.NamedIndividual:
        return True
    if not isinstance(resource_type, URIRef) or resource_type in STRUCTURAL_RESOURCE_TYPES:
        return False
    value = str(resource_type)
    return not value.startswith((str(RDF), str(RDFS), str(OWL), str(SH)))


class SemanticLinter:
    """Repository-aware rules that are not naturally expressed in SHACL Core."""

    def lint(
        self,
        dataset: Dataset,
        context: ValidationContext,
        baseline: Dataset | None = None,
    ) -> tuple[ValidationIssue, ...]:
        issues = [
            *self.lint_namespaces(dataset, context),
            *self.lint_module_ownership(dataset, context),
            *self.lint_lexical_duplicates(dataset, context),
            *self.lint_deprecations(dataset, context, baseline),
            *self.lint_dangerous_properties(dataset, context),
            *self.lint_import_cycles(dataset, context),
            *self.lint_proposal_graph_separation(dataset, context),
        ]
        return tuple(sorted(set(issues), key=ValidationIssue.sort_key))

    def lint_namespaces(
        self, dataset: Dataset, context: ValidationContext
    ) -> tuple[ValidationIssue, ...]:
        graph = _union_graph(dataset)
        canonical_graph = _canonical_union_graph(dataset)
        graph_iris = {
            graph_item.identifier
            for graph_item in dataset.graphs()
            if len(graph_item) and isinstance(graph_item.identifier, URIRef)
        }
        defined = {
            subject for subject in graph.subjects() if isinstance(subject, URIRef)
        } | graph_iris
        referenced = {
            node
            for subject, predicate, obj, graph_name in dataset.quads((None, None, None, None))
            for node in (subject, predicate, obj, graph_name)
            if isinstance(node, URIRef) and str(node).startswith(context.base)
        }
        issues: list[ValidationIssue] = []
        for iri in sorted(referenced, key=str):
            value = str(iri)
            parsed = urlsplit(value)
            relative = value.removeprefix(context.base)
            if (
                not relative
                or parsed.query
                or any(char.isspace() or ord(char) < 32 for char in value)
            ):
                issues.append(
                    self._issue(
                        "namespace.invalid_internal_iri",
                        ValidationSeverity.ERROR,
                        f"La IRI interna no cumple la sintaxis estable: {value}",
                        iri,
                        context,
                    )
                )
            if iri not in defined:
                issues.append(
                    self._issue(
                        "namespace.dangling_internal_iri",
                        ValidationSeverity.ERROR,
                        f"La IRI interna referenciada no está definida: {value}",
                        iri,
                        context,
                    )
                )

        for subject in sorted(
            (term for term in _term_subjects(graph) if str(term).startswith(context.base)),
            key=str,
        ):
            kinds = {kind for kind in COLLISION_TYPES if (subject, RDF.type, kind) in graph}
            if len(kinds) > 1:
                issues.append(
                    self._issue(
                        "namespace.type_collision",
                        ValidationSeverity.ERROR,
                        "La IRI declara tipos de recurso incompatibles: "
                        + ", ".join(sorted(map(str, kinds))),
                        subject,
                        context,
                    )
                )
            local_name = _local_name(subject)
            if (subject, RDF.type, OWL.Class) in graph and not re.fullmatch(
                r"[A-Z][A-Za-z0-9]*", local_name
            ):
                issues.append(
                    self._issue(
                        "namespace.class_name",
                        ValidationSeverity.ERROR,
                        f"La clase interna debe usar PascalCase: {local_name}",
                        subject,
                        context,
                    )
                )
            if any(
                (subject, RDF.type, kind) in graph for kind in PROPERTY_TYPES
            ) and not re.fullmatch(r"[a-z][A-Za-z0-9]*", local_name):
                issues.append(
                    self._issue(
                        "namespace.property_name",
                        ValidationSeverity.ERROR,
                        f"La propiedad interna debe usar lowerCamelCase: {local_name}",
                        subject,
                        context,
                    )
                )

        individuals = {
            subject
            for subject, resource_type in graph.subject_objects(RDF.type)
            if isinstance(subject, URIRef)
            and str(subject).startswith(context.base)
            and _is_enterprise_instance_type(resource_type)
        }
        for individual in sorted(individuals, key=str):
            local_name = _local_name(individual)
            if not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", local_name):
                issues.append(
                    self._issue(
                        "namespace.individual_name",
                        ValidationSeverity.ERROR,
                        f"El individuo interno debe usar snake_case: {local_name}",
                        individual,
                        context,
                    )
                )

        enterprise_bnodes = {
            subject
            for subject, resource_type in canonical_graph.subject_objects(RDF.type)
            if isinstance(subject, BNode) and _is_enterprise_instance_type(resource_type)
        }
        for enterprise_bnode in sorted(enterprise_bnodes, key=str):
            issues.append(
                self._issue(
                    "namespace.enterprise_individual_bnode",
                    ValidationSeverity.ERROR,
                    "Un individuo empresarial relevante debe tener una IRI canónica.",
                    enterprise_bnode,
                    context,
                )
            )
        return tuple(issues)

    def lint_module_ownership(
        self, dataset: Dataset, context: ValidationContext
    ) -> tuple[ValidationIssue, ...]:
        graph = _union_graph(dataset)
        issues: list[ValidationIssue] = []
        terms = {term for term in _term_subjects(graph) if str(term).startswith(context.base)}
        for term in sorted(terms, key=str):
            owners = {
                owner
                for owner in graph.objects(term, DCTERMS.isPartOf)
                if isinstance(owner, URIRef)
            }
            if len(owners) != 1:
                issues.append(
                    self._issue(
                        "module.owner_count",
                        ValidationSeverity.ERROR,
                        "El término debe declarar exactamente un módulo responsable.",
                        term,
                        context,
                    )
                )
            elif str(next(iter(owners))) not in context.module_iris:
                issues.append(
                    self._issue(
                        "module.unknown_owner",
                        ValidationSeverity.ERROR,
                        "El módulo responsable no está definido en el dataset.",
                        term,
                        context,
                    )
                )

            definition_graphs = {
                str(graph_name)
                for _, _, term_type, graph_name in dataset.quads((term, RDF.type, None, None))
                if term_type in TERM_TYPES and str(graph_name) in context.graph_modules
            }
            if len(definition_graphs) > 1:
                issues.append(
                    self._issue(
                        "module.multiple_definitions",
                        ValidationSeverity.ERROR,
                        "El término está definido en más de un módulo: "
                        + ", ".join(
                            sorted(context.graph_modules[item] for item in definition_graphs)
                        ),
                        term,
                        context,
                        details=(("graphs", ",".join(sorted(definition_graphs))),),
                    )
                )
            if len(definition_graphs) == 1 and len(owners) == 1:
                graph_name = next(iter(definition_graphs))
                expected_owner = context.graph_modules[graph_name]
                actual_owner = str(next(iter(owners)))
                if actual_owner in context.module_iris and actual_owner != expected_owner:
                    issues.append(
                        self._issue(
                            "module.owner_graph_mismatch",
                            ValidationSeverity.ERROR,
                            "El ownership no coincide con el módulo que define el término.",
                            term,
                            context,
                            graph=graph_name,
                        )
                    )
        return tuple(issues)

    def lint_lexical_duplicates(
        self, dataset: Dataset, context: ValidationContext
    ) -> tuple[ValidationIssue, ...]:
        graph = _union_graph(dataset)
        index: dict[tuple[str, str], set[URIRef]] = {}
        for term in _term_subjects(graph):
            for predicate in (SKOS.prefLabel, SKOS.altLabel):
                for label in graph.objects(term, predicate):
                    if not isinstance(label, Literal):
                        continue
                    normalized = _normalized_label(label)
                    if normalized:
                        index.setdefault((label.language or "", normalized), set()).add(term)

        issues: list[ValidationIssue] = []
        for (language, normalized), terms in sorted(index.items()):
            if len(terms) < 2:
                continue
            candidates = ", ".join(sorted(map(str, terms)))
            for term in sorted(terms, key=str):
                issues.append(
                    self._issue(
                        "lexical.duplicate_label",
                        ValidationSeverity.WARNING,
                        "Etiqueta normalizada duplicada "
                        f"({language or 'sin idioma'}): {normalized}",
                        term,
                        context,
                        details=(("candidates", candidates), ("normalized", normalized)),
                    )
                )
        return tuple(issues)

    def lint_deprecations(
        self,
        dataset: Dataset,
        context: ValidationContext,
        baseline: Dataset | None,
    ) -> tuple[ValidationIssue, ...]:
        candidate = _union_graph(dataset)
        issues: list[ValidationIssue] = []
        for term in sorted(
            (term for term in _term_subjects(candidate) if str(term).startswith(context.base)),
            key=str,
        ):
            if (
                candidate.value(term, Namespace(context.base + "ontology/core#").status)
                == Literal("deprecated")
                and candidate.value(term, DCTERMS.description) is None
            ):
                issues.append(
                    self._issue(
                        "deprecation.missing_reason",
                        ValidationSeverity.ERROR,
                        "Un término deprecado debe conservar una explicación del motivo.",
                        term,
                        context,
                    )
                )
        if baseline is None:
            return tuple(issues)

        published = _union_graph(baseline)
        status = Namespace(context.base + "ontology/core#").status
        for term in sorted(
            (term for term in _term_subjects(published) if str(term).startswith(context.base)),
            key=str,
        ):
            if not any(candidate.triples((term, None, None))):
                issues.append(
                    self._issue(
                        "deprecation.published_term_removed",
                        ValidationSeverity.ERROR,
                        "Un término publicado no puede eliminarse; debe deprecarse.",
                        term,
                        context,
                    )
                )
                continue
            old_kinds = {kind for kind in TERM_TYPES if (term, RDF.type, kind) in published}
            new_kinds = {kind for kind in TERM_TYPES if (term, RDF.type, kind) in candidate}
            if old_kinds != new_kinds:
                issues.append(
                    self._issue(
                        "deprecation.published_type_changed",
                        ValidationSeverity.ERROR,
                        "No puede cambiarse el tipo RDF de un término publicado.",
                        term,
                        context,
                    )
                )
            if published.value(term, status) == Literal("deprecated") and candidate.value(
                term, status
            ) != Literal("deprecated"):
                issues.append(
                    self._issue(
                        "deprecation.iri_reused",
                        ValidationSeverity.ERROR,
                        "Una IRI deprecada no puede reactivarse ni reutilizarse.",
                        term,
                        context,
                    )
                )
        return tuple(issues)

    def lint_dangerous_properties(
        self, dataset: Dataset, context: ValidationContext
    ) -> tuple[ValidationIssue, ...]:
        graph = _union_graph(dataset)
        issues: list[ValidationIssue] = []
        properties = {
            subject
            for property_type in PROPERTY_TYPES
            for subject in graph.subjects(RDF.type, property_type)
            if isinstance(subject, URIRef)
        }
        used_predicates = {
            predicate
            for _, predicate, _ in graph
            if isinstance(predicate, URIRef) and str(predicate).startswith(context.base)
        }
        for property_iri in sorted(properties | used_predicates, key=str):
            normalized = re.sub(r"[^a-z0-9]", "", _local_name(property_iri).casefold())
            if normalized == "relatedto":
                rule_id = "property.related_to"
            elif normalized in GENERIC_PROPERTY_NAMES:
                rule_id = "property.generic_name"
            else:
                continue
            if rule_id:
                issues.append(
                    self._issue(
                        rule_id,
                        ValidationSeverity.WARNING,
                        "La propiedad tiene un nombre excesivamente genérico: "
                        f"{_local_name(property_iri)}",
                        property_iri,
                        context,
                    )
                )
        for subject, _, obj in sorted(
            graph.triples((None, OWL.sameAs, None)), key=lambda item: tuple(map(str, item))
        ):
            resource = subject if isinstance(subject, URIRef) else None
            issues.append(
                self._issue(
                    "property.owl_same_as",
                    ValidationSeverity.WARNING,
                    "owl:sameAs requiere revisión explícita y no puede agregarse automáticamente.",
                    resource,
                    context,
                    details=(("object", str(obj)),),
                )
            )
        return tuple(issues)

    def lint_import_cycles(
        self, dataset: Dataset, context: ValidationContext
    ) -> tuple[ValidationIssue, ...]:
        graph = _union_graph(dataset)
        modules = {
            subject
            for subject in graph.subjects(RDF.type, OWL.Ontology)
            if isinstance(subject, URIRef)
        }
        edges = {
            module: sorted(
                {
                    imported
                    for imported in graph.objects(module, OWL.imports)
                    if isinstance(imported, URIRef) and imported in modules
                },
                key=str,
            )
            for module in modules
        }
        cycles: set[tuple[str, ...]] = set()
        visited: set[URIRef] = set()
        active: list[URIRef] = []

        def visit(module: URIRef) -> None:
            if module in active:
                start = active.index(module)
                raw_cycle = [str(item) for item in active[start:]]
                rotations = [
                    tuple(raw_cycle[index:] + raw_cycle[:index]) for index in range(len(raw_cycle))
                ]
                cycles.add(min(rotations))
                return
            if module in visited:
                return
            active.append(module)
            for imported in edges.get(module, []):
                visit(imported)
            active.pop()
            visited.add(module)

        for module in sorted(modules, key=str):
            visit(module)

        issues: list[ValidationIssue] = []
        for cycle in sorted(cycles):
            chain = " -> ".join((*cycle, cycle[0]))
            resource = URIRef(cycle[0])
            issues.append(
                self._issue(
                    "imports.cycle",
                    ValidationSeverity.ERROR,
                    f"Los imports contienen un ciclo: {chain}",
                    resource,
                    context,
                    details=(("chain", chain),),
                )
            )
        return tuple(issues)

    def lint_proposal_graph_separation(
        self, dataset: Dataset, context: ValidationContext
    ) -> tuple[ValidationIssue, ...]:
        """Reject proposed assertions materialized in graphs declared published."""

        status = URIRef(f"{context.base}ontology/core#status")
        published_graphs = {
            graph_iri
            for graph_iri, _, _, _ in dataset.quads((None, status, Literal("published"), None))
            if isinstance(graph_iri, URIRef)
        }
        proposed_assertions = {
            assertion
            for assertion, _, _, _ in dataset.quads((None, status, Literal("proposed"), None))
            if self._dataset_has(dataset, assertion, RDF.type, RDF.Statement)
        }
        issues: list[ValidationIssue] = []
        for assertion in sorted(proposed_assertions, key=str):
            subjects = self._dataset_objects(dataset, assertion, RDF.subject)
            predicates = self._dataset_objects(dataset, assertion, RDF.predicate)
            objects = self._dataset_objects(dataset, assertion, RDF.object)
            if len(subjects) != 1 or len(predicates) != 1 or len(objects) != 1:
                continue
            triple = (next(iter(subjects)), next(iter(predicates)), next(iter(objects)))
            for graph_iri in sorted(published_graphs, key=str):
                if triple not in dataset.graph(graph_iri):
                    continue
                issues.append(
                    self._issue(
                        "proposal.relation_in_published_graph",
                        ValidationSeverity.ERROR,
                        "Una relación propuesta no puede materializarse en un graph publicado.",
                        assertion if isinstance(assertion, (URIRef, BNode)) else None,
                        context,
                        graph=str(graph_iri),
                        details=(
                            ("subject", str(triple[0])),
                            ("predicate", str(triple[1])),
                            ("object", str(triple[2])),
                        ),
                    )
                )
        return tuple(issues)

    @staticmethod
    def _dataset_has(dataset: Dataset, subject: Node, predicate: Node, obj: Node) -> bool:
        return any(dataset.quads((subject, predicate, obj, None)))

    @staticmethod
    def _dataset_objects(dataset: Dataset, subject: Node, predicate: Node) -> set[Node]:
        return {obj for _, _, obj, _ in dataset.quads((subject, predicate, None, None))}

    @staticmethod
    def _issue(
        rule_id: str,
        severity: ValidationSeverity,
        message: str,
        resource: URIRef | BNode | None,
        context: ValidationContext,
        *,
        graph: str | None = None,
        details: tuple[tuple[str, str], ...] = (),
    ) -> ValidationIssue:
        return ValidationIssue(
            source=ValidationSource.LINT,
            rule_id=rule_id,
            severity=severity,
            message=message,
            resource=str(resource) if resource is not None else None,
            resource_type=(
                ValidationResourceType.BNODE
                if isinstance(resource, BNode)
                else ValidationResourceType.IRI
                if isinstance(resource, URIRef)
                else None
            ),
            path=context.location_for(resource),
            graph=graph,
            details=details,
        )


class ValidationService:
    """Parse, execute SHACL Core, lint and return one deterministic report."""

    def __init__(self, store: FilesystemRdfStore) -> None:
        self.store = store
        self.linter = SemanticLinter()

    def validate_repository(self, baseline: Dataset | None = None) -> ValidationReport:
        try:
            dataset = self.store.load()
            shapes = self._load_shapes()
            context = self._build_context(dataset)
        except RdfLoadError as error:
            return ValidationReport.from_issues([self._parse_issue(error)])
        return self.validate_dataset(dataset, shapes=shapes, context=context, baseline=baseline)

    def validate_dataset(
        self,
        dataset: Dataset,
        *,
        shapes: Graph | None = None,
        context: ValidationContext | None = None,
        baseline: Dataset | None = None,
    ) -> ValidationReport:
        effective_context = context or self._build_context(dataset)
        effective_shapes = shapes if shapes is not None else self._load_shapes()
        missing_shapes = self._missing_governance_shapes(effective_shapes, effective_context)
        if missing_shapes:
            return ValidationReport.from_issues(
                [
                    ValidationIssue(
                        source=ValidationSource.SHACL,
                        rule_id="shacl.missing_governance",
                        severity=ValidationSeverity.ERROR,
                        message="Faltan shapes globales obligatorias de gobernanza.",
                        path="shapes/governance.ttl",
                        details=(("missing", ",".join(missing_shapes)),),
                    )
                ]
            )
        original_quads = set(dataset.quads((None, None, None, None)))
        issues = [
            *self._run_shacl(dataset, effective_shapes, effective_context),
            *self.linter.lint(dataset, effective_context, baseline),
        ]
        if set(dataset.quads((None, None, None, None))) != original_quads:
            issues.append(
                ValidationIssue(
                    source=ValidationSource.LINT,
                    rule_id="validation.dataset_mutated",
                    severity=ValidationSeverity.ERROR,
                    message="La validación modificó el dataset de entrada.",
                )
            )
        return ValidationReport.from_issues(issues)

    @staticmethod
    def _missing_governance_shapes(shapes: Graph, context: ValidationContext) -> tuple[str, ...]:
        governance = Namespace(context.base + "shape/governance/")
        term_shape = governance.TermShape
        property_shape = governance.PropertyShape
        missing: list[str] = []

        def require(condition: bool, identifier: str) -> None:
            if not condition:
                missing.append(identifier)

        def exact_objects(subject: Node, predicate: URIRef, expected: set[Node]) -> bool:
            return set(shapes.objects(subject, predicate)) == expected

        def exact_integer(subject: Node, predicate: URIRef, expected: int) -> bool:
            return exact_objects(subject, predicate, {Literal(expected)})

        def is_active_violation_component(subject: Node) -> bool:
            deactivated = set(shapes.objects(subject, SH.deactivated))
            severities = set(shapes.objects(subject, SH.severity))
            return deactivated <= {Literal(False)} and severities <= {SH.Violation}

        def rdf_list(head: Node | None) -> tuple[Node, ...]:
            values: list[Node] = []
            visited: set[Node] = set()
            current = head
            while current is not None and current != RDF.nil and current not in visited:
                visited.add(current)
                first_values = tuple(shapes.objects(current, RDF.first))
                rest_values = tuple(shapes.objects(current, RDF.rest))
                if len(first_values) != 1 or len(rest_values) != 1:
                    return ()
                values.append(first_values[0])
                current = rest_values[0]
            return tuple(values) if current == RDF.nil else ()

        def property_nodes(shape: Node, path: URIRef) -> tuple[Node, ...]:
            return tuple(
                node
                for node in shapes.objects(shape, SH.property)
                if exact_objects(node, SH.path, {path})
            )

        def single_logical_list(shape: Node, predicate: URIRef) -> tuple[Node, ...]:
            heads = tuple(shapes.objects(shape, predicate))
            return rdf_list(heads[0]) if len(heads) == 1 else ()

        def exact_direct_paths(shape: Node, paths: set[URIRef]) -> bool:
            properties = tuple(shapes.objects(shape, SH.property))
            path_values = [tuple(shapes.objects(node, SH.path)) for node in properties]
            actual_paths = [values[0] for values in path_values if len(values) == 1]
            return len(properties) == len(paths) and set(actual_paths) == paths

        def nonempty_text(node: Node) -> bool:
            return exact_integer(node, SH.minLength, 1) and exact_objects(
                node, SH.pattern, {Literal(r"\S")}
            )

        def direct_text_contract(shape: Node, path: URIRef) -> bool:
            nodes = property_nodes(shape, path)
            return len(nodes) == 1 and (
                is_active_violation_component(nodes[0])
                and exact_integer(nodes[0], SH.minCount, 1)
                and nonempty_text(nodes[0])
            )

        def reachable_blank_nodes(*roots: URIRef) -> frozenset[Node]:
            pending: list[Node] = list(roots)
            visited: set[Node] = set()
            while pending:
                subject = pending.pop()
                if subject in visited:
                    continue
                visited.add(subject)
                pending.extend(
                    obj
                    for obj in shapes.objects(subject)
                    if isinstance(obj, BNode) and obj not in visited
                )
            return frozenset(visited)

        require((term_shape, RDF.type, SH.NodeShape) in shapes, "TermShape.type")
        require(
            is_active_violation_component(term_shape),
            "TermShape.active",
        )
        term_targets = set(shapes.objects(term_shape, SH.targetClass))
        require(term_targets == set(TERM_TYPES), "TermShape.targetClasses")
        require(
            exact_direct_paths(
                term_shape,
                {
                    SKOS.prefLabel,
                    SKOS.definition,
                    DCTERMS.isPartOf,
                    Namespace(context.base + "ontology/core#").status,
                    DCTERMS.source,
                    DCTERMS.creator,
                },
            ),
            "TermShape.properties",
        )

        label_nodes = property_nodes(term_shape, SKOS.prefLabel)
        label_node = label_nodes[0] if len(label_nodes) == 1 else None
        label_qualified_values = (
            tuple(shapes.objects(label_node, SH.qualifiedValueShape))
            if label_node is not None
            else ()
        )
        label_qualified = label_qualified_values[0] if len(label_qualified_values) == 1 else None
        label_languages = (
            single_logical_list(label_qualified, SH.languageIn)
            if label_qualified is not None
            else ()
        )
        label_contract = (
            label_node is not None
            and label_qualified is not None
            and is_active_violation_component(label_node)
            and is_active_violation_component(label_qualified)
            and exact_integer(label_node, SH.minCount, 1)
            and exact_objects(label_node, SH.uniqueLang, {Literal(True)})
            and exact_integer(label_node, SH.qualifiedMinCount, 1)
            and label_languages == (Literal("es"),)
            and nonempty_text(label_qualified)
        )
        require(label_contract, "TermShape.property:prefLabel")

        definition_nodes = property_nodes(term_shape, SKOS.definition)
        definition_node = definition_nodes[0] if len(definition_nodes) == 1 else None
        definition_qualified_values = (
            tuple(shapes.objects(definition_node, SH.qualifiedValueShape))
            if definition_node is not None
            else ()
        )
        definition_qualified = (
            definition_qualified_values[0] if len(definition_qualified_values) == 1 else None
        )
        definition_languages = (
            single_logical_list(definition_qualified, SH.languageIn)
            if definition_qualified is not None
            else ()
        )
        definition_contract = (
            definition_node is not None
            and definition_qualified is not None
            and is_active_violation_component(definition_node)
            and is_active_violation_component(definition_qualified)
            and exact_integer(definition_node, SH.minCount, 1)
            and exact_integer(definition_node, SH.qualifiedMinCount, 1)
            and definition_languages == (Literal("es"),)
            and nonempty_text(definition_qualified)
        )
        require(definition_contract, "TermShape.property:definition")

        module_nodes = property_nodes(term_shape, DCTERMS.isPartOf)
        module_contract = len(module_nodes) == 1 and (
            is_active_violation_component(module_nodes[0])
            and exact_integer(module_nodes[0], SH.minCount, 1)
            and exact_integer(module_nodes[0], SH.maxCount, 1)
            and exact_objects(module_nodes[0], SH.nodeKind, {SH.IRI})
        )
        require(module_contract, "TermShape.property:module")

        status_path = Namespace(context.base + "ontology/core#").status
        status_nodes = property_nodes(term_shape, status_path)
        status_node = status_nodes[0] if len(status_nodes) == 1 else None
        status_values = (
            single_logical_list(status_node, SH["in"]) if status_node is not None else ()
        )
        status_contract = (
            status_node is not None
            and is_active_violation_component(status_node)
            and exact_integer(status_node, SH.minCount, 1)
            and exact_integer(status_node, SH.maxCount, 1)
            and len(status_values) == 3
            and set(status_values)
            == {Literal("proposed"), Literal("active"), Literal("deprecated")}
        )
        require(status_contract, "TermShape.property:status")
        require(direct_text_contract(term_shape, DCTERMS.source), "TermShape.property:evidence")
        require(direct_text_contract(term_shape, DCTERMS.creator), "TermShape.property:author")

        date_branches = single_logical_list(term_shape, SH["or"])
        date_paths: set[Node] = set()
        date_contract = len(date_branches) == 2
        for branch in date_branches:
            properties = tuple(shapes.objects(branch, SH.property))
            date_contract = date_contract and is_active_violation_component(branch)
            if len(properties) != 1:
                date_contract = False
                continue
            date_node = properties[0]
            date_path_values = tuple(shapes.objects(date_node, SH.path))
            if len(date_path_values) == 1:
                date_paths.add(date_path_values[0])
            else:
                date_contract = False
            date_contract = date_contract and (
                is_active_violation_component(date_node)
                and exact_integer(date_node, SH.minCount, 1)
                and exact_objects(date_node, SH.datatype, {XSD.date})
            )
        require(
            date_contract and date_paths == {DCTERMS.created, DCTERMS.modified},
            "TermShape.logical:date",
        )

        require((property_shape, RDF.type, SH.NodeShape) in shapes, "PropertyShape.type")
        require(
            is_active_violation_component(property_shape),
            "PropertyShape.active",
        )
        property_targets = set(shapes.objects(property_shape, SH.targetClass))
        require(property_targets == set(PROPERTY_TYPES), "PropertyShape.targetClasses")
        require(
            exact_direct_paths(property_shape, {SKOS.scopeNote, SKOS.example}),
            "PropertyShape.properties",
        )
        require(
            direct_text_contract(property_shape, SKOS.scopeNote),
            "PropertyShape.property:direction",
        )
        require(
            direct_text_contract(property_shape, SKOS.example),
            "PropertyShape.property:example",
        )

        domain_range_branches = single_logical_list(property_shape, SH["or"])
        domain_range_contract = len(domain_range_branches) == 2
        domain_range_branch_count = 0
        justification_branch_count = 0
        for branch in domain_range_branches:
            domain_range_contract = domain_range_contract and is_active_violation_component(branch)
            and_branches = single_logical_list(branch, SH["and"])
            direct_properties = tuple(shapes.objects(branch, SH.property))
            if and_branches:
                domain_range_branch_count += 1
                component_paths: set[Node] = set()
                branch_contract = len(and_branches) == 2 and not direct_properties
                for component in and_branches:
                    properties = tuple(shapes.objects(component, SH.property))
                    branch_contract = branch_contract and is_active_violation_component(component)
                    if len(properties) != 1:
                        branch_contract = False
                        continue
                    property_node = properties[0]
                    component_path_values = tuple(shapes.objects(property_node, SH.path))
                    if len(component_path_values) == 1:
                        component_paths.add(component_path_values[0])
                    else:
                        branch_contract = False
                    branch_contract = branch_contract and (
                        is_active_violation_component(property_node)
                        and exact_integer(property_node, SH.minCount, 1)
                    )
                domain_range_contract = (
                    domain_range_contract
                    and branch_contract
                    and (component_paths == {RDFS.domain, RDFS.range})
                )
            elif direct_properties:
                justification_branch_count += 1
                domain_range_contract = domain_range_contract and (
                    exact_direct_paths(branch, {DCTERMS.description})
                    and direct_text_contract(branch, DCTERMS.description)
                )
            else:
                domain_range_contract = False
        require(
            domain_range_contract
            and domain_range_branch_count == 1
            and justification_branch_count == 1,
            "PropertyShape.logical:domain-range-or-justification",
        )

        reachable = reachable_blank_nodes(term_shape, property_shape)
        require(
            all(is_active_violation_component(node) for node in reachable),
            "GovernanceShape.components:active-violations",
        )
        return tuple(sorted(missing))

    def _load_shapes(self) -> Graph:
        return self.store.load_shape_catalog().graph

    def _build_context(self, dataset: Dataset) -> ValidationContext:
        base = self.store.namespace_configuration.base
        vocabulary = Namespace(base + "ontology/core#")
        graph = _union_graph(dataset)
        graph_modules = {
            str(graph_iri): str(module)
            for module in graph.subjects(RDF.type, vocabulary.OntologyModule)
            for graph_iri in graph.objects(module, vocabulary.graph)
            if isinstance(module, URIRef) and isinstance(graph_iri, URIRef)
        }
        module_iris = frozenset(
            str(module)
            for module in graph.subjects(RDF.type, vocabulary.OntologyModule)
            if isinstance(module, URIRef)
        )
        locations: dict[str, set[str]] = {}
        paths = [self.store.manifest_path]
        for module in self.store.discover_modules():
            paths.extend(self.store.discover_module_files(module))
        paths.extend(self.store.discover_source_files())
        for path in sorted(set(paths)):
            relative = path.relative_to(self.store.knowledge_root).as_posix()
            parsed: Graph | Dataset
            if path.suffix.lower() == ".trig":
                parsed_dataset = Dataset()
                self.store._parse_trig_into(parsed_dataset, path)
                parsed = parsed_dataset
                subjects = {
                    subject
                    for subject, _, _, _ in parsed.quads((None, None, None, None))
                    if isinstance(subject, URIRef)
                }
            else:
                parsed = self.store._parse_turtle(path)
                subjects = {subject for subject in parsed.subjects() if isinstance(subject, URIRef)}
            for subject in subjects:
                locations.setdefault(str(subject), set()).add(relative)
        return ValidationContext(
            base=base,
            graph_modules=graph_modules,
            module_iris=module_iris,
            locations={key: tuple(sorted(value)) for key, value in locations.items()},
        )

    def _run_shacl(
        self, dataset: Dataset, shapes: Graph, context: ValidationContext
    ) -> tuple[ValidationIssue, ...]:
        data = self._shacl_data_graph(dataset, context)
        try:
            _, results_graph, _ = pyshacl_validate(
                data_graph=data,
                shacl_graph=shapes,
                inference="none",
                abort_on_first=False,
                allow_infos=True,
                allow_warnings=True,
                advanced=False,
                do_owl_imports=False,
                inplace=False,
            )
        except ReportableRuntimeError as error:
            return (
                ValidationIssue(
                    source=ValidationSource.SHACL,
                    rule_id="shacl.execution",
                    severity=ValidationSeverity.ERROR,
                    message=f"{type(error).__name__}: {error}",
                ),
            )
        if not isinstance(results_graph, Graph):
            return (
                ValidationIssue(
                    source=ValidationSource.SHACL,
                    rule_id="shacl.execution",
                    severity=ValidationSeverity.ERROR,
                    message=str(results_graph),
                ),
            )

        issues: list[ValidationIssue] = []
        severity_map = {
            SH.Violation: ValidationSeverity.ERROR,
            SH.Warning: ValidationSeverity.WARNING,
            SH.Info: ValidationSeverity.INFO,
        }
        for result in sorted(results_graph.subjects(RDF.type, SH.ValidationResult), key=str):
            focus = results_graph.value(result, SH.focusNode)
            result_path = results_graph.value(result, SH.resultPath)
            severity_node = results_graph.value(result, SH.resultSeverity)
            messages = sorted(map(str, results_graph.objects(result, SH.resultMessage)))
            message = messages[0] if messages else "Violación SHACL sin mensaje."
            issues.append(
                ValidationIssue(
                    source=ValidationSource.SHACL,
                    rule_id=self._shacl_rule_id(result_path, message),
                    severity=(
                        severity_map.get(severity_node, ValidationSeverity.ERROR)
                        if isinstance(severity_node, URIRef)
                        else ValidationSeverity.ERROR
                    ),
                    message=message,
                    resource=str(focus) if isinstance(focus, (URIRef, BNode)) else None,
                    resource_type=(
                        ValidationResourceType.BNODE
                        if isinstance(focus, BNode)
                        else ValidationResourceType.IRI
                        if isinstance(focus, URIRef)
                        else None
                    ),
                    path=context.location_for(focus),
                    details=(("result_path", str(result_path)),) if result_path is not None else (),
                )
            )
        return tuple(issues)

    @staticmethod
    def _shacl_data_graph(dataset: Dataset, context: ValidationContext) -> Graph:
        """Build a canonical validation view while scoping governance to local terms."""

        union = _union_graph(dataset)
        scoped = Graph()
        for subject, predicate, obj in union:
            is_ungoverned_term_declaration = (
                predicate == RDF.type
                and obj in TERM_TYPES
                and (
                    isinstance(subject, BNode)
                    or (isinstance(subject, URIRef) and not str(subject).startswith(context.base))
                )
            )
            if not is_ungoverned_term_declaration:
                scoped.add((subject, predicate, obj))
        canonical = Graph()
        for triple in to_canonical_graph(scoped):
            canonical.add(triple)
        return canonical

    @staticmethod
    def _shacl_rule_id(result_path: Node | None, message: str) -> str:
        if isinstance(result_path, URIRef):
            known_paths = {
                SKOS.prefLabel: "label",
                SKOS.definition: "definition",
                DCTERMS.isPartOf: "module",
                DCTERMS.source: "evidence",
                DCTERMS.creator: "author",
                SKOS.scopeNote: "property_direction",
                SKOS.example: "property_example",
            }
            if result_path in known_paths:
                return f"shacl.{known_paths[result_path]}"
            return f"shacl.{_local_name(result_path)}"
        if "fecha" in message.casefold():
            return "shacl.date"
        if "dominio" in message.casefold():
            return "shacl.property_domain_range"
        return "shacl.composite_constraint"

    def _parse_issue(self, error: RdfLoadError) -> ValidationIssue:
        try:
            relative = error.path.absolute().relative_to(self.store.knowledge_root).as_posix()
        except ValueError:
            relative = error.path.name
        detail = error.detail
        root_text = str(self.store.knowledge_root)
        root_uri = self.store.knowledge_root.as_uri()
        detail = detail.replace(root_uri, "file://<knowledge>")
        detail = detail.replace(root_text, "<knowledge>")
        if error.rule_id == "parser.path_escape":
            detail = "source resolves outside knowledge root"
        return ValidationIssue(
            source=ValidationSource.PARSER,
            rule_id=error.rule_id,
            severity=ValidationSeverity.ERROR,
            message=f"could not load RDF from {relative}: {detail}",
            path=relative,
        )

"""Deterministic read models and graph queries shared by future adapters."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast
from typing import Literal as TypingLiteral

from rdflib import BNode, Dataset, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS
from rdflib.term import IdentifiedNode, Node

from ontology_core.prefixes import PrefixResolver
from ontology_core.search_receipts import (
    SearchReceiptAuthority,
    normalize_search_query,
)
from ontology_core.store import ModuleDefinition

SH = URIRef("http://www.w3.org/ns/shacl#")
SH_TARGET_CLASS = URIRef(f"{SH}targetClass")
SH_TARGET_NODE = URIRef(f"{SH}targetNode")
SH_PATH = URIRef(f"{SH}path")
SH_NODE_SHAPE = URIRef(f"{SH}NodeShape")
DatasetQuad = tuple[Node, Node, Node, IdentifiedNode]
ResourceCategory = TypingLiteral[
    "class",
    "property",
    "individual",
    "concept",
    "shape",
    "module",
    "literal",
    "resource",
]
RelationshipKind = TypingLiteral[
    "subclass",
    "subproperty",
    "domain",
    "range",
    "import",
    "internal_object_property",
    "other",
]
PROPERTY_TYPES = frozenset((OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty))
PROVENANCE_PREDICATES = frozenset(
    (
        DCTERMS.source,
        DCTERMS.creator,
        DCTERMS.created,
        DCTERMS.modified,
        PROV.wasDerivedFrom,
        PROV.wasGeneratedBy,
        PROV.generatedAtTime,
        PROV.wasAssociatedWith,
    )
)


def _normalise(value: str) -> str:
    return normalize_search_query(value)


def _local_name(iri: str) -> str:
    return iri.rsplit("#", 1)[-1].rstrip("/").rsplit("/", 1)[-1]


def _node_key(node: Node) -> tuple[str, str, str, str]:
    if isinstance(node, URIRef):
        return ("iri", str(node), "", "")
    if isinstance(node, BNode):
        return ("bnode", str(node), "", "")
    if isinstance(node, Literal):
        return ("literal", str(node), str(node.datatype or ""), node.language or "")
    return (type(node).__name__, str(node), "", "")


def _identified(value: str | IdentifiedNode) -> IdentifiedNode:
    if type(value) is str:
        return URIRef(value)
    return cast(IdentifiedNode, value)


@dataclass(frozen=True)
class RdfValue:
    """JSON-safe RDF node representation that preserves blank nodes and literals."""

    kind: TypingLiteral["iri", "bnode", "literal"]
    value: str
    compact: str | None = None
    datatype: str | None = None
    language: str | None = None
    category: ResourceCategory | None = None
    module: str | None = None

    @classmethod
    def from_node(
        cls,
        node: Node,
        prefixes: PrefixResolver,
        *,
        category: ResourceCategory | None = None,
        module: str | None = None,
    ) -> RdfValue:
        if isinstance(node, URIRef):
            return cls(
                kind="iri",
                value=str(node),
                compact=prefixes.compact(node),
                category=category,
                module=module,
            )
        if isinstance(node, BNode):
            return cls(kind="bnode", value=str(node), category=category, module=module)
        if isinstance(node, Literal):
            return cls(
                kind="literal",
                value=str(node),
                datatype=str(node.datatype) if node.datatype else None,
                language=node.language,
                category=category,
            )
        raise TypeError(f"unsupported RDF node: {type(node).__name__}")

    def to_dict(self) -> dict[str, str]:
        result = {"kind": self.kind, "value": self.value}
        for key, value in (
            ("compact", self.compact),
            ("datatype", self.datatype),
            ("language", self.language),
            ("category", self.category),
            ("module", self.module),
        ):
            if value is not None:
                result[key] = value
        return result


@dataclass(frozen=True)
class QuadView:
    subject: RdfValue
    predicate: RdfValue
    object: RdfValue
    graph: RdfValue
    relationship_kind: RelationshipKind = "other"
    priority: int = 7
    status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject.to_dict(),
            "predicate": self.predicate.to_dict(),
            "object": self.object.to_dict(),
            "graph": self.graph.to_dict(),
            "relationship_kind": self.relationship_kind,
            "priority": self.priority,
            "status": self.status,
        }


@dataclass(frozen=True)
class SearchResult:
    iri: str
    compact_iri: str
    local_name: str
    label: str | None
    types: tuple[str, ...]
    modules: tuple[str, ...]
    matched_fields: tuple[str, ...]
    score: int

    def to_dict(self) -> dict[str, object]:
        return {
            "iri": self.iri,
            "compact_iri": self.compact_iri,
            "local_name": self.local_name,
            "label": self.label,
            "types": list(self.types),
            "modules": list(self.modules),
            "matched_fields": list(self.matched_fields),
            "score": self.score,
        }


@dataclass(frozen=True)
class SearchPage:
    items: tuple[SearchResult, ...]
    total: int
    offset: int
    limit: int
    search_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
            "has_next": self.offset + len(self.items) < self.total,
            "search_id": self.search_id,
        }


@dataclass(frozen=True)
class ResourceDescription:
    resource: RdfValue
    types: tuple[RdfValue, ...]
    labels: tuple[RdfValue, ...]
    definitions: tuple[RdfValue, ...]
    modules: tuple[RdfValue, ...]
    direct_modules: tuple[RdfValue, ...]
    status: tuple[RdfValue, ...]
    outgoing: tuple[QuadView, ...]
    incoming: tuple[QuadView, ...]
    superclasses: tuple[RdfValue, ...]
    subclasses: tuple[RdfValue, ...]
    domains: tuple[RdfValue, ...]
    ranges: tuple[RdfValue, ...]
    provenance: tuple[QuadView, ...]
    predicate_uses: tuple[QuadView, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "resource": self.resource.to_dict(),
            "types": [value.to_dict() for value in self.types],
            "labels": [value.to_dict() for value in self.labels],
            "definitions": [value.to_dict() for value in self.definitions],
            "modules": [value.to_dict() for value in self.modules],
            "direct_modules": [value.to_dict() for value in self.direct_modules],
            "status": [value.to_dict() for value in self.status],
            "outgoing": [quad.to_dict() for quad in self.outgoing],
            "incoming": [quad.to_dict() for quad in self.incoming],
            "superclasses": [value.to_dict() for value in self.superclasses],
            "subclasses": [value.to_dict() for value in self.subclasses],
            "domains": [value.to_dict() for value in self.domains],
            "ranges": [value.to_dict() for value in self.ranges],
            "provenance": [quad.to_dict() for quad in self.provenance],
            "predicate_uses": [quad.to_dict() for quad in self.predicate_uses],
        }


@dataclass(frozen=True)
class ModuleDescription:
    identifier: str
    ontology_iri: str
    graph_iri: str
    source_path: str
    imports: tuple[str, ...]
    labels: tuple[RdfValue, ...]
    definitions: tuple[RdfValue, ...]
    responsible: tuple[RdfValue, ...]
    status: tuple[RdfValue, ...]
    classes: tuple[RdfValue, ...]
    properties: tuple[RdfValue, ...]
    import_cycles: tuple[tuple[str, ...], ...]
    term_count: int
    competency_question_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.identifier,
            "ontology_iri": self.ontology_iri,
            "graph_iri": self.graph_iri,
            "source_path": self.source_path,
            "imports": list(self.imports),
            "labels": [value.to_dict() for value in self.labels],
            "definitions": [value.to_dict() for value in self.definitions],
            "responsible": [value.to_dict() for value in self.responsible],
            "status": [value.to_dict() for value in self.status],
            "classes": [value.to_dict() for value in self.classes],
            "properties": [value.to_dict() for value in self.properties],
            "import_cycles": [list(cycle) for cycle in self.import_cycles],
            "term_count": self.term_count,
            "competency_question_count": self.competency_question_count,
        }


@dataclass(frozen=True)
class ResourceCategoryCounts:
    classes: int
    properties: int
    concepts: int
    individuals: int

    def to_dict(self) -> dict[str, int]:
        return {
            "classes": self.classes,
            "properties": self.properties,
            "concepts": self.concepts,
            "individuals": self.individuals,
        }


@dataclass(frozen=True)
class NeighborhoodFilter:
    graph_iris: frozenset[str] = frozenset()
    predicates: frozenset[str] = frozenset()
    rdf_types: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NeighborhoodLimits:
    max_depth: int = 3
    max_nodes: int = 500
    max_edges: int = 1500

    def __post_init__(self) -> None:
        if not 0 <= self.max_depth <= 10:
            raise ValueError("max_depth must be between 0 and 10")
        if not 1 <= self.max_nodes <= 5000:
            raise ValueError("max_nodes must be between 1 and 5000")
        if not 0 <= self.max_edges <= 15000:
            raise ValueError("max_edges must be between 0 and 15000")


@dataclass(frozen=True)
class Neighborhood:
    center: RdfValue
    depth: int
    nodes: tuple[RdfValue, ...]
    edges: tuple[QuadView, ...]
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "center": self.center.to_dict(),
            "depth": self.depth,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class ModuleStats:
    module_id: str
    graph_iri: str
    quads: int
    resources: int
    types: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "graph_iri": self.graph_iri,
            "quads": self.quads,
            "resources": self.resources,
            "types": dict(self.types),
        }


@dataclass(frozen=True)
class DatasetStats:
    quads: int
    named_graphs: int
    resources: int
    types: tuple[tuple[str, int], ...]
    modules: tuple[ModuleStats, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "quads": self.quads,
            "named_graphs": self.named_graphs,
            "resources": self.resources,
            "types": dict(self.types),
            "modules": [module.to_dict() for module in self.modules],
        }


class OntologyQueryService:
    """Framework-independent deterministic search and graph traversal."""

    def __init__(
        self,
        dataset: Dataset,
        prefixes: PrefixResolver,
        *,
        receipt_authority: SearchReceiptAuthority | None = None,
        snapshot_id: str | None = None,
    ) -> None:
        self.dataset = dataset
        self.prefixes = prefixes
        quads: list[DatasetQuad] = []
        for subject, predicate, obj, graph in dataset.quads((None, None, None, None)):
            if graph is not None:
                quads.append((subject, predicate, obj, graph))
        self._quads = tuple(
            sorted(
                quads,
                key=lambda quad: (*_node_key(quad[3]), *(_node_key(node) for node in quad[:3])),
            )
        )
        self._receipt_authority = receipt_authority or SearchReceiptAuthority()
        if snapshot_id is None:
            digest = sha256()
            for quad in self._quads:
                digest.update(repr(tuple(_node_key(node) for node in quad)).encode("utf-8"))
                digest.update(b"\0")
            snapshot_id = f"dataset:{digest.hexdigest()}"
        self.receipt_snapshot = snapshot_id
        self._internal_object_properties = frozenset(
            subject
            for subject, predicate, obj, _ in self._quads
            if predicate == RDF.type
            and obj == OWL.ObjectProperty
            and isinstance(subject, URIRef)
            and str(subject).startswith(self.prefixes.configuration.base)
        )

    def resource_category(self, node: Node) -> ResourceCategory:
        """Classify a graph node once in the semantic core for every adapter."""

        if isinstance(node, Literal):
            return "literal"
        if not isinstance(node, (URIRef, BNode)):
            return "resource"
        types = frozenset(self._objects(node, RDF.type))
        module_type = URIRef(f"{self.prefixes.configuration.base}ontology/core#OntologyModule")
        if OWL.Ontology in types or module_type in types:
            return "module"
        if OWL.Class in types:
            return "class"
        if PROPERTY_TYPES.intersection(types):
            return "property"
        if SKOS.Concept in types:
            return "concept"
        if SH_NODE_SHAPE in types:
            return "shape"
        if OWL.NamedIndividual in types:
            return "individual"
        if any(
            isinstance(rdf_type, (URIRef, BNode)) and OWL.Class in self._objects(rdf_type, RDF.type)
            for rdf_type in types
        ):
            return "individual"
        return "resource"

    def resource_module(self, node: Node) -> str | None:
        """Return the governed module id without asking an adapter to infer RDF."""

        if not isinstance(node, (URIRef, BNode)):
            return None
        base = self.prefixes.configuration.base
        module_id = URIRef(f"{base}ontology/core#moduleId")
        identifiers = sorted(str(value) for value in self._objects(node, module_id))
        if identifiers:
            return identifiers[0]

        module_prefix = f"{base}id/module/"

        def owner(candidate: Node) -> str | None:
            owners = sorted(
                str(value)
                for value in self._objects(candidate, DCTERMS.isPartOf)
                if isinstance(value, URIRef) and str(value).startswith(module_prefix)
            )
            return owners[0][len(module_prefix) :] if owners else None

        direct = owner(node)
        if direct is not None:
            return direct
        inherited = sorted(
            {
                module
                for rdf_type in self._objects(node, RDF.type)
                if (module := owner(rdf_type)) is not None
            }
        )
        return inherited[0] if len(inherited) == 1 else None

    def resource_modules(self, node: Node) -> tuple[URIRef, ...]:
        """Return effective ownership IRIs, preserving direct ownership when present."""

        direct = self._direct_modules(node)
        if direct:
            return direct
        module = self.resource_module(node)
        if module is None:
            return ()
        return (URIRef(f"{self.prefixes.configuration.base}id/module/{module}"),)

    def _direct_modules(self, node: Node) -> tuple[URIRef, ...]:
        module_prefix = f"{self.prefixes.configuration.base}id/module/"
        return tuple(
            sorted(
                (
                    value
                    for value in self._objects(node, DCTERMS.isPartOf)
                    if isinstance(value, URIRef) and str(value).startswith(module_prefix)
                ),
                key=str,
            )
        )

    def search(
        self,
        text: str,
        *,
        limit: int = 50,
        offset: int = 0,
        rdf_types: frozenset[str] = frozenset(),
        modules: frozenset[str] = frozenset(),
    ) -> tuple[SearchResult, ...]:
        if not _normalise(text):
            return ()
        return self.search_page(
            text,
            limit=limit,
            offset=offset,
            rdf_types=rdf_types,
            modules=modules,
        ).items

    def search_page(
        self,
        text: str,
        *,
        limit: int = 50,
        offset: int = 0,
        rdf_types: frozenset[str] = frozenset(),
        modules: frozenset[str] = frozenset(),
    ) -> SearchPage:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        query = _normalise(text)
        if not query:
            raise ValueError("search text must be non-empty")
        resources = sorted(
            {
                node
                for subject, predicate, obj, _ in self._quads
                for node in (subject, predicate, obj)
                if isinstance(node, URIRef)
            },
            key=str,
        )
        results: list[SearchResult] = []
        for resource in resources:
            iri = str(resource)
            local = _local_name(iri)
            values: dict[str, tuple[str, ...]] = {
                "iri": (iri,),
                "local_name": (local,),
                "prefLabel": tuple(str(value) for value in self._objects(resource, SKOS.prefLabel)),
                "altLabel": tuple(str(value) for value in self._objects(resource, SKOS.altLabel)),
                "definition": tuple(
                    str(value) for value in self._objects(resource, SKOS.definition)
                ),
            }
            matches = tuple(
                field
                for field, candidates in values.items()
                if any(query in _normalise(candidate) for candidate in candidates)
            )
            if not matches:
                continue
            field_weight = {
                "iri": 0,
                "local_name": 10,
                "prefLabel": 20,
                "altLabel": 30,
                "definition": 40,
            }
            exact_bonus = min(
                (
                    0 if query == _normalise(candidate) else 5
                    for field in matches
                    for candidate in values[field]
                ),
                default=5,
            )
            score = min(field_weight[field] for field in matches) + exact_bonus
            labels = values["prefLabel"]
            resource_types = tuple(
                sorted(str(value) for value in self._objects(resource, RDF.type))
            )
            resource_modules = tuple(str(value) for value in self.resource_modules(resource))
            if rdf_types and not rdf_types.intersection(resource_types):
                continue
            if modules and not any(
                value in modules or any(value.endswith(f"/{item}") for item in modules)
                for value in resource_modules
            ):
                continue
            results.append(
                SearchResult(
                    iri=iri,
                    compact_iri=self.prefixes.compact(resource),
                    local_name=local,
                    label=sorted(labels)[0] if labels else None,
                    types=resource_types,
                    modules=resource_modules,
                    matched_fields=matches,
                    score=score,
                )
            )
        ordered = tuple(sorted(results, key=lambda item: (item.score, item.iri)))
        page_items = ordered[offset : offset + limit]
        search_id = self._receipt_authority.issue(
            text,
            snapshot=self.receipt_snapshot,
            results=[item.to_dict() for item in page_items],
            total=len(ordered),
            offset=offset,
            limit=limit,
            rdf_types=rdf_types,
            modules=modules,
        )
        return SearchPage(
            page_items,
            len(ordered),
            offset,
            limit,
            search_id,
        )

    def validate_search_receipt(
        self,
        query: str,
        search_id: str,
        *,
        rdf_types: frozenset[str] = frozenset(),
        modules: frozenset[str] = frozenset(),
        offset: int = 0,
        limit: int | None = None,
        for_authoring: bool = False,
    ) -> bool:
        """Validate the query, snapshot and exact semantic search modality."""

        return self._receipt_authority.validate(
            query,
            search_id,
            snapshot=self.receipt_snapshot,
            rdf_types=rdf_types,
            modules=modules,
            offset=offset,
            limit=limit,
            for_authoring=for_authoring,
        )

    def validate_authoring_search_receipt(self, query: str, search_id: str) -> bool:
        """Require an unfiltered first page suitable for global duplicate review."""

        return self.validate_search_receipt(query, search_id, for_authoring=True)

    def describe(self, resource: str | IdentifiedNode) -> ResourceDescription | None:
        node = _identified(resource)
        outgoing = tuple(self._quad_view(quad) for quad in self._quads if quad[0] == node)
        incoming = tuple(self._quad_view(quad) for quad in self._quads if quad[2] == node)
        predicate_uses = tuple(self._quad_view(quad) for quad in self._quads if quad[1] == node)
        if not outgoing and not incoming and not predicate_uses:
            return None

        def values(predicate: Node) -> tuple[RdfValue, ...]:
            return tuple(
                RdfValue.from_node(value, self.prefixes) for value in self._objects(node, predicate)
            )

        subclasses = tuple(
            RdfValue.from_node(subject, self.prefixes)
            for subject in sorted(
                {
                    subject
                    for subject, predicate, obj, _ in self._quads
                    if predicate == RDFS.subClassOf
                    and obj == node
                    and isinstance(subject, (URIRef, BNode))
                },
                key=_node_key,
            )
        )
        relevant_graphs = {
            graph
            for subject, predicate, obj, graph in self._quads
            if subject == node or predicate == node or obj == node
        }
        provenance_subjects: set[Node] = {node, *relevant_graphs}
        provenance = tuple(
            self._quad_view(quad)
            for quad in self._quads
            if quad[0] in provenance_subjects and quad[1] in PROVENANCE_PREDICATES
        )

        direct_modules = self._direct_modules(node)
        effective_modules = self.resource_modules(node)
        return ResourceDescription(
            resource=RdfValue.from_node(node, self.prefixes),
            types=values(RDF.type),
            labels=tuple(
                sorted(
                    values(SKOS.prefLabel) + values(SKOS.altLabel),
                    key=lambda item: (item.language or "", item.value),
                )
            ),
            definitions=values(SKOS.definition),
            modules=tuple(RdfValue.from_node(value, self.prefixes) for value in effective_modules),
            direct_modules=tuple(
                RdfValue.from_node(value, self.prefixes) for value in direct_modules
            ),
            status=values(URIRef(f"{self.prefixes.configuration.base}ontology/core#status")),
            outgoing=outgoing,
            incoming=incoming,
            superclasses=values(RDFS.subClassOf),
            subclasses=subclasses,
            domains=values(RDFS.domain),
            ranges=values(RDFS.range),
            provenance=provenance,
            predicate_uses=predicate_uses,
        )

    def modules(self, definitions: Iterable[ModuleDefinition]) -> tuple[ModuleDescription, ...]:
        modules = tuple(sorted(definitions, key=lambda item: item.identifier))
        ontology_by_id = {
            module.identifier: URIRef(
                f"{self.prefixes.configuration.base}ontology/{module.identifier}"
            )
            for module in modules
        }
        import_graph = {
            str(ontology): tuple(
                sorted(
                    str(value)
                    for value in self._objects(ontology, OWL.imports)
                    if isinstance(value, URIRef)
                )
            )
            for ontology in ontology_by_id.values()
        }
        cycles = self._import_cycles(import_graph)
        descriptions: list[ModuleDescription] = []
        status_predicate = URIRef(f"{self.prefixes.configuration.base}ontology/core#status")

        def values(subject: Node, predicate: Node) -> tuple[RdfValue, ...]:
            return tuple(
                RdfValue.from_node(value, self.prefixes)
                for value in self._objects(subject, predicate)
            )

        for module in modules:
            ontology = ontology_by_id[module.identifier]
            owner = URIRef(f"{self.prefixes.configuration.base}id/module/{module.identifier}")
            terms = {
                subject
                for subject, predicate, obj, _ in self._quads
                if predicate == DCTERMS.isPartOf and obj == owner
            }
            classes = {
                term
                for term in terms
                if any(
                    subject == term and predicate == RDF.type and obj == OWL.Class
                    for subject, predicate, obj, _ in self._quads
                )
            }
            properties = {
                term
                for term in terms
                if any(
                    subject == term and predicate == RDF.type and obj in PROPERTY_TYPES
                    for subject, predicate, obj, _ in self._quads
                )
            }
            competency_type = URIRef(
                f"{self.prefixes.configuration.base}ontology/competency#CompetencyQuestion"
            )
            question_count = sum(
                any(
                    subject == term and predicate == RDF.type and obj == competency_type
                    for subject, predicate, obj, _ in self._quads
                )
                for term in terms
            )

            ontology_iri = str(ontology)
            descriptions.append(
                ModuleDescription(
                    identifier=module.identifier,
                    ontology_iri=ontology_iri,
                    graph_iri=str(module.graph_iri),
                    source_path=module.source_path.as_posix(),
                    imports=import_graph[ontology_iri],
                    labels=values(ontology, SKOS.prefLabel),
                    definitions=values(ontology, SKOS.definition),
                    responsible=values(ontology, DCTERMS.rightsHolder),
                    status=values(ontology, status_predicate),
                    classes=tuple(
                        RdfValue.from_node(value, self.prefixes)
                        for value in sorted(classes, key=_node_key)
                    ),
                    properties=tuple(
                        RdfValue.from_node(value, self.prefixes)
                        for value in sorted(properties, key=_node_key)
                    ),
                    import_cycles=tuple(cycle for cycle in cycles if ontology_iri in cycle[:-1]),
                    term_count=len(terms),
                    competency_question_count=question_count,
                )
            )
        return tuple(descriptions)

    def category_counts(self) -> ResourceCategoryCounts:
        def subjects_of_type(rdf_types: frozenset[URIRef]) -> set[Node]:
            return {
                subject
                for subject, predicate, obj, _ in self._quads
                if predicate == RDF.type and obj in rdf_types
            }

        resources = {
            node
            for subject, _, obj, _ in self._quads
            for node in (subject, obj)
            if isinstance(node, (URIRef, BNode))
        }
        return ResourceCategoryCounts(
            classes=len(subjects_of_type(frozenset((OWL.Class,)))),
            properties=len(subjects_of_type(PROPERTY_TYPES)),
            concepts=len(subjects_of_type(frozenset((SKOS.Concept,)))),
            individuals=sum(
                self.resource_category(resource) == "individual" for resource in resources
            ),
        )

    @staticmethod
    def _import_cycles(import_graph: dict[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
        cycles: set[tuple[str, ...]] = set()

        def canonical(cycle: tuple[str, ...]) -> tuple[str, ...]:
            body = cycle[:-1]
            rotations = tuple(body[index:] + body[:index] for index in range(len(body)))
            selected = min(rotations)
            return (*selected, selected[0])

        def visit(node: str, path: tuple[str, ...]) -> None:
            if node in path:
                start = path.index(node)
                cycles.add(canonical((*path[start:], node)))
                return
            for imported in import_graph.get(node, ()):
                if imported in import_graph:
                    visit(imported, (*path, node))

        for ontology in sorted(import_graph):
            visit(ontology, ())
        return tuple(sorted(cycles))

    def neighborhood(
        self,
        center: str | IdentifiedNode,
        *,
        depth: int = 1,
        filters: NeighborhoodFilter | None = None,
        limits: NeighborhoodLimits | None = None,
    ) -> Neighborhood:
        active_limits = limits or NeighborhoodLimits()
        if not 0 <= depth <= active_limits.max_depth:
            raise ValueError(f"depth must be between 0 and {active_limits.max_depth}")
        center_node = _identified(center)
        active_filters = filters or NeighborhoodFilter()
        candidates = tuple(
            sorted(
                (quad for quad in self._quads if self._quad_matches(quad, active_filters)),
                key=lambda quad: (
                    self._relationship_priority(quad[1])[1],
                    tuple(_node_key(node) for node in quad),
                ),
            )
        )
        seen: set[Node] = {center_node}
        queue: deque[tuple[IdentifiedNode, int]] = deque([(center_node, 0)])
        edges: list[DatasetQuad] = []
        edge_keys: set[tuple[tuple[str, str, str, str], ...]] = set()
        truncated = False
        while queue:
            node, node_depth = queue.popleft()
            if node_depth >= depth:
                continue
            adjacent = [quad for quad in candidates if quad[0] == node or quad[2] == node]
            for quad in adjacent:
                other = quad[2] if quad[0] == node else quad[0]
                if active_filters.rdf_types and (
                    not isinstance(other, (URIRef, BNode))
                    or not self._has_type(other, active_filters.rdf_types)
                ):
                    continue
                key = tuple(_node_key(item) for item in quad)
                if key in edge_keys:
                    continue
                if len(edges) >= active_limits.max_edges:
                    truncated = True
                    continue
                if other not in seen and len(seen) >= active_limits.max_nodes:
                    truncated = True
                    continue
                edges.append(quad)
                edge_keys.add(key)
                if other not in seen:
                    seen.add(other)
                    if isinstance(other, (URIRef, BNode)):
                        queue.append((other, node_depth + 1))
        return Neighborhood(
            center=RdfValue.from_node(
                center_node,
                self.prefixes,
                category=self.resource_category(center_node),
                module=self.resource_module(center_node),
            ),
            depth=depth,
            nodes=tuple(
                RdfValue.from_node(
                    node,
                    self.prefixes,
                    category=self.resource_category(node),
                    module=self.resource_module(node),
                )
                for node in sorted(seen, key=_node_key)
            ),
            edges=tuple(
                self._quad_view(quad)
                for quad in sorted(
                    edges,
                    key=lambda item: (
                        self._relationship_priority(item[1])[1],
                        tuple(_node_key(node) for node in item),
                    ),
                )
            ),
            truncated=truncated,
        )

    def stats(self, modules: Iterable[ModuleDefinition] = ()) -> DatasetStats:
        type_counts = self._type_counts(self._quads)
        resources = self._identified_nodes(self._quads)
        module_stats: list[ModuleStats] = []
        for module in modules:
            identifier = module.identifier
            graph_iri = str(module.graph_iri)
            graph_quads = tuple(quad for quad in self._quads if str(quad[3]) == graph_iri)
            graph_resources = self._identified_nodes(graph_quads)
            module_stats.append(
                ModuleStats(
                    module_id=identifier,
                    graph_iri=graph_iri,
                    quads=len(graph_quads),
                    resources=len(graph_resources),
                    types=self._type_counts(graph_quads),
                )
            )
        graph_ids = {graph for *_, graph in self._quads}
        return DatasetStats(
            quads=len(self._quads),
            named_graphs=len(graph_ids),
            resources=len(resources),
            types=type_counts,
            modules=tuple(sorted(module_stats, key=lambda item: item.module_id)),
        )

    def _objects(self, subject: Node, predicate: Node) -> tuple[Node, ...]:
        return tuple(
            sorted(
                {
                    obj
                    for current, current_predicate, obj, _ in self._quads
                    if current == subject and current_predicate == predicate
                },
                key=_node_key,
            )
        )

    def _quad_view(self, quad: tuple[Node, Node, Node, IdentifiedNode]) -> QuadView:
        subject, predicate, obj, graph = quad
        relationship_kind, priority = self._relationship_priority(predicate)
        status_predicate = URIRef(f"{self.prefixes.configuration.base}ontology/core#status")
        assertion_statuses = sorted(
            str(status)
            for assertion, assertion_predicate, assertion_subject, assertion_graph in self._quads
            if assertion_predicate == RDF.subject
            and assertion_subject == subject
            and assertion_graph == graph
            and (assertion, RDF.predicate, predicate, graph) in self._quads
            and (assertion, RDF.object, obj, graph) in self._quads
            for status_subject, current_predicate, status, status_graph in self._quads
            if status_subject == assertion
            and current_predicate == status_predicate
            and status_graph == graph
        )
        return QuadView(
            subject=RdfValue.from_node(subject, self.prefixes),
            predicate=RdfValue.from_node(predicate, self.prefixes),
            object=RdfValue.from_node(obj, self.prefixes),
            graph=RdfValue.from_node(graph, self.prefixes),
            relationship_kind=relationship_kind,
            priority=priority,
            status=assertion_statuses[0] if assertion_statuses else None,
        )

    def _relationship_priority(self, predicate: Node) -> tuple[RelationshipKind, int]:
        fixed: dict[Node, tuple[RelationshipKind, int]] = {
            RDFS.subClassOf: ("subclass", 1),
            RDFS.subPropertyOf: ("subproperty", 2),
            RDFS.domain: ("domain", 3),
            RDFS.range: ("range", 4),
            OWL.imports: ("import", 5),
        }
        if predicate in fixed:
            return fixed[predicate]
        if predicate in self._internal_object_properties:
            return ("internal_object_property", 6)
        return ("other", 7)

    def _quad_matches(
        self,
        quad: DatasetQuad,
        filters: NeighborhoodFilter,
    ) -> bool:
        _, predicate, _, graph = quad
        if filters.graph_iris and str(graph) not in filters.graph_iris:
            return False
        return not filters.predicates or str(predicate) in filters.predicates

    def _has_type(self, node: IdentifiedNode, rdf_types: frozenset[str]) -> bool:
        return any(
            current == node and predicate == RDF.type and str(obj) in rdf_types
            for current, predicate, obj, _ in self._quads
        )

    @staticmethod
    def _identified_nodes(quads: Iterable[DatasetQuad]) -> set[IdentifiedNode]:
        return {
            node
            for subject, predicate, obj, _ in quads
            for node in (subject, predicate, obj)
            if isinstance(node, (URIRef, BNode))
        }

    @staticmethod
    def _type_counts(
        quads: Iterable[DatasetQuad],
    ) -> tuple[tuple[str, int], ...]:
        typed: dict[str, set[Node]] = {}
        for subject, predicate, obj, _ in quads:
            if predicate == RDF.type and isinstance(obj, URIRef):
                typed.setdefault(str(obj), set()).add(subject)
        return tuple(sorted((rdf_type, len(subjects)) for rdf_type, subjects in typed.items()))

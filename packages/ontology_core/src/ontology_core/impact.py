"""Deterministic impact analysis over references, hierarchies, shapes and imports."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import BNode, Dataset, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS
from rdflib.term import IdentifiedNode, Node

from ontology_core.prefixes import PrefixResolver
from ontology_core.query import QuadView, RdfValue, _identified, _node_key
from ontology_core.store import FilesystemRdfStore

SH = "http://www.w3.org/ns/shacl#"
SH_TARGET_CLASS = URIRef(f"{SH}targetClass")
SH_TARGET_NODE = URIRef(f"{SH}targetNode")
SH_PATH = URIRef(f"{SH}path")
SH_NODE_SHAPE = URIRef(f"{SH}NodeShape")


@dataclass(frozen=True)
class ImpactReport:
    resource: RdfValue
    incoming: tuple[QuadView, ...]
    outgoing: tuple[QuadView, ...]
    predicate_uses: tuple[QuadView, ...]
    ancestors: tuple[RdfValue, ...]
    descendants: tuple[RdfValue, ...]
    shapes: tuple[RdfValue, ...]
    competency_questions: tuple[RdfValue, ...]
    import_dependencies: tuple[RdfValue, ...]
    affected_importers: tuple[RdfValue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "resource": self.resource.to_dict(),
            "incoming": [quad.to_dict() for quad in self.incoming],
            "outgoing": [quad.to_dict() for quad in self.outgoing],
            "predicate_uses": [quad.to_dict() for quad in self.predicate_uses],
            "ancestors": [node.to_dict() for node in self.ancestors],
            "descendants": [node.to_dict() for node in self.descendants],
            "shapes": [node.to_dict() for node in self.shapes],
            "competency_questions": [node.to_dict() for node in self.competency_questions],
            "import_dependencies": [node.to_dict() for node in self.import_dependencies],
            "affected_importers": [node.to_dict() for node in self.affected_importers],
        }


class ImpactService:
    """Calculate explainable impact without reasoning or remote dereferencing."""

    def __init__(
        self,
        dataset: Dataset,
        prefixes: PrefixResolver,
        *,
        store: FilesystemRdfStore,
    ) -> None:
        if dataset is not store.dataset:
            raise ValueError("ImpactService requires the current Dataset loaded by its store")
        if prefixes is not store.prefixes:
            raise ValueError("ImpactService requires the PrefixResolver owned by its store")
        self.dataset = dataset
        self.prefixes = prefixes
        catalog = store.load_shape_catalog()
        required_shapes = {
            URIRef(f"{prefixes.configuration.base}shape/governance/TermShape"),
            URIRef(f"{prefixes.configuration.base}shape/governance/PropertyShape"),
        }
        missing_shapes = sorted(
            str(shape)
            for shape in required_shapes
            if (shape, RDF.type, SH_NODE_SHAPE) not in catalog.graph
        )
        if missing_shapes:
            raise ValueError(
                "the complete local SHACL shape catalog is required; missing: "
                + ", ".join(missing_shapes)
            )
        self.knowledge_root = store.knowledge_root
        self.shape_sources = catalog.source_paths
        self.shapes_graph = catalog.graph
        self._quads = tuple(
            sorted(
                (
                    (subject, predicate, obj, graph)
                    for subject, predicate, obj, graph in dataset.quads((None, None, None, None))
                    if graph is not None
                ),
                key=lambda quad: tuple(_node_key(node) for node in quad),
            )
        )

    def analyze(self, resource: str | IdentifiedNode) -> ImpactReport:
        node = _identified(resource)
        incoming = tuple(self._view(quad) for quad in self._quads if quad[2] == node)
        outgoing = tuple(self._view(quad) for quad in self._quads if quad[0] == node)
        predicate_uses = tuple(self._view(quad) for quad in self._quads if quad[1] == node)
        hierarchy_predicates = (RDFS.subClassOf, RDFS.subPropertyOf)
        ancestors: set[IdentifiedNode] = set()
        descendants: set[IdentifiedNode] = set()
        for predicate in hierarchy_predicates:
            ancestors.update(self._transitive(node, predicate, forward=True))
            descendants.update(self._transitive(node, predicate, forward=False))
        return ImpactReport(
            resource=RdfValue.from_node(node, self.prefixes),
            incoming=incoming,
            outgoing=outgoing,
            predicate_uses=predicate_uses,
            ancestors=self._values(ancestors),
            descendants=self._values(descendants),
            shapes=self._values(self._applicable_shapes(node)),
            competency_questions=self._values(self._related_questions(node)),
            import_dependencies=self._values(self._import_closure(node, reverse=False)),
            affected_importers=self._values(self._import_closure(node, reverse=True)),
        )

    def _transitive(
        self,
        start: IdentifiedNode,
        predicate: URIRef,
        *,
        forward: bool,
    ) -> set[IdentifiedNode]:
        found: set[IdentifiedNode] = set()
        pending = [start]
        while pending:
            current = pending.pop()
            candidates = (
                (
                    obj
                    for subject, pred, obj, _ in self._quads
                    if subject == current and pred == predicate
                )
                if forward
                else (
                    subject
                    for subject, pred, obj, _ in self._quads
                    if obj == current and pred == predicate
                )
            )
            for candidate in candidates:
                if isinstance(candidate, (URIRef, BNode)) and candidate not in found:
                    found.add(candidate)
                    pending.append(candidate)
        found.discard(start)
        return found

    def _applicable_shapes(self, resource: IdentifiedNode) -> set[IdentifiedNode]:
        resource_types = {
            obj
            for subject, predicate, obj, _ in self._quads
            if subject == resource and predicate == RDF.type
        }
        shapes: set[IdentifiedNode] = set()
        for shape, predicate, target in self.shapes_graph.triples((None, None, None)):
            if not isinstance(shape, (URIRef, BNode)):
                continue
            matches_target = (
                (predicate == SH_TARGET_NODE and target == resource)
                or (predicate == SH_TARGET_CLASS and target in resource_types)
                or (predicate == SH_PATH and target == resource)
            )
            if matches_target:
                shapes.add(shape)
        return shapes

    def _owned_ontologies(self, resource: IdentifiedNode) -> set[URIRef]:
        owners = {
            obj
            for subject, predicate, obj, _ in self._quads
            if subject == resource and predicate == DCTERMS.isPartOf and isinstance(obj, URIRef)
        }
        owned_ontologies = {
            subject
            for subject, predicate, obj, _ in self._quads
            if predicate == DCTERMS.isPartOf
            and obj in owners
            and isinstance(subject, URIRef)
            and any(
                current == subject and current_predicate == RDF.type and current_obj == OWL.Ontology
                for current, current_predicate, current_obj, _ in self._quads
            )
        }
        if isinstance(resource, URIRef) and any(
            subject == resource and predicate == RDF.type and obj == OWL.Ontology
            for subject, predicate, obj, _ in self._quads
        ):
            owned_ontologies.add(resource)
        return owned_ontologies

    def _import_closure(
        self,
        resource: IdentifiedNode,
        *,
        reverse: bool,
    ) -> set[IdentifiedNode]:
        origins = self._owned_ontologies(resource)
        found: set[IdentifiedNode] = set()
        pending: list[IdentifiedNode] = sorted(origins, key=_node_key)
        while pending:
            current = pending.pop()
            candidates = (
                (
                    subject
                    for subject, predicate, obj, _ in self._quads
                    if predicate == OWL.imports and obj == current
                )
                if reverse
                else (
                    obj
                    for subject, predicate, obj, _ in self._quads
                    if predicate == OWL.imports and subject == current
                )
            )
            for candidate in candidates:
                if isinstance(candidate, (URIRef, BNode)) and candidate not in found:
                    found.add(candidate)
                    pending.append(candidate)
        found.difference_update(origins)
        return found

    def _related_questions(self, resource: IdentifiedNode) -> set[IdentifiedNode]:
        owners = {
            obj
            for subject, predicate, obj, _ in self._quads
            if subject == resource and predicate == DCTERMS.isPartOf
        }
        question_type = URIRef(
            f"{self.prefixes.configuration.base}ontology/competency#CompetencyQuestion"
        )
        questions = {
            subject
            for subject, predicate, obj, _ in self._quads
            if predicate == RDF.type
            and obj == question_type
            and isinstance(subject, (URIRef, BNode))
        }
        return {
            question
            for question in questions
            if any(
                subject == question and predicate == DCTERMS.isPartOf and obj in owners
                for subject, predicate, obj, _ in self._quads
            )
        }

    def _view(self, quad: tuple[Node, Node, Node, IdentifiedNode]) -> QuadView:
        subject, predicate, obj, graph = quad
        return QuadView(
            subject=RdfValue.from_node(subject, self.prefixes),
            predicate=RdfValue.from_node(predicate, self.prefixes),
            object=RdfValue.from_node(obj, self.prefixes),
            graph=RdfValue.from_node(graph, self.prefixes),
        )

    def _values(self, nodes: set[IdentifiedNode]) -> tuple[RdfValue, ...]:
        return tuple(
            RdfValue.from_node(node, self.prefixes) for node in sorted(nodes, key=_node_key)
        )

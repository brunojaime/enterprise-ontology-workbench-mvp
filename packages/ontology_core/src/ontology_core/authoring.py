"""Confined, atomic RDF authoring for proposal branches."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Literal as TypingLiteral

from rdflib import Dataset, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SH, SKOS, XSD
from rdflib.term import Node

from ontology_core.forms import FormField, FormSchemaService
from ontology_core.query import PROPERTY_TYPES, OntologyQueryService
from ontology_core.store import FilesystemRdfStore, ModuleDefinition
from ontology_core.validation import ValidationService
from ontology_core.workspace import GitWorkspaceService

TermKind = TypingLiteral[
    "class",
    "concept",
    "object_property",
    "datatype_property",
    "annotation_property",
    "ontology",
    "node_shape",
    "competency_question",
]
PropertyKind = TypingLiteral["object_property", "datatype_property", "annotation_property"]
StatementState = TypingLiteral["proposed", "active", "deprecated"]
LOCAL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
SOURCE_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TERM_RDF_TYPES = frozenset(
    (OWL.Class, SKOS.Concept, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)
)
STANDARD_RELATION_PROPERTIES = frozenset((DCTERMS.identifier, DCTERMS.rightsHolder, OWL.imports))


class AuthoringError(RuntimeError):
    """A deterministic authoring rule rejected a proposed change."""

    def __init__(self, code: str, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class SearchConfirmation:
    query: str
    confirmed: bool
    search_id: str = ""

    def require(self, search: OntologyQueryService | None) -> None:
        if not self.query.strip() or not self.confirmed:
            raise AuthoringError(
                "authoring.search_required",
                "A prior search and explicit review of candidates are required.",
            )
        if search is None or not search.validate_authoring_search_receipt(
            self.query, self.search_id
        ):
            raise AuthoringError(
                "authoring.invalid_search_id",
                "The proposal must include the search receipt issued for its reviewed query.",
            )


@dataclass(frozen=True)
class TermDraft:
    iri: str
    module_id: str
    kind: TermKind
    preferred_label_es: str
    definition_es: str
    evidence: str
    author: str
    search: SearchConfirmation
    alternative_labels_es: tuple[str, ...] = ()
    status: StatementState = "proposed"
    reading_direction_es: str | None = None
    valid_example: str | None = None
    domain: str | None = None
    range: str | None = None
    question_text_es: str | None = None
    acceptance_criterion_es: str | None = None
    form_values: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class IndividualDraft:
    iri: str
    class_iri: str
    source_id: str
    preferred_label_es: str
    evidence: str
    author: str
    search: SearchConfirmation
    alternative_labels_es: tuple[str, ...] = ()
    status: StatementState = "proposed"
    form_values: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class RelationDraft:
    subject: str
    predicate: str
    object_iri: str | None
    literal: str | None
    datatype: str | None
    language: str | None
    evidence: str
    status: StatementState = "proposed"


@dataclass(frozen=True)
class RelationIdentity:
    subject: str
    predicate: str
    object_iri: str | None
    literal: str | None
    datatype: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class DeprecationDraft:
    iri: str
    reason: str
    replacement_iri: str | None = None


@dataclass(frozen=True)
class WriteResult:
    operation: str
    resource: str
    path: str
    preserved_unknown_triples: int

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "resource": self.resource,
            "path": self.path,
            "preserved_unknown_triples": self.preserved_unknown_triples,
        }


@dataclass(frozen=True)
class EditableResource:
    iri: str
    kind: str
    preferred_label_es: str
    alternative_labels_es: tuple[str, ...]
    definition_es: str
    module_id: str
    status: str
    evidence: str
    author: str
    reading_direction_es: str
    valid_example: str
    domain: str
    range: str
    class_iri: str
    source_id: str
    question_text_es: str
    acceptance_criterion_es: str
    form_values: tuple[tuple[str, tuple[str, ...]], ...]
    path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "iri": self.iri,
            "kind": self.kind,
            "preferred_label_es": self.preferred_label_es,
            "alternative_labels_es": list(self.alternative_labels_es),
            "definition_es": self.definition_es,
            "module_id": self.module_id,
            "status": self.status,
            "evidence": self.evidence,
            "author": self.author,
            "reading_direction_es": self.reading_direction_es,
            "valid_example": self.valid_example,
            "domain": self.domain,
            "range": self.range,
            "class_iri": self.class_iri,
            "source_id": self.source_id,
            "question_text_es": self.question_text_es,
            "acceptance_criterion_es": self.acceptance_criterion_es,
            "form_values": {key: list(values) for key, values in self.form_values},
            "path": self.path,
        }


class TermWriter:
    """Write only responsible RDF files while retaining unmodelled statements."""

    def __init__(
        self,
        store: FilesystemRdfStore,
        workspace: GitWorkspaceService | None,
        search: OntologyQueryService | None = None,
    ) -> None:
        if workspace is not None and store.knowledge_root != workspace.knowledge_root:
            raise ValueError("writer and workspace require the same knowledge root")
        self.store = store
        self.workspace = workspace
        self.search = search
        self.base = store.namespace_configuration.base
        self.status_predicate = URIRef(f"{self.base}ontology/core#status")
        self.competency_type = URIRef(f"{self.base}ontology/competency#CompetencyQuestion")
        self.question_text = URIRef(f"{self.base}ontology/competency#questionText")
        self.acceptance_criterion = URIRef(f"{self.base}ontology/competency#acceptanceCriterion")

    def save_term(self, draft: TermDraft) -> WriteResult:
        self._require_workspace().require_proposal_branch()
        draft.search.require(self.search)
        self._require_text(draft.preferred_label_es, "preferred_label_es")
        self._require_text(draft.definition_es, "definition_es")
        self._require_text(draft.evidence, "evidence")
        self._require_text(draft.author, "author")
        if draft.kind in {"ontology", "node_shape", "competency_question"}:
            return self._save_structured_resource(draft)
        subject = self._internal_iri(draft.iri)
        module = self._module(draft.module_id)
        path = self._term_path(subject, module)
        graph = self._load_graph(path)
        existed = path.exists()
        if not existed and any(True for _ in self.store.load().quads((subject, None, None, None))):
            raise AuthoringError(
                "authoring.iri_exists_elsewhere",
                "The IRI already exists outside its responsible term file.",
                details={"iri": draft.iri},
            )
        rdf_type = {
            "class": OWL.Class,
            "concept": SKOS.Concept,
            "object_property": OWL.ObjectProperty,
            "datatype_property": OWL.DatatypeProperty,
            "annotation_property": OWL.AnnotationProperty,
        }[draft.kind]
        existing_editable_types = set(graph.objects(subject, RDF.type)) & TERM_RDF_TYPES
        if existed and existing_editable_types != {rdf_type}:
            raise AuthoringError(
                "authoring.kind_mismatch",
                "An existing resource cannot change its supported RDF type implicitly.",
                details={
                    "expected": str(rdf_type),
                    "actual": ",".join(sorted(map(str, existing_editable_types))),
                },
            )
        dynamic_fields = self._dynamic_fields(
            draft.kind, draft.form_values, graph=graph, subject=subject
        )
        managed = self._managed_term_predicates() | frozenset((self.status_predicate,))
        preserved = sum(
            1
            for _, predicate, _ in graph.triples((subject, None, None))
            if predicate not in managed
        )
        self._replace_dynamic_fields(graph, subject, dynamic_fields)
        self._replace_iri_nodes(
            graph, subject, DCTERMS.isPartOf, (self._module_iri(module.identifier),)
        )
        self._replace_plain_literals(graph, subject, self.status_predicate, (draft.status,))
        self._replace_plain_literals(graph, subject, DCTERMS.creator, (draft.author,))
        self._replace_language_literals(
            graph, subject, SKOS.prefLabel, (draft.preferred_label_es,), "es"
        )
        self._replace_language_literals(
            graph, subject, SKOS.definition, (draft.definition_es,), "es"
        )
        self._replace_language_literals(
            graph, subject, SKOS.altLabel, draft.alternative_labels_es, "es"
        )
        self._replace_language_literals(graph, subject, DCTERMS.source, (draft.evidence,), "es")
        self._update_timestamp(graph, subject, existed)
        for editable_type in TERM_RDF_TYPES:
            graph.remove((subject, RDF.type, editable_type))
        graph.add((subject, RDF.type, rdf_type))
        if draft.kind.endswith("property"):
            self._add_property_fields(graph, subject, draft)
        elif any(
            value is not None
            for value in (
                draft.reading_direction_es,
                draft.valid_example,
                draft.domain,
                draft.range,
            )
        ):
            raise AuthoringError(
                "authoring.unexpected_property_fields",
                "Property-specific fields are not valid for this term kind.",
            )
        self._add_dynamic_fields(graph, subject, dynamic_fields)
        self._write_graph(path, graph)
        return self._result("created" if not existed else "updated", subject, path, preserved)

    def editable_resource(self, iri: str) -> EditableResource:
        dataset = self.store.load()
        subject = URIRef(iri)
        sources = self.store.source_paths_for(subject)
        if not any(True for _ in dataset.quads((subject, None, None, None))):
            shape_sources = self._shape_sources_for(subject)
            if shape_sources:
                shape_graph = Graph().parse(shape_sources[0], format="turtle")
                target = dataset.graph(URIRef(f"{self.base}graph/authoring/shapes"))
                for triple in shape_graph:
                    target.add(triple)
                sources = shape_sources
            else:
                self._existing_resource(dataset, iri, "resource")
        if len(sources) != 1:
            raise AuthoringError(
                "authoring.responsible_file_ambiguous",
                "An editable resource must have exactly one responsible source file.",
            )
        types = set(self._objects(dataset, subject, RDF.type))
        kind = self._kind_for_types(types)
        if kind is None:
            raise AuthoringError(
                "authoring.unsupported_resource_type",
                "The resource has no unambiguous editable RDF type.",
            )
        modules = tuple(self._objects(dataset, subject, DCTERMS.isPartOf))
        module_id = str(modules[0]).rstrip("/").rsplit("/", 1)[-1] if len(modules) == 1 else ""
        business_classes = sorted(
            (
                value
                for value in types
                if value != OWL.NamedIndividual and self._has(dataset, value, RDF.type, OWL.Class)
            ),
            key=str,
        )
        path = sources[0]
        dynamic_schema = FormSchemaService(self.store).schema(kind)
        standard_keys = self._standard_form_keys()
        form_values = tuple(
            (
                field.key,
                tuple(
                    sorted(
                        str(value)
                        for value in self._objects(dataset, subject, URIRef(field.path))
                        if self._dynamic_node_is_editable(field, value)
                    )
                ),
            )
            for field in dynamic_schema.fields
            if field.key not in standard_keys
            and any(
                self._dynamic_node_is_editable(field, value)
                for value in self._objects(dataset, subject, URIRef(field.path))
            )
        )
        return EditableResource(
            iri=iri,
            kind=kind,
            preferred_label_es=self._language_text(dataset, subject, SKOS.prefLabel, "es")
            or self._language_text(dataset, subject, SH.name, "es")
            or self._language_text(dataset, subject, self.question_text, "es"),
            alternative_labels_es=self._language_texts(dataset, subject, SKOS.altLabel, "es"),
            definition_es=self._language_text(dataset, subject, SKOS.definition, "es")
            or self._language_text(dataset, subject, SH.description, "es"),
            module_id=module_id,
            status=self._first_text(dataset, subject, self.status_predicate),
            evidence=self._first_text(dataset, subject, DCTERMS.source),
            author=self._first_text(dataset, subject, DCTERMS.creator),
            reading_direction_es=self._language_text(dataset, subject, SKOS.scopeNote, "es"),
            valid_example=self._first_text(dataset, subject, SKOS.example),
            domain=self._first_iri(dataset, subject, RDFS.domain),
            range=self._first_iri(dataset, subject, RDFS.range),
            class_iri=str(business_classes[0]) if len(business_classes) == 1 else "",
            source_id=path.stem if kind == "individual" else "",
            question_text_es=self._language_text(dataset, subject, self.question_text, "es"),
            acceptance_criterion_es=self._language_text(
                dataset, subject, self.acceptance_criterion, "es"
            ),
            form_values=form_values,
            path=path.relative_to(self._repository_root()).as_posix(),
        )

    def save_individual(self, draft: IndividualDraft) -> WriteResult:
        self._require_workspace().require_proposal_branch()
        draft.search.require(self.search)
        self._require_text(draft.preferred_label_es, "preferred_label_es")
        self._require_text(draft.evidence, "evidence")
        self._require_text(draft.author, "author")
        if not SOURCE_SLUG.fullmatch(draft.source_id):
            raise AuthoringError("authoring.invalid_source", "source_id must be a safe slug")
        subject = self._internal_iri(draft.iri)
        class_iri = URIRef(draft.class_iri)
        dataset = self.store.load()
        if not self._has(dataset, class_iri, RDF.type, OWL.Class):
            raise AuthoringError(
                "authoring.unknown_class",
                "The selected individual class does not exist.",
                details={"class_iri": draft.class_iri},
            )
        source_paths = self.store.source_paths_for(subject)
        if len(source_paths) > 1:
            raise AuthoringError(
                "authoring.duplicate_individual_iri",
                "An individual IRI must have exactly one responsible source file.",
                details={"paths": ",".join(item.as_posix() for item in source_paths)},
            )
        if source_paths:
            path = source_paths[0]
            if path.stem != draft.source_id:
                raise AuthoringError(
                    "authoring.duplicate_individual_iri",
                    "An existing individual must remain in its responsible source file.",
                    details={"source_id": path.stem},
                )
        else:
            path = (
                self.store.knowledge_root
                / "data"
                / "sources"
                / "proposals"
                / f"{draft.source_id}.ttl"
            )
        document_dataset: Dataset | None = None
        if path.suffix.lower() == ".trig":
            document_dataset = self._load_dataset(path)
            graph_ids = tuple(
                sorted(
                    {
                        graph_iri
                        for _, _, _, graph_iri in document_dataset.quads(
                            (subject, None, None, None)
                        )
                        if graph_iri is not None
                    },
                    key=str,
                )
            )
            if len(graph_ids) != 1:
                raise AuthoringError(
                    "authoring.responsible_graph_ambiguous",
                    "The individual must belong to exactly one graph in its source file.",
                )
            graph = document_dataset.graph(graph_ids[0])
        else:
            graph = self._load_graph(path)
        dynamic_fields = self._dynamic_fields(
            "individual", draft.form_values, graph=graph, subject=subject
        )
        managed = frozenset(
            (
                DCTERMS.creator,
                self.status_predicate,
            )
        )
        existed = any(True for _ in graph.triples((subject, None, None)))
        preserved = sum(
            1
            for _, predicate, _ in graph.triples((subject, None, None))
            if predicate not in managed
        )
        self._replace_dynamic_fields(graph, subject, dynamic_fields)
        self._replace_plain_literals(graph, subject, DCTERMS.creator, (draft.author,))
        self._replace_plain_literals(graph, subject, self.status_predicate, (draft.status,))
        self._replace_language_literals(
            graph, subject, SKOS.prefLabel, (draft.preferred_label_es,), "es"
        )
        self._replace_language_literals(
            graph, subject, SKOS.altLabel, draft.alternative_labels_es, "es"
        )
        self._replace_language_literals(graph, subject, DCTERMS.source, (draft.evidence,), "es")
        self._update_timestamp(graph, subject, existed)
        existing_classes = {
            value
            for value in graph.objects(subject, RDF.type)
            if value != OWL.NamedIndividual and self._has(dataset, value, RDF.type, OWL.Class)
        }
        if existed and existing_classes and existing_classes != {class_iri}:
            raise AuthoringError(
                "authoring.kind_mismatch",
                "An existing individual cannot change its business class implicitly.",
            )
        graph.add((subject, RDF.type, class_iri))
        graph.add((subject, RDF.type, OWL.NamedIndividual))
        self._add_dynamic_fields(graph, subject, dynamic_fields)
        if document_dataset is None:
            self._write_graph(path, graph)
        else:
            self._write_dataset(path, document_dataset)
        return self._result("created" if not existed else "updated", subject, path, preserved)

    def save_relation(self, draft: RelationDraft) -> WriteResult:
        workspace_status = self._require_workspace().require_proposal_branch()
        self._require_text(draft.evidence, "evidence")
        if (draft.object_iri is None) == (draft.literal is None):
            raise AuthoringError(
                "authoring.invalid_relation_object",
                "Exactly one object IRI or literal must be supplied.",
            )
        dataset = self.store.load()
        subject = self._existing_resource(dataset, draft.subject, "subject")
        requested_predicate = URIRef(draft.predicate)
        predicate = (
            requested_predicate
            if requested_predicate in STANDARD_RELATION_PROPERTIES
            else self._existing_resource(dataset, draft.predicate, "predicate")
        )
        property_types = set(self._objects(dataset, predicate, RDF.type))
        if (
            not property_types.intersection(PROPERTY_TYPES)
            and predicate not in STANDARD_RELATION_PROPERTIES
        ):
            raise AuthoringError(
                "authoring.not_property", "The selected predicate is not a property."
            )
        if draft.object_iri is not None:
            obj: Node = self._existing_resource(dataset, draft.object_iri, "object")
            if OWL.DatatypeProperty in property_types:
                raise AuthoringError(
                    "authoring.object_type_mismatch", "Datatype properties require literals."
                )
        else:
            if OWL.ObjectProperty in property_types:
                raise AuthoringError(
                    "authoring.object_type_mismatch", "Object properties require resource IRIs."
                )
            datatype = URIRef(draft.datatype) if draft.datatype else None
            obj = Literal(draft.literal, lang=draft.language, datatype=datatype)
        if any(True for _ in dataset.quads((subject, predicate, obj, None))):
            raise AuthoringError(
                "authoring.relation_exists",
                "The direct relation already exists and cannot be relabelled as a proposal.",
            )
        self._validate_domain_range(dataset, subject, predicate, obj)
        sources = self.store.source_paths_for(subject)
        if len(sources) != 1:
            raise AuthoringError(
                "authoring.responsible_file_ambiguous",
                "The relation subject must have exactly one responsible source file.",
            )
        path = sources[0]
        document_dataset: Dataset | None = None
        metadata_triples: tuple[tuple[Node, Node, Node], ...] = ()
        metadata_graph_iri: URIRef | None = None
        if path.suffix.lower() == ".trig":
            document_dataset = self._load_dataset(path)
            graph_ids = tuple(
                sorted(
                    {
                        graph_iri
                        for _, _, _, graph_iri in document_dataset.quads(
                            (subject, None, None, None)
                        )
                        if graph_iri is not None
                    },
                    key=str,
                )
            )
            definition_graph_ids = tuple(
                graph_iri
                for graph_iri in graph_ids
                if any(document_dataset.graph(graph_iri).triples((subject, RDF.type, None)))
            )
            responsible_graph_ids = definition_graph_ids or graph_ids
            if len(responsible_graph_ids) != 1:
                raise AuthoringError(
                    "authoring.responsible_graph_ambiguous",
                    "The relation subject must belong to exactly one graph in its source file.",
                )
            source_graph_iri = responsible_graph_ids[0]
            target_graph_iri = source_graph_iri
            if draft.status == "proposed" and self._has(
                dataset,
                source_graph_iri,
                self.status_predicate,
                Literal("published"),
            ):
                branch_slug = (workspace_status.branch or "proposal/unknown").removeprefix(
                    "proposal/"
                )
                target_graph_iri = URIRef(f"{self.base}graph/proposal/{branch_slug}/{path.stem}")
                metadata_graph_iri = URIRef(
                    f"{self.base}graph/metadata/proposal/{branch_slug}/{path.stem}"
                )
                metadata_triples = (
                    (target_graph_iri, RDF.type, PROV.Entity),
                    (target_graph_iri, self.status_predicate, Literal("proposed")),
                    (target_graph_iri, PROV.wasDerivedFrom, source_graph_iri),
                )
            graph = document_dataset.graph(target_graph_iri)
        else:
            graph = self._load_graph(path)
            graph_ids = tuple(
                sorted(
                    {
                        graph_iri
                        for _, _, _, graph_iri in dataset.quads((subject, None, None, None))
                        if graph_iri is not None
                    },
                    key=str,
                )
            )
            if len(graph_ids) != 1:
                raise AuthoringError(
                    "authoring.responsible_graph_ambiguous",
                    "The relation subject must belong to exactly one canonical graph.",
                )
            target_graph_iri = graph_ids[0]
        before = len(graph)
        assertion = self._statement_iri(subject, predicate, obj)
        statement_triples = (
            (subject, predicate, obj),
            (assertion, RDF.type, RDF.Statement),
            (assertion, RDF.subject, subject),
            (assertion, RDF.predicate, predicate),
            (assertion, RDF.object, obj),
            (assertion, DCTERMS.source, Literal(draft.evidence.strip(), lang="es")),
            (assertion, self.status_predicate, Literal(draft.status)),
        )
        for triple in statement_triples:
            graph.add(triple)
        if document_dataset is not None and metadata_graph_iri is not None:
            metadata_graph = document_dataset.graph(metadata_graph_iri)
            for metadata_triple in metadata_triples:
                metadata_graph.add(metadata_triple)
        candidate = self._copy_dataset(dataset)
        candidate_graph = candidate.graph(target_graph_iri)
        for triple in statement_triples:
            candidate_graph.add(triple)
        if metadata_graph_iri is not None:
            candidate_metadata_graph = candidate.graph(metadata_graph_iri)
            for metadata_triple in metadata_triples:
                candidate_metadata_graph.add(metadata_triple)
        report = ValidationService(self.store).validate_dataset(candidate)
        if not report.conforms:
            raise AuthoringError(
                "authoring.relation_validation_failed",
                "The relation does not pass the current SHACL and governance rules.",
                details={"issues": str(len(report.issues))},
            )
        if document_dataset is None:
            self._write_graph(path, graph)
        else:
            self._write_dataset(path, document_dataset)
        return self._result("relation_added", subject, path, before)

    def deprecate(self, draft: DeprecationDraft) -> WriteResult:
        self._require_workspace().require_proposal_branch()
        self._require_text(draft.reason, "reason")
        subject = self._internal_iri(draft.iri)
        self.store.load()
        sources = self.store.source_paths_for(subject)
        if len(sources) != 1 or "/ontology/" not in sources[0].as_posix():
            raise AuthoringError(
                "authoring.published_term_not_found",
                "Only a published ontology term with one responsible file can be deprecated.",
            )
        path = sources[0]
        graph = self._load_graph(path)
        before = len(graph)
        graph.set((subject, self.status_predicate, Literal("deprecated")))
        graph.set((subject, OWL.deprecated, Literal(True)))
        graph.set((subject, SKOS.changeNote, Literal(draft.reason.strip(), lang="es")))
        graph.set((subject, DCTERMS.modified, Literal(date.today().isoformat(), datatype=XSD.date)))
        if draft.replacement_iri:
            replacement = self._existing_resource(
                self.store.dataset, draft.replacement_iri, "replacement"
            )
            graph.set((subject, DCTERMS.isReplacedBy, replacement))
        self._write_graph(path, graph)
        return self._result("deprecated", subject, path, before)

    def delete_draft_relation(self, identity: RelationIdentity) -> WriteResult:
        self._require_workspace().require_proposal_branch()
        dataset = self.store.load()
        subject = self._existing_resource(dataset, identity.subject, "subject")
        predicate = URIRef(identity.predicate)
        if (identity.object_iri is None) == (identity.literal is None):
            raise AuthoringError(
                "authoring.invalid_relation_object",
                "Exactly one object IRI or literal must be supplied.",
            )
        obj: Node
        if identity.object_iri is not None:
            obj = URIRef(identity.object_iri)
        else:
            obj = Literal(
                identity.literal,
                lang=identity.language,
                datatype=URIRef(identity.datatype) if identity.datatype else None,
            )
        assertions = tuple(
            assertion
            for assertion, _, _, _ in dataset.quads((None, RDF.subject, subject, None))
            if self._has(dataset, assertion, RDF.predicate, predicate)
            and self._has(dataset, assertion, RDF.object, obj)
            and self._has(dataset, assertion, self.status_predicate, Literal("proposed"))
        )
        if len(assertions) != 1:
            raise AuthoringError(
                "authoring.published_relation",
                "Only relations explicitly marked as proposed in this branch can be deleted.",
            )
        sources = self.store.source_paths_for(subject)
        if len(sources) != 1:
            raise AuthoringError(
                "authoring.responsible_file_ambiguous",
                "The relation subject must have exactly one responsible source file.",
            )
        path = sources[0]
        if self._published_triple(path, subject, predicate, obj):
            raise AuthoringError(
                "authoring.published_relation",
                "A relation present in the published base cannot be deleted.",
            )
        if path.suffix == ".trig":
            document = self._load_dataset(path)
            located = next(
                (
                    (candidate, graph_iri)
                    for candidate, _, _, graph_iri in document.quads(
                        (None, RDF.subject, subject, None)
                    )
                    if graph_iri is not None
                    and any(
                        candidate_graph == graph_iri
                        for _, _, _, candidate_graph in document.quads(
                            (candidate, RDF.predicate, predicate, None)
                        )
                    )
                    and any(
                        candidate_graph == graph_iri
                        for _, _, _, candidate_graph in document.quads(
                            (candidate, RDF.object, obj, None)
                        )
                    )
                    and any(
                        candidate_graph == graph_iri
                        for _, _, _, candidate_graph in document.quads(
                            (
                                candidate,
                                self.status_predicate,
                                Literal("proposed"),
                                None,
                            )
                        )
                    )
                ),
                None,
            )
            if located is None:
                raise AuthoringError(
                    "authoring.draft_not_found", "The draft relation metadata was not found."
                )
            assertion_node, graph_iri = located
            graph = document.graph(graph_iri)
            before = len(graph)
            graph.remove((subject, predicate, obj))
            graph.remove((assertion_node, None, None))
            self._write_dataset(path, document)
        else:
            graph = self._load_graph(path)
            before = len(graph)
            ttl_assertion = next(
                (
                    candidate
                    for candidate in graph.subjects(RDF.subject, subject)
                    if (candidate, RDF.predicate, predicate) in graph
                    and (candidate, RDF.object, obj) in graph
                    and (candidate, self.status_predicate, Literal("proposed")) in graph
                ),
                None,
            )
            if ttl_assertion is None:
                raise AuthoringError(
                    "authoring.draft_not_found", "The draft relation metadata was not found."
                )
            graph.remove((subject, predicate, obj))
            graph.remove((ttl_assertion, None, None))
            self._write_graph(path, graph)
        return self._result("draft_relation_deleted", subject, path, before)

    def _save_structured_resource(self, draft: TermDraft) -> WriteResult:
        subject = self._internal_iri(draft.iri)
        module = self._module(draft.module_id)
        sources = (
            self._shape_sources_for(subject)
            if draft.kind == "node_shape"
            else self.store.source_paths_for(subject)
        )
        if len(sources) > 1:
            raise AuthoringError(
                "authoring.responsible_file_ambiguous",
                "The resource is defined in more than one responsible file.",
            )
        if draft.kind == "ontology":
            path = self.store.knowledge_root / module.source_path / "module.ttl"
        elif draft.kind == "node_shape":
            local = self._safe_local_name(subject)
            path = (
                sources[0]
                if sources
                else self.store.knowledge_root / "shapes/modules" / f"{local}.ttl"
            )
        else:
            path = (
                sources[0]
                if sources
                else self.store.knowledge_root / "competency_questions/questions.ttl"
            )
        path = self._confined(path, allow_missing=True)
        graph = self._load_graph(path)
        existed = any(True for _ in graph.triples((subject, None, None)))
        expected_type = {
            "ontology": OWL.Ontology,
            "node_shape": SH.NodeShape,
            "competency_question": self.competency_type,
        }[draft.kind]
        existing_kind = self._kind_for_types(set(graph.objects(subject, RDF.type)))
        if existed and existing_kind != draft.kind:
            raise AuthoringError(
                "authoring.kind_mismatch",
                "An existing resource cannot change its supported RDF type implicitly.",
            )
        dynamic_fields = self._dynamic_fields(
            draft.kind, draft.form_values, graph=graph, subject=subject
        )
        managed = {
            DCTERMS.isPartOf,
            DCTERMS.creator,
            self.status_predicate,
        }
        if draft.kind == "competency_question":
            self._require_text(draft.question_text_es or "", "question_text_es")
            self._require_text(draft.acceptance_criterion_es or "", "acceptance_criterion_es")
        preserved = sum(
            1
            for _, predicate, _ in graph.triples((subject, None, None))
            if predicate not in managed and predicate != RDF.type
        )
        self._replace_dynamic_fields(graph, subject, dynamic_fields)
        self._replace_iri_nodes(
            graph, subject, DCTERMS.isPartOf, (self._module_iri(module.identifier),)
        )
        self._replace_plain_literals(graph, subject, self.status_predicate, (draft.status,))
        self._replace_plain_literals(graph, subject, DCTERMS.creator, (draft.author,))
        self._replace_language_literals(
            graph, subject, SKOS.prefLabel, (draft.preferred_label_es,), "es"
        )
        self._replace_language_literals(
            graph, subject, SKOS.altLabel, draft.alternative_labels_es, "es"
        )
        self._replace_language_literals(
            graph, subject, SKOS.definition, (draft.definition_es,), "es"
        )
        self._replace_language_literals(graph, subject, DCTERMS.source, (draft.evidence,), "es")
        self._update_timestamp(graph, subject, existed)
        for resource_type in self._editable_primary_types():
            graph.remove((subject, RDF.type, resource_type))
        graph.add((subject, RDF.type, expected_type))
        if draft.kind == "node_shape":
            self._replace_language_literals(
                graph, subject, SH.name, (draft.preferred_label_es,), "es"
            )
            self._replace_language_literals(
                graph, subject, SH.description, (draft.definition_es,), "es"
            )
        elif draft.kind == "competency_question":
            self._replace_language_literals(
                graph,
                subject,
                self.question_text,
                (draft.question_text_es or "",),
                "es",
            )
            self._replace_language_literals(
                graph,
                subject,
                self.acceptance_criterion,
                (draft.acceptance_criterion_es or "",),
                "es",
            )
        self._add_dynamic_fields(graph, subject, dynamic_fields)
        self._write_graph(path, graph)
        return self._result("updated" if existed else "created", subject, path, preserved)

    def _add_property_fields(self, graph: Graph, subject: URIRef, draft: TermDraft) -> None:
        direction = draft.reading_direction_es or ""
        example = draft.valid_example or ""
        self._require_text(direction, "reading_direction_es")
        self._require_text(example, "valid_example")
        self._replace_language_literals(graph, subject, SKOS.scopeNote, (direction,), "es")
        self._replace_language_literals(graph, subject, SKOS.example, (example,), "es")
        self._replace_language_literals(graph, subject, DCTERMS.description, (), "es")
        self._replace_iri_nodes(
            graph,
            subject,
            RDFS.domain,
            (URIRef(draft.domain),) if draft.domain else (),
        )
        self._replace_iri_nodes(
            graph,
            subject,
            RDFS.range,
            (URIRef(draft.range),) if draft.range else (),
        )
        if not draft.domain or not draft.range:
            self._replace_language_literals(
                graph,
                subject,
                DCTERMS.description,
                ("Dominio y rango se posponen hasta contar con evidencia suficiente.",),
                "es",
            )

    def _dynamic_fields(
        self,
        kind: str,
        form_values: tuple[tuple[str, tuple[str, ...]], ...],
        *,
        graph: Graph | None = None,
        subject: URIRef | None = None,
    ) -> tuple[tuple[URIRef, FormField, tuple[str, ...]], ...]:
        standard = self._standard_form_keys()
        schema = FormSchemaService(self.store).schema(kind)
        available = {field.key: field for field in schema.fields if field.key not in standard}
        submitted = dict(form_values)
        unknown = sorted(set(submitted) - set(available))
        if unknown:
            raise AuthoringError(
                "authoring.unknown_form_field",
                "The proposal contains a field outside the supported SHACL form schema.",
                details={"fields": ",".join(unknown)},
            )
        result: list[tuple[URIRef, FormField, tuple[str, ...]]] = []
        for key, field in sorted(available.items()):
            values = tuple(value.strip() for value in submitted.get(key, ()) if value.strip())
            predicate = URIRef(field.path)
            opaque_count = (
                sum(
                    not self._dynamic_node_is_editable(field, value)
                    for value in graph.objects(subject, predicate)
                )
                if graph is not None and subject is not None
                else 0
            )
            effective_count = len(values) + opaque_count
            minimum = field.min_count if field.min_count is not None else int(field.required)
            maximum = field.max_count
            if effective_count < minimum:
                raise AuthoringError(
                    "authoring.required_form_field",
                    f"The SHACL-derived field {key} requires at least {minimum} value(s).",
                    details={"field": key, "min_count": str(minimum)},
                )
            if maximum is not None and effective_count > maximum:
                raise AuthoringError(
                    "authoring.form_field_cardinality",
                    f"The SHACL-derived field {key} accepts at most {maximum} value(s).",
                    details={"field": key, "max_count": str(maximum)},
                )
            if field.allowed_values and any(value not in field.allowed_values for value in values):
                raise AuthoringError(
                    "authoring.form_field_value",
                    f"The SHACL-derived field {key} contains a value outside sh:in.",
                )
            if field.pattern and any(
                re.fullmatch(field.pattern, value) is None for value in values
            ):
                raise AuthoringError(
                    "authoring.form_field_pattern",
                    f"The SHACL-derived field {key} does not match sh:pattern.",
                )
            result.append((predicate, field, values))
        return tuple(result)

    @staticmethod
    def _standard_form_keys() -> set[str]:
        return {
            "iri",
            "label",
            "definition",
            "module_id",
            "status",
            "evidence",
            "author",
            "direction",
            "example",
            "domain",
            "range",
            "class_iri",
            "source_id",
            "question_text",
            "acceptance_criterion",
        }

    @staticmethod
    def _add_dynamic_fields(
        graph: Graph,
        subject: URIRef,
        fields: tuple[tuple[URIRef, FormField, tuple[str, ...]], ...],
    ) -> None:
        for predicate, field, values in fields:
            for value in values:
                if field.input == "iri" or field.class_iri:
                    node: Node = URIRef(value)
                elif field.datatype:
                    node = Literal(value, datatype=URIRef(field.datatype))
                else:
                    node = Literal(value)
                graph.add((subject, predicate, node))

    @staticmethod
    def _dynamic_node_is_editable(field: FormField, node: Node) -> bool:
        """Return whether a form string can reproduce this RDF node exactly."""

        if field.input == "iri" or field.class_iri:
            return isinstance(node, URIRef)
        if field.datatype:
            return (
                isinstance(node, Literal)
                and node.language is None
                and node.datatype == URIRef(field.datatype)
            )
        return isinstance(node, Literal) and node.language is None and node.datatype is None

    @classmethod
    def _replace_dynamic_fields(
        cls,
        graph: Graph,
        subject: URIRef,
        fields: tuple[tuple[URIRef, FormField, tuple[str, ...]], ...],
    ) -> None:
        for predicate, field, _ in fields:
            for node in tuple(graph.objects(subject, predicate)):
                if cls._dynamic_node_is_editable(field, node):
                    graph.remove((subject, predicate, node))

    def _term_path(self, subject: URIRef, module: ModuleDefinition) -> Path:
        local = self._safe_local_name(subject)
        path = self.store.knowledge_root / module.source_path / "terms" / f"{local}.ttl"
        return self._confined(path, allow_missing=True)

    @staticmethod
    def _safe_local_name(subject: URIRef) -> str:
        local = str(subject).rsplit("#", 1)[-1].rstrip("/").rsplit("/", 1)[-1]
        if not LOCAL_NAME.fullmatch(local):
            raise AuthoringError(
                "authoring.invalid_local_name", "The term IRI has an unsafe local name."
            )
        return local

    def _module(self, module_id: str) -> ModuleDefinition:
        module = next(
            (item for item in self.store.discover_modules() if item.identifier == module_id), None
        )
        if module is None:
            raise AuthoringError(
                "authoring.unknown_module", "The responsible module does not exist."
            )
        return module

    def _module_iri(self, module_id: str) -> URIRef:
        return URIRef(f"{self.base}id/module/{module_id}")

    def _internal_iri(self, value: str) -> URIRef:
        if not value.startswith(self.base):
            raise AuthoringError(
                "authoring.external_iri", "New or edited resources must use the internal base IRI."
            )
        return URIRef(value)

    @staticmethod
    def _existing_resource(dataset: Dataset, value: str, role: str) -> URIRef:
        node = URIRef(value)
        if not any(True for _ in dataset.quads((node, None, None, None))) and not any(
            True for _ in dataset.quads((None, None, node, None))
        ):
            raise AuthoringError(
                f"authoring.unknown_{role}",
                f"The selected {role} does not exist.",
                details={role: value},
            )
        return node

    def _validate_domain_range(
        self, dataset: Dataset, subject: URIRef, predicate: URIRef, obj: Node
    ) -> None:
        domains = tuple(self._objects(dataset, predicate, RDFS.domain))
        if domains and not any(self._has(dataset, subject, RDF.type, domain) for domain in domains):
            raise AuthoringError(
                "authoring.domain_mismatch", "The subject does not satisfy the property domain."
            )
        ranges = tuple(self._objects(dataset, predicate, RDFS.range))
        if (
            isinstance(obj, URIRef)
            and ranges
            and not any(self._has(dataset, obj, RDF.type, range_iri) for range_iri in ranges)
        ):
            raise AuthoringError(
                "authoring.range_mismatch", "The object does not satisfy the property range."
            )
        if isinstance(obj, Literal) and ranges and obj.datatype and obj.datatype not in ranges:
            raise AuthoringError(
                "authoring.range_mismatch",
                "The literal datatype does not satisfy the property range.",
            )

    @staticmethod
    def _statement_iri(subject: Node, predicate: Node, obj: Node) -> URIRef:
        """Name proposed reifications deterministically without creating business IRIs."""

        identity = "\x00".join((subject.n3(), predicate.n3(), obj.n3()))
        return URIRef(f"urn:eow:proposal-statement:{sha256(identity.encode()).hexdigest()}")

    @staticmethod
    def _managed_term_predicates() -> frozenset[URIRef]:
        return frozenset(
            (
                DCTERMS.isPartOf,
                DCTERMS.creator,
                RDFS.domain,
                RDFS.range,
            )
        )

    @staticmethod
    def _replace_language_literals(
        graph: Graph,
        subject: URIRef,
        predicate: URIRef,
        values: tuple[str, ...],
        language: str,
    ) -> None:
        """Replace only the editable language projection of a predicate."""

        normalized_language = language.casefold()
        for obj in tuple(graph.objects(subject, predicate)):
            if (
                isinstance(obj, Literal)
                and obj.language is not None
                and obj.language.casefold() == normalized_language
            ):
                graph.remove((subject, predicate, obj))
        for value in sorted({item.strip() for item in values if item.strip()}):
            graph.add((subject, predicate, Literal(value, lang=language)))

    @staticmethod
    def _replace_plain_literals(
        graph: Graph,
        subject: URIRef,
        predicate: URIRef,
        values: tuple[str, ...],
    ) -> None:
        for obj in tuple(graph.objects(subject, predicate)):
            if isinstance(obj, Literal) and obj.language is None and obj.datatype is None:
                graph.remove((subject, predicate, obj))
        for value in sorted({item.strip() for item in values if item.strip()}):
            graph.add((subject, predicate, Literal(value)))

    @staticmethod
    def _replace_iri_nodes(
        graph: Graph,
        subject: URIRef,
        predicate: URIRef,
        values: tuple[URIRef, ...],
    ) -> None:
        for obj in tuple(graph.objects(subject, predicate)):
            if isinstance(obj, URIRef):
                graph.remove((subject, predicate, obj))
        for value in sorted(set(values), key=str):
            graph.add((subject, predicate, value))

    @staticmethod
    def _update_timestamp(graph: Graph, subject: URIRef, existed: bool) -> None:
        today = Literal(date.today().isoformat(), datatype=XSD.date)
        if existed:
            graph.remove((subject, DCTERMS.modified, None))
            graph.add((subject, DCTERMS.modified, today))
            return
        graph.add((subject, DCTERMS.created, today))

    def _published_triple(self, path: Path, subject: Node, predicate: Node, obj: Node) -> bool:
        payload = self._require_workspace().base_file(path)
        if payload is None:
            return False
        try:
            if path.suffix.lower() == ".trig":
                document = Dataset().parse(data=payload.decode("utf-8"), format="trig")
                return any(True for _ in document.quads((subject, predicate, obj, None)))
            graph = Graph().parse(data=payload.decode("utf-8"), format="turtle")
            return (subject, predicate, obj) in graph
        except Exception as error:  # noqa: BLE001 - fail closed on malformed published RDF
            raise AuthoringError(
                "authoring.base_parse_failed",
                "The published source file could not be checked safely.",
            ) from error

    def _editable_primary_types(self) -> frozenset[URIRef]:
        return TERM_RDF_TYPES | frozenset(
            (OWL.Ontology, OWL.NamedIndividual, SH.NodeShape, self.competency_type)
        )

    def _kind_for_types(self, types: set[Node]) -> str | None:
        mapping = {
            OWL.Ontology: "ontology",
            OWL.Class: "class",
            OWL.ObjectProperty: "object_property",
            OWL.DatatypeProperty: "datatype_property",
            OWL.AnnotationProperty: "annotation_property",
            OWL.NamedIndividual: "individual",
            SKOS.Concept: "concept",
            SH.NodeShape: "node_shape",
            self.competency_type: "competency_question",
        }
        matches = {kind for rdf_type, kind in mapping.items() if rdf_type in types}
        return next(iter(matches)) if len(matches) == 1 else None

    @staticmethod
    def _language_texts(
        dataset: Dataset, subject: Node, predicate: Node, language: str
    ) -> tuple[str, ...]:
        normalized_language = language.casefold()
        return tuple(
            sorted(
                str(value)
                for value in TermWriter._objects(dataset, subject, predicate)
                if isinstance(value, Literal)
                and value.language is not None
                and value.language.casefold() == normalized_language
            )
        )

    @staticmethod
    def _language_text(dataset: Dataset, subject: Node, predicate: Node, language: str) -> str:
        values = TermWriter._language_texts(dataset, subject, predicate, language)
        return values[0] if values else ""

    def _shape_sources_for(self, subject: URIRef) -> tuple[Path, ...]:
        sources: list[Path] = []
        for path in self.store.discover_shape_files():
            graph = Graph().parse(path, format="turtle")
            if any(True for _ in graph.triples((subject, None, None))):
                sources.append(path)
        return tuple(sorted(sources))

    @staticmethod
    def _first_text(dataset: Dataset, subject: Node, predicate: Node) -> str:
        values = sorted(map(str, TermWriter._objects(dataset, subject, predicate)))
        return values[0] if values else ""

    @staticmethod
    def _first_iri(dataset: Dataset, subject: Node, predicate: Node) -> str:
        values = sorted(
            str(value)
            for value in TermWriter._objects(dataset, subject, predicate)
            if isinstance(value, URIRef)
        )
        return values[0] if values else ""

    def _load_graph(self, path: Path) -> Graph:
        path = self._confined(path, allow_missing=True)
        graph = Graph()
        for prefix, namespace in sorted(self.store.namespace_configuration.prefixes.items()):
            graph.bind(prefix, namespace, replace=True)
        if path.is_symlink():
            raise AuthoringError(
                "authoring.unsafe_path", "Responsible files must be regular local files."
            )
        if path.exists():
            if not path.is_file():
                raise AuthoringError(
                    "authoring.unsafe_path", "Responsible files must be regular local files."
                )
            graph.parse(path, format="turtle")
        return graph

    def _write_graph(self, path: Path, graph: Graph) -> None:
        path = self._confined(path, allow_missing=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise AuthoringError(
                "authoring.unsafe_path", "Refusing to replace a non-regular RDF file."
            )
        self._atomic_write(path, graph.serialize(format="turtle"))

    def _load_dataset(self, path: Path) -> Dataset:
        path = self._confined(path, allow_missing=False)
        if path.is_symlink() or not path.is_file():
            raise AuthoringError(
                "authoring.unsafe_path", "Responsible files must be regular local files."
            )
        dataset = Dataset()
        dataset.parse(path, format="trig")
        return dataset

    def _write_dataset(self, path: Path, dataset: Dataset) -> None:
        path = self._confined(path, allow_missing=False)
        if path.is_symlink() or not path.is_file():
            raise AuthoringError(
                "authoring.unsafe_path", "Refusing to replace a non-regular RDF file."
            )
        self._atomic_write(path, dataset.serialize(format="trig"))

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _confined(self, path: Path, *, allow_missing: bool) -> Path:
        try:
            resolved_parent = path.parent.resolve(strict=True)
        except FileNotFoundError:
            if not allow_missing:
                raise
            ancestor = path.parent
            while not ancestor.exists():
                ancestor = ancestor.parent
            resolved_ancestor = ancestor.resolve(strict=True)
            if not resolved_ancestor.is_relative_to(self.store.knowledge_root):
                raise AuthoringError(
                    "authoring.path_escape", "The RDF path escapes knowledge/."
                ) from None
            return path
        resolved = resolved_parent / path.name
        if not resolved.is_relative_to(self.store.knowledge_root):
            raise AuthoringError("authoring.path_escape", "The RDF path escapes knowledge/.")
        return resolved

    @staticmethod
    def _require_text(value: str, field: str) -> None:
        if not value.strip():
            raise AuthoringError(
                "authoring.required_field", f"{field} is required.", details={"field": field}
            )

    @staticmethod
    def _copy_dataset(dataset: Dataset) -> Dataset:
        candidate = Dataset()
        for subject, predicate, obj, graph in dataset.quads((None, None, None, None)):
            if graph is not None:
                candidate.graph(graph).add((subject, predicate, obj))
        return candidate

    @staticmethod
    def _objects(dataset: Dataset, subject: Node, predicate: Node) -> tuple[Node, ...]:
        return tuple(
            sorted(
                {obj for _, _, obj, _ in dataset.quads((subject, predicate, None, None))},
                key=lambda node: (type(node).__name__, str(node)),
            )
        )

    @staticmethod
    def _has(dataset: Dataset, subject: Node, predicate: Node, obj: Node) -> bool:
        return any(True for _ in dataset.quads((subject, predicate, obj, None)))

    def _require_workspace(self) -> GitWorkspaceService:
        if self.workspace is None:
            raise AuthoringError(
                "authoring.workspace_required",
                "This write operation requires a Git workspace.",
            )
        return self.workspace

    def _repository_root(self) -> Path:
        if self.workspace is not None:
            return self.workspace.repository_root
        return self.store.knowledge_root.parent

    def _result(self, operation: str, resource: URIRef, path: Path, preserved: int) -> WriteResult:
        return WriteResult(
            operation=operation,
            resource=str(resource),
            path=path.relative_to(self._repository_root()).as_posix(),
            preserved_unknown_triples=preserved,
        )

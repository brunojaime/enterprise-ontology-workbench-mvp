"""Deterministic authoring schemas derived from the supported SHACL subset."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from typing import Literal as TypingLiteral

from rdflib import Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, SH, SKOS, XSD
from rdflib.term import Node

from ontology_core.store import FilesystemRdfStore

FormInput = TypingLiteral["text", "textarea", "iri", "select", "number", "checkbox"]


@dataclass(frozen=True)
class FormField:
    key: str
    path: str
    name: str
    description: str | None
    input: FormInput
    required: bool = False
    multiple: bool = True
    min_count: int | None = None
    max_count: int | None = None
    datatype: str | None = None
    class_iri: str | None = None
    allowed_values: tuple[str, ...] = ()
    pattern: str | None = None
    message: str | None = None
    severity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "path": self.path,
            "name": self.name,
            "description": self.description,
            "input": self.input,
            "required": self.required,
            "multiple": self.multiple,
            "min_count": self.min_count,
            "max_count": self.max_count,
            "datatype": self.datatype,
            "class_iri": self.class_iri,
            "allowed_values": list(self.allowed_values),
            "pattern": self.pattern,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class FormSchema:
    kind: str
    rdf_type: str
    name: str
    fields: tuple[FormField, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "rdf_type": self.rdf_type,
            "name": self.name,
            "fields": [field.to_dict() for field in self.fields],
        }


class FormSchemaService:
    """Translate the section 28 SHACL subset into stable JSON-ready schemas."""

    RESOURCE_TYPES = (
        ("ontology", OWL.Ontology, "Módulo ontológico"),
        ("class", OWL.Class, "Clase OWL"),
        ("object_property", OWL.ObjectProperty, "Object property"),
        ("datatype_property", OWL.DatatypeProperty, "Datatype property"),
        ("annotation_property", OWL.AnnotationProperty, "Annotation property"),
        ("individual", OWL.NamedIndividual, "Named individual"),
        ("concept", SKOS.Concept, "Concepto SKOS"),
        ("node_shape", SH.NodeShape, "Node shape SHACL"),
    )

    def __init__(self, store: FilesystemRdfStore) -> None:
        self.store = store
        self.base = store.namespace_configuration.base
        self.status_path = URIRef(f"{self.base}ontology/core#status")
        self.competency_type = URIRef(f"{self.base}ontology/competency#CompetencyQuestion")
        self.question_text = URIRef(f"{self.base}ontology/competency#questionText")
        self.acceptance_criterion = URIRef(f"{self.base}ontology/competency#acceptanceCriterion")

    def schemas(self, *, shapes: Graph | None = None) -> tuple[FormSchema, ...]:
        graph = shapes if shapes is not None else self.store.load_shape_catalog().graph
        resource_types = (
            *self.RESOURCE_TYPES,
            ("competency_question", self.competency_type, "Pregunta de competencia"),
        )
        return tuple(
            self._schema(kind, rdf_type, name, graph) for kind, rdf_type, name in resource_types
        )

    def schema(self, kind: str, *, shapes: Graph | None = None) -> FormSchema:
        match = next(
            (schema for schema in self.schemas(shapes=shapes) if schema.kind == kind), None
        )
        if match is None:
            raise ValueError(f"unsupported authoring kind: {kind}")
        return match

    def _schema(self, kind: str, rdf_type: URIRef, name: str, shapes: Graph) -> FormSchema:
        fields = {field.path: field for field in self._base_fields(kind)}
        for shape in sorted(shapes.subjects(SH.targetClass, rdf_type), key=str):
            for property_shape in sorted(shapes.objects(shape, SH.property), key=str):
                translated = self._translate_property(shapes, property_shape)
                if translated is None:
                    continue
                previous = fields.get(translated.path)
                fields[translated.path] = self._merge(previous, translated)
        return FormSchema(
            kind=kind,
            rdf_type=str(rdf_type),
            name=name,
            fields=tuple(sorted(fields.values(), key=lambda field: self._field_order(field.key))),
        )

    def _translate_property(self, graph: Graph, node: Node) -> FormField | None:
        paths = tuple(graph.objects(node, SH.path))
        if len(paths) != 1 or not isinstance(paths[0], URIRef):
            return None
        path = paths[0]
        datatype = self._single_iri(graph, node, SH.datatype)
        class_iri = self._single_iri(graph, node, SH["class"])
        allowed_head = next(iter(graph.objects(node, SH["in"])), None)
        allowed = self._rdf_list(graph, allowed_head)
        min_count = self._integer(graph, node, SH.minCount)
        max_count = self._integer(graph, node, SH.maxCount)
        key = self._key(path)
        return FormField(
            key=key,
            path=str(path),
            name=self._text(graph, node, SH.name) or self._default_name(key),
            description=self._text(graph, node, SH.description),
            input=self._input(datatype, class_iri, allowed),
            required=bool(min_count and min_count > 0),
            multiple=max_count != 1,
            min_count=min_count,
            max_count=max_count,
            datatype=datatype,
            class_iri=class_iri,
            allowed_values=allowed,
            pattern=self._text(graph, node, SH.pattern),
            message=self._text(graph, node, SH.message),
            severity=self._single_iri(graph, node, SH.severity),
        )

    def _base_fields(self, kind: str) -> tuple[FormField, ...]:
        common: tuple[FormField, ...] = (
            self._field("iri", RDF.subject, "IRI completa", "iri", required=True, multiple=False),
            self._field(
                "label",
                SKOS.prefLabel,
                "Etiqueta preferida (es)",
                "text",
                required=True,
                multiple=False,
            ),
            self._field(
                "status",
                self.status_path,
                "Estado",
                "select",
                required=True,
                multiple=False,
                allowed=("proposed", "active", "deprecated"),
            ),
            self._field(
                "evidence", DCTERMS.source, "Evidencia", "textarea", required=True, multiple=False
            ),
            self._field(
                "author", DCTERMS.creator, "Autoría", "text", required=True, multiple=False
            ),
        )
        if kind != "individual":
            common += (
                self._field(
                    "definition",
                    SKOS.definition,
                    "Definición",
                    "textarea",
                    required=True,
                    multiple=False,
                ),
                self._field(
                    "module_id",
                    DCTERMS.isPartOf,
                    "Módulo responsable",
                    "iri",
                    required=True,
                    multiple=False,
                ),
            )
        extras: tuple[FormField, ...] = ()
        if kind.endswith("_property"):
            extras = (
                self._field(
                    "direction",
                    SKOS.scopeNote,
                    "Dirección de lectura",
                    "textarea",
                    required=True,
                    multiple=False,
                ),
                self._field(
                    "example",
                    SKOS.example,
                    "Ejemplo válido",
                    "textarea",
                    required=True,
                    multiple=False,
                ),
                self._field(
                    "domain",
                    URIRef("http://www.w3.org/2000/01/rdf-schema#domain"),
                    "Dominio",
                    "iri",
                    multiple=False,
                ),
                self._field(
                    "range",
                    URIRef("http://www.w3.org/2000/01/rdf-schema#range"),
                    "Rango",
                    "iri",
                    multiple=False,
                ),
            )
        elif kind == "individual":
            extras = (
                self._field(
                    "class_iri", RDF.type, "Clase existente", "iri", required=True, multiple=False
                ),
                self._field(
                    "source_id",
                    DCTERMS.identifier,
                    "Fuente (slug)",
                    "text",
                    required=True,
                    multiple=False,
                    pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
                ),
            )
        elif kind == "competency_question":
            extras = (
                self._field(
                    "question_text",
                    self.question_text,
                    "Pregunta",
                    "textarea",
                    required=True,
                    multiple=False,
                ),
                self._field(
                    "acceptance_criterion",
                    self.acceptance_criterion,
                    "Criterio de aceptación",
                    "textarea",
                    required=True,
                    multiple=False,
                ),
            )
        return common + extras

    def _field(
        self,
        key: str,
        path: URIRef,
        name: str,
        input_type: FormInput,
        *,
        required: bool = False,
        multiple: bool = True,
        allowed: tuple[str, ...] = (),
        pattern: str | None = None,
    ) -> FormField:
        return FormField(
            key,
            str(path),
            name,
            None,
            input_type,
            required,
            multiple,
            min_count=1 if required else 0,
            max_count=None if multiple else 1,
            allowed_values=allowed,
            pattern=pattern,
        )

    @staticmethod
    def _merge(previous: FormField | None, current: FormField) -> FormField:
        if previous is None:
            return current
        minimums = tuple(
            value for value in (previous.min_count, current.min_count) if value is not None
        )
        maximums = tuple(
            value for value in (previous.max_count, current.max_count) if value is not None
        )
        min_count = max(minimums) if minimums else None
        max_count = min(maximums) if maximums else None
        return replace(
            previous,
            name=current.name or previous.name,
            description=current.description or previous.description,
            input=current.input,
            required=bool(min_count and min_count > 0),
            multiple=max_count is None or max_count > 1,
            min_count=min_count,
            max_count=max_count,
            datatype=current.datatype or previous.datatype,
            class_iri=current.class_iri or previous.class_iri,
            allowed_values=current.allowed_values or previous.allowed_values,
            pattern=current.pattern or previous.pattern,
            message=current.message or previous.message,
            severity=current.severity or previous.severity,
        )

    def _key(self, path: URIRef) -> str:
        mapping = {
            str(SKOS.prefLabel): "label",
            str(SKOS.definition): "definition",
            str(SKOS.scopeNote): "direction",
            str(SKOS.example): "example",
            str(DCTERMS.isPartOf): "module_id",
            str(DCTERMS.source): "evidence",
            str(DCTERMS.creator): "author",
            str(self.status_path): "status",
            str(self.question_text): "question_text",
            str(self.acceptance_criterion): "acceptance_criterion",
        }
        return mapping.get(str(path), str(path).rsplit("#", 1)[-1].rsplit("/", 1)[-1])

    @staticmethod
    def _input(datatype: str | None, class_iri: str | None, allowed: tuple[str, ...]) -> FormInput:
        if allowed:
            return "select"
        if class_iri:
            return "iri"
        if datatype == str(XSD.boolean):
            return "checkbox"
        if datatype in {str(XSD.integer), str(XSD.decimal), str(XSD.float), str(XSD.double)}:
            return "number"
        return "text"

    @staticmethod
    def _rdf_list(graph: Graph, head: Node | None) -> tuple[str, ...]:
        if head is None:
            return ()
        try:
            return tuple(str(value) for value in Collection(graph, head))
        except (KeyError, ValueError):
            return ()

    @staticmethod
    def _single_iri(graph: Graph, node: Node, predicate: URIRef) -> str | None:
        values = tuple(graph.objects(node, predicate))
        return str(values[0]) if len(values) == 1 and isinstance(values[0], URIRef) else None

    @staticmethod
    def _integer(graph: Graph, node: Node, predicate: URIRef) -> int | None:
        values = tuple(graph.objects(node, predicate))
        if len(values) != 1 or not isinstance(values[0], Literal):
            return None
        try:
            return int(values[0])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _text(graph: Graph, node: Node, predicate: URIRef) -> str | None:
        values = sorted(str(value) for value in graph.objects(node, predicate))
        return values[0] if values else None

    @staticmethod
    def _default_name(key: str) -> str:
        return key.replace("_", " ").capitalize()

    @staticmethod
    def _field_order(key: str) -> tuple[int, str]:
        order = (
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
        )
        return (order.index(key) if key in order else len(order), key)

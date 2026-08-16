"""Strict MCP input models shared by schema generation and runtime validation."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

NonEmpty = Annotated[StrictStr, Field(min_length=1, max_length=2048)]
ShortText = Annotated[StrictStr, Field(min_length=1, max_length=500)]
Limit = Annotated[StrictInt, Field(ge=1, le=500)]
Offset = Annotated[StrictInt, Field(ge=0, le=1_000_000)]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyInput(StrictInput):
    pass


class SearchInput(StrictInput):
    text: ShortText
    limit: Limit = 50
    offset: Offset = 0
    rdf_types: list[NonEmpty] = Field(default_factory=list, max_length=20)
    modules: list[NonEmpty] = Field(default_factory=list, max_length=20)


class DescribeInput(StrictInput):
    iri: NonEmpty
    depth: Annotated[StrictInt, Field(ge=0, le=5)] = 1
    max_nodes: Annotated[StrictInt, Field(ge=1, le=500)] = 100
    max_edges: Annotated[StrictInt, Field(ge=0, le=1500)] = 300


class ContextInput(StrictInput):
    task: ShortText
    terms: list[NonEmpty] = Field(default_factory=list, max_length=100)
    modules: list[NonEmpty] = Field(default_factory=list, max_length=50)
    max_terms: Annotated[StrictInt, Field(ge=1, le=500)] = 80
    depth: Annotated[StrictInt, Field(ge=0, le=5)] = 2
    max_bytes: Annotated[StrictInt, Field(ge=4096, le=1_048_576)] = 65_536


class DiffInput(StrictInput):
    base: Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")] = "main"


class TermInput(StrictInput):
    agent: ShortText
    iri: NonEmpty
    module_id: Annotated[StrictStr, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
    kind: Literal[
        "class",
        "concept",
        "object_property",
        "datatype_property",
        "annotation_property",
        "individual",
        "ontology",
        "node_shape",
        "competency_question",
    ]
    preferred_label_es: ShortText
    definition_es: Annotated[StrictStr, Field(max_length=5000)] = ""
    evidence: Annotated[StrictStr, Field(min_length=1, max_length=5000)]
    author: ShortText
    search_query: ShortText
    search_id: Annotated[
        StrictStr,
        Field(pattern=r"^eow-search-v2:[A-Za-z0-9_-]+\.[0-9a-f]{64}$"),
    ]
    search_confirmed: StrictBool
    alternative_labels_es: list[ShortText] = Field(default_factory=list, max_length=100)
    status: Literal["proposed", "active", "deprecated"] = "proposed"
    reading_direction_es: Annotated[StrictStr, Field(max_length=2000)] | None = None
    valid_example: Annotated[StrictStr, Field(max_length=2000)] | None = None
    domain: NonEmpty | None = None
    range: NonEmpty | None = None
    class_iri: NonEmpty | None = None
    source_id: Annotated[StrictStr, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")] | None = None
    question_text_es: Annotated[StrictStr, Field(max_length=2000)] | None = None
    acceptance_criterion_es: Annotated[StrictStr, Field(max_length=2000)] | None = None
    form_values: dict[NonEmpty, list[NonEmpty]] = Field(default_factory=dict, max_length=100)


class RelationInput(StrictInput):
    agent: ShortText
    subject: NonEmpty
    predicate: NonEmpty
    object_iri: NonEmpty | None = None
    literal: Annotated[StrictStr, Field(max_length=10_000)] | None = None
    datatype: NonEmpty | None = None
    language: (
        Annotated[StrictStr, Field(pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")] | None
    ) = None
    evidence: Annotated[StrictStr, Field(min_length=1, max_length=5000)]
    status: Literal["proposed"] = "proposed"


class DeprecateInput(StrictInput):
    agent: ShortText
    iri: NonEmpty
    reason: Annotated[StrictStr, Field(min_length=1, max_length=5000)]
    replacement_iri: NonEmpty | None = None

"""Pydantic HTTP contracts generated into the frontend client from OpenAPI."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthModel(StrictModel):
    status: Literal["ok"]


class OperationalCheckModel(StrictModel):
    status: Literal["pass", "fail"]
    detail: str


class ReadinessModel(StrictModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, OperationalCheckModel]
    generation: int
    loaded_at: str


class OperationMetricModel(StrictModel):
    count: int = Field(ge=0)
    failures: int = Field(ge=0)
    total_duration_ms: float = Field(ge=0)
    last_duration_ms: float | None = Field(default=None, ge=0)


class OperationalMetricsModel(StrictModel):
    load: OperationMetricModel
    validation: OperationMetricModel
    query: OperationMetricModel


class RdfValueModel(StrictModel):
    kind: Literal["iri", "bnode", "literal"]
    value: str
    compact: str | None = None
    datatype: str | None = None
    language: str | None = None


class GraphNodeModel(RdfValueModel):
    category: Literal[
        "class",
        "property",
        "individual",
        "concept",
        "shape",
        "module",
        "literal",
        "resource",
    ]
    module: str | None = None


class QuadModel(StrictModel):
    subject: RdfValueModel
    predicate: RdfValueModel
    object: RdfValueModel
    graph: RdfValueModel
    relationship_kind: Literal[
        "subclass",
        "subproperty",
        "domain",
        "range",
        "import",
        "internal_object_property",
        "other",
    ] = "other"
    priority: int = Field(default=7, ge=1, le=7)
    status: str | None = None


class SearchResultModel(StrictModel):
    iri: str
    compact_iri: str
    local_name: str
    label: str | None
    types: list[str]
    modules: list[str]
    matched_fields: list[str]
    score: int


class SearchPageModel(StrictModel):
    items: list[SearchResultModel]
    total: int
    offset: int
    limit: int
    has_next: bool
    search_id: str = Field(pattern=r"^eow-search-v2:[A-Za-z0-9_-]+\.[0-9a-f]{64}$")


class ResourceDescriptionModel(StrictModel):
    resource: RdfValueModel
    types: list[RdfValueModel]
    labels: list[RdfValueModel]
    definitions: list[RdfValueModel]
    modules: list[RdfValueModel]
    direct_modules: list[RdfValueModel]
    status: list[RdfValueModel]
    outgoing: list[QuadModel]
    incoming: list[QuadModel]
    superclasses: list[RdfValueModel]
    subclasses: list[RdfValueModel]
    domains: list[RdfValueModel]
    ranges: list[RdfValueModel]
    shapes: list[RdfValueModel]
    provenance: list[QuadModel]
    predicate_uses: list[QuadModel]
    usage: ResourceUsageModel
    git_history: list[GitHistoryEntryModel]


class ResourceUsageModel(StrictModel):
    incoming_references: int
    outgoing_statements: int
    predicate_uses: int


class GitHistoryEntryModel(StrictModel):
    commit: str
    author: str
    date: str
    subject: str
    path: str


class NeighborhoodModel(StrictModel):
    center: GraphNodeModel
    depth: int
    nodes: list[GraphNodeModel]
    edges: list[QuadModel]
    truncated: bool


class ModuleStatsModel(StrictModel):
    module_id: str
    graph_iri: str
    quads: int
    resources: int
    types: dict[str, int]


class DatasetStatsModel(StrictModel):
    quads: int
    named_graphs: int
    resources: int
    types: dict[str, int]
    modules: list[ModuleStatsModel]


class ModuleModel(StrictModel):
    id: str
    ontology_iri: str
    graph_iri: str
    source_path: str
    imports: list[str]
    labels: list[RdfValueModel]
    definitions: list[RdfValueModel]
    responsible: list[RdfValueModel]
    status: list[RdfValueModel]
    classes: list[RdfValueModel]
    properties: list[RdfValueModel]
    term_total: int
    term_offset: int
    term_limit: int
    terms_has_next: bool
    import_cycles: list[list[str]]
    term_count: int
    competency_question_count: int


class ModulePageModel(StrictModel):
    items: list[ModuleModel]
    total: int
    offset: int
    limit: int
    has_next: bool


class ModuleGraphModel(StrictModel):
    module_id: str
    graph_iri: str
    total: int
    offset: int
    limit: int
    truncated: bool
    quads: list[QuadModel]


class ValidationIssueModel(StrictModel):
    source: str
    rule_id: str
    severity: str
    message: str
    resource: str | None
    resource_type: str | None
    path: str | None
    graph: str | None
    details: dict[str, str]


class ValidationReportModel(StrictModel):
    conforms: bool
    counts: dict[str, int]
    issues: list[ValidationIssueModel]


class ImpactModel(StrictModel):
    resource: RdfValueModel
    incoming: list[QuadModel]
    outgoing: list[QuadModel]
    predicate_uses: list[QuadModel]
    ancestors: list[RdfValueModel]
    descendants: list[RdfValueModel]
    shapes: list[RdfValueModel]
    competency_questions: list[RdfValueModel]
    import_dependencies: list[RdfValueModel]
    affected_importers: list[RdfValueModel]


class SparqlRequest(StrictModel):
    query: str = Field(min_length=1, max_length=65536)
    timeout_seconds: float = Field(default=5.0, gt=0, le=10)
    max_results: int = Field(default=1000, ge=1, le=5000)


class SparqlResultModel(StrictModel):
    kind: Literal["select", "ask", "construct", "describe"]
    variables: list[str]
    rows: list[list[RdfValueModel | None]]
    boolean: bool | None
    triples: list[list[RdfValueModel]]
    truncated: bool


class CompetencyQuestionModel(StrictModel):
    iri: str
    text: str
    module: str
    state: str
    query_file: str | None
    expected_boolean: bool | None
    minimum_result_count: int | None
    acceptance_criterion: str | None


class CompetencyQuestionPageModel(StrictModel):
    items: list[CompetencyQuestionModel]
    total: int
    offset: int
    limit: int
    has_next: bool


class CompetencyRunRequest(StrictModel):
    iri: str | None = None


class CompetencyResultModel(StrictModel):
    question: CompetencyQuestionModel
    status: Literal["passed", "failed", "not_executable"]
    reason: str
    result: SparqlResultModel | None


class ContextRequestModel(StrictModel):
    task: str = Field(min_length=1)
    terms: list[str] = Field(default_factory=list, max_length=500)
    modules: list[str] = Field(default_factory=list, max_length=100)
    max_terms: int = Field(default=80, ge=1, le=500)
    depth: int = Field(default=2, ge=0, le=5)
    max_bytes: int = Field(default=65536, ge=4096, le=1048576)


class ContextResponseModel(StrictModel):
    payload: dict[str, Any]
    json_text: str = Field(alias="json")
    markdown: str
    truncated: bool


class RepositoryRevisionModel(StrictModel):
    branch: str | None
    commit: str | None
    dirty: bool


class RuntimeStatusModel(StrictModel):
    ready: bool
    generation: int
    loaded_at: str
    revision: RepositoryRevisionModel
    quads: int
    modules: int
    validation_conforms: bool


class WorkspaceModel(StrictModel):
    runtime: RuntimeStatusModel
    stats: DatasetStatsModel
    validation: ValidationReportModel
    competency_questions: int
    agent_contract_status: Literal["synchronized", "stale", "not_available"]
    branch: str | None
    commit: str | None
    pending_changes: bool
    module_count: int
    class_count: int
    property_count: int
    concept_count: int
    individual_count: int
    validation_conforms: bool


class AgentRuleModel(StrictModel):
    id: str
    source: str
    content: str


class AgentSkillStatusModel(StrictModel):
    available: list[str]
    status: Literal["synchronized", "stale"]
    version: str


class AgentStatusModel(StrictModel):
    context_available: bool
    rules_available: bool
    skills_available: bool
    canonical_contract_available: bool
    version: str
    digest: str
    synchronized: bool
    stale: list[str]
    generated: list[str]
    mcp_status: Literal["available_stdio"]
    cli_commands: list[str]
    validation_conforms: bool


class SearchConfirmationModel(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    confirmed: bool
    search_id: str = Field(pattern=r"^eow-search-v2:[A-Za-z0-9_-]+\.[0-9a-f]{64}$")


class TermWriteRequest(StrictModel):
    iri: str = Field(min_length=1, max_length=2048)
    module_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    kind: Literal[
        "ontology",
        "class",
        "concept",
        "object_property",
        "datatype_property",
        "annotation_property",
        "node_shape",
        "competency_question",
    ]
    preferred_label_es: str = Field(min_length=1, max_length=500)
    alternative_labels_es: list[str] = Field(default_factory=list, max_length=100)
    definition_es: str = Field(min_length=1, max_length=5000)
    evidence: str = Field(min_length=1, max_length=5000)
    author: str = Field(min_length=1, max_length=500)
    search: SearchConfirmationModel
    status: Literal["proposed", "active", "deprecated"] = "proposed"
    reading_direction_es: str | None = Field(default=None, max_length=2000)
    valid_example: str | None = Field(default=None, max_length=2000)
    domain: str | None = Field(default=None, max_length=2048)
    range: str | None = Field(default=None, max_length=2048)
    question_text_es: str | None = Field(default=None, max_length=5000)
    acceptance_criterion_es: str | None = Field(default=None, max_length=5000)
    form_values: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict,
        max_length=100,
    )


class EditableResourceModel(StrictModel):
    iri: str
    kind: str
    preferred_label_es: str
    alternative_labels_es: list[str]
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
    form_values: dict[str, list[str]]
    path: str


class FormFieldModel(StrictModel):
    key: str
    path: str
    name: str
    description: str | None
    input: Literal["text", "textarea", "iri", "select", "number", "checkbox"]
    required: bool
    multiple: bool
    min_count: int | None = Field(ge=0)
    max_count: int | None = Field(ge=0)
    datatype: str | None
    class_iri: str | None
    allowed_values: list[str]
    pattern: str | None
    message: str | None
    severity: str | None


class FormSchemaModel(StrictModel):
    kind: str
    rdf_type: str
    name: str
    fields: list[FormFieldModel]


class IndividualWriteRequest(StrictModel):
    iri: str = Field(min_length=1, max_length=2048)
    class_iri: str = Field(min_length=1, max_length=2048)
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    preferred_label_es: str = Field(min_length=1, max_length=500)
    alternative_labels_es: list[str] = Field(default_factory=list, max_length=100)
    evidence: str = Field(min_length=1, max_length=5000)
    author: str = Field(min_length=1, max_length=500)
    search: SearchConfirmationModel
    status: Literal["proposed", "active", "deprecated"] = "proposed"
    form_values: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict,
        max_length=100,
    )


class WriteResultModel(StrictModel):
    operation: str
    resource: str
    path: str
    preserved_unknown_triples: int


class RelationWriteRequest(StrictModel):
    subject: str = Field(min_length=1, max_length=2048)
    predicate: str = Field(min_length=1, max_length=2048)
    object_iri: str | None = Field(default=None, max_length=2048)
    literal: str | None = Field(default=None, max_length=10000)
    datatype: str | None = Field(default=None, max_length=2048)
    language: str | None = Field(default=None, max_length=64)
    evidence: str = Field(min_length=1, max_length=5000)
    status: Literal["proposed", "active", "deprecated"] = "proposed"


class RelationDeleteRequest(StrictModel):
    subject: str = Field(min_length=1, max_length=2048)
    predicate: str = Field(min_length=1, max_length=2048)
    object_iri: str | None = Field(default=None, max_length=2048)
    literal: str | None = Field(default=None, max_length=10000)
    datatype: str | None = Field(default=None, max_length=2048)
    language: str | None = Field(default=None, max_length=64)


class DeprecationRequest(StrictModel):
    iri: str = Field(min_length=1, max_length=2048)
    reason: str = Field(min_length=1, max_length=5000)
    replacement_iri: str | None = Field(default=None, max_length=2048)


class GitCommitModel(StrictModel):
    commit: str
    author: str
    date: str
    subject: str


class GitStatusModel(StrictModel):
    repository_root: str
    branch: str | None
    head: str | None
    base_branch: str
    base_commit: str | None
    dirty: bool
    changed_paths: list[str]
    proposal_commits: list[GitCommitModel]
    proposal_branches: list[str]
    editable: bool


class BranchRequest(StrictModel):
    branch: str = Field(min_length=1, max_length=72)
    create: bool = False


class CommitRequest(StrictModel):
    module: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=5, max_length=72)
    exception_reason: str | None = Field(default=None, max_length=5000)


class CommitResultModel(StrictModel):
    commit: str
    subject: str
    paths: list[str]
    validation_conforms: bool
    exception_reason: str | None


class PullRequestRequest(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    draft: bool = True


class PullRequestResultModel(StrictModel):
    status: str
    url: str | None
    reason: str | None


class SemanticQuadModel(StrictModel):
    subject: RdfValueModel
    predicate: RdfValueModel
    object: RdfValueModel
    graph: RdfValueModel
    category: Literal[
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


class ResourceChangeModel(StrictModel):
    resource: RdfValueModel
    categories: list[str]
    added: list[SemanticQuadModel]
    removed: list[SemanticQuadModel]


class SemanticDiffModel(StrictModel):
    base: str
    head: str
    added_resources: list[RdfValueModel]
    modified_resources: list[RdfValueModel]
    deprecated_resources: list[RdfValueModel]
    added_quads: list[SemanticQuadModel]
    removed_quads: list[SemanticQuadModel]
    changes: list[ResourceChangeModel]
    affected_modules: list[str]
    potentially_impacted_questions: list[RdfValueModel]


class ProposalReviewModel(StrictModel):
    diff: SemanticDiffModel
    validation: ValidationReportModel
    impact: dict[str, dict[str, Any]]
    evidence: list[SemanticQuadModel]
    ready_to_commit: bool

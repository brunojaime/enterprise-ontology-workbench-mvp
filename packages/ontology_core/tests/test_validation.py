from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

import pytest
from ontology_core import (
    FilesystemRdfStore,
    RdfLoadLimits,
    SemanticLinter,
    ValidationContext,
    ValidationIssue,
    ValidationReport,
    ValidationResourceType,
    ValidationService,
    ValidationSeverity,
    ValidationSource,
)
from pyshacl.errors import ConstraintLoadError, ReportableRuntimeError, ShapeLoadError
from rdflib import BNode, Dataset, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, SH, SKOS

REPOSITORY_ROOT = Path(__file__).parents[3]
KNOWLEDGE_ROOT = REPOSITORY_ROOT / "knowledge"
NAMESPACE_CONFIG = REPOSITORY_ROOT / "config" / "namespace.yaml"
VALIDATION_FIXTURES = REPOSITORY_ROOT / "fixtures" / "validation"
BASE = "https://knowledge.example.com/"
EOW = Namespace(f"{BASE}ontology/core#")


def make_store(knowledge_root: Path = KNOWLEDGE_ROOT) -> FilesystemRdfStore:
    return FilesystemRdfStore(knowledge_root, NAMESPACE_CONFIG)


def make_service(knowledge_root: Path = KNOWLEDGE_ROOT) -> ValidationService:
    return ValidationService(make_store(knowledge_root))


def dataset_from_fixture(relative_path: str) -> Dataset:
    path = VALIDATION_FIXTURES / relative_path
    dataset = Dataset()
    if path.suffix == ".trig":
        dataset.parse(path, format="trig")
    else:
        dataset.graph(URIRef(f"{BASE}graph/test/{path.parent.name}/{path.stem}")).parse(
            path, format="turtle"
        )
    return dataset


def context_for(dataset: Dataset) -> ValidationContext:
    graph = Graph()
    for subject, predicate, obj, _ in dataset.quads((None, None, None, None)):
        graph.add((subject, predicate, obj))
    graph_modules = {
        str(graph_iri): str(module)
        for module in graph.subjects(RDF.type, EOW.OntologyModule)
        for graph_iri in graph.objects(module, EOW.graph)
        if isinstance(module, URIRef) and isinstance(graph_iri, URIRef)
    }
    module_iris = frozenset(
        str(module)
        for module in graph.subjects(RDF.type, EOW.OntologyModule)
        if isinstance(module, URIRef)
    )
    return ValidationContext(
        base=BASE,
        graph_modules=graph_modules,
        module_iris=module_iris,
        locations={},
    )


def add_valid_examples(dataset: Dataset) -> None:
    for path in sorted((KNOWLEDGE_ROOT / "examples" / "valid").glob("*.ttl")):
        dataset.graph(URIRef(f"{BASE}graph/example/valid/{path.stem}")).parse(path, format="turtle")


def governance_shapes(*extras: str) -> Graph:
    shapes = Graph().parse(KNOWLEDGE_ROOT / "shapes" / "governance.ttl")
    for extra in extras:
        shapes.parse(VALIDATION_FIXTURES / "shacl" / extra, format="turtle")
    return shapes


def valid_aggregate() -> Dataset:
    dataset = make_store().load()
    add_valid_examples(dataset)
    return dataset


def aggregate_with_shacl_fixture(fixture: str) -> Dataset:
    dataset = valid_aggregate()
    path = VALIDATION_FIXTURES / "shacl" / fixture
    dataset.graph(URIRef(f"{BASE}graph/test/shacl/{path.stem}")).parse(path, format="turtle")
    return dataset


def assert_weakened_governance_is_rejected(dataset: Dataset, shapes: Graph) -> None:
    before = set(dataset.quads((None, None, None, None)))

    report = make_service().validate_dataset(dataset, shapes=shapes)

    assert not report.conforms
    assert rule_ids(report.issues) == {"shacl.missing_governance"}
    assert set(dataset.quads((None, None, None, None))) == before


def canonical_with_fixture(relative_path: str) -> Dataset:
    dataset = make_store().load()
    path = VALIDATION_FIXTURES / relative_path
    dataset.graph(URIRef(f"{BASE}graph/test/{path.parent.name}/{path.stem}")).parse(
        path,
        format="turtle",
    )
    return dataset


def rule_ids(issues: tuple[ValidationIssue, ...]) -> set[str]:
    return {issue.rule_id for issue in issues}


def test_global_shapes_validate_the_canonical_and_valid_fixture_aggregate() -> None:
    shape_graph = Graph().parse(KNOWLEDGE_ROOT / "shapes" / "governance.ttl")
    report = make_service().validate_dataset(valid_aggregate(), shapes=shape_graph)

    assert (URIRef(f"{BASE}shape/governance/TermShape"), RDF.type, SH.NodeShape) in shape_graph
    assert (URIRef(f"{BASE}shape/governance/PropertyShape"), RDF.type, SH.NodeShape) in shape_graph
    assert report.conforms
    assert report.issues == ()


@pytest.mark.parametrize(
    ("fixture", "expected_rule"),
    [
        ("class_missing_definition.ttl", "shacl.definition"),
        ("property_missing_direction.ttl", "shacl.property_direction"),
        ("concept_invalid_status.ttl", "shacl.status"),
    ],
)
def test_global_shapes_reject_each_directed_metadata_defect(
    fixture: str, expected_rule: str
) -> None:
    dataset = valid_aggregate()
    dataset.graph(URIRef(f"{BASE}graph/example/invalid/{Path(fixture).stem}")).parse(
        KNOWLEDGE_ROOT / "examples" / "invalid" / fixture,
        format="turtle",
    )

    report = make_service().validate_dataset(dataset)

    assert not report.conforms
    assert expected_rule in rule_ids(report.issues)
    assert all(
        issue.source in {ValidationSource.SHACL, ValidationSource.LINT} for issue in report.issues
    )


def test_pyshacl_report_has_deterministic_json_and_rdf() -> None:
    dataset = valid_aggregate()
    dataset.graph(URIRef(f"{BASE}graph/example/invalid/status")).parse(
        KNOWLEDGE_ROOT / "examples" / "invalid" / "concept_invalid_status.ttl",
        format="turtle",
    )
    service = make_service()

    first = service.validate_dataset(dataset)
    second = service.validate_dataset(dataset)

    assert first.to_json() == second.to_json()
    assert first.to_rdf() == second.to_rdf()
    payload = json.loads(first.to_json())
    assert payload["conforms"] is False
    assert payload["counts"]["error"] >= 1
    report_graph = Graph().parse(data=first.to_rdf(), format="nt")
    report = next(report_graph.subjects(RDF.type, SH.ValidationReport))
    assert report_graph.value(report, SH.conforms) == Literal(False)
    assert list(report_graph.objects(report, SH.result))


def test_global_shapes_cover_every_required_metadata_field() -> None:
    dataset = valid_aggregate()
    invalid = KNOWLEDGE_ROOT / "examples" / "invalid" / "missing_governance_metadata.ttl"
    dataset.graph(URIRef(f"{BASE}graph/example/invalid/missing_metadata")).parse(
        invalid, format="turtle"
    )

    report = make_service().validate_dataset(dataset)
    shacl_rules = {
        issue.rule_id for issue in report.issues if issue.source is ValidationSource.SHACL
    }

    assert shacl_rules == {
        "shacl.author",
        "shacl.date",
        "shacl.definition",
        "shacl.evidence",
        "shacl.label",
        "shacl.module",
        "shacl.property_direction",
        "shacl.property_domain_range",
        "shacl.property_example",
        "shacl.status",
    }


@pytest.mark.parametrize(
    ("fixture", "expected_rule"),
    [
        ("invalid_empty_label.ttl", "shacl.label"),
        ("invalid_empty_definition.ttl", "shacl.definition"),
        ("invalid_empty_evidence.ttl", "shacl.evidence"),
        ("invalid_empty_author.ttl", "shacl.author"),
    ],
)
def test_global_shapes_reject_empty_or_whitespace_mandatory_values(
    fixture: str, expected_rule: str
) -> None:
    dataset = valid_aggregate()
    dataset.graph(URIRef(f"{BASE}graph/test/shacl/{Path(fixture).stem}")).parse(
        VALIDATION_FIXTURES / "shacl" / fixture,
        format="turtle",
    )

    report = make_service().validate_dataset(dataset)

    assert not report.conforms
    assert rule_ids(report.issues) == {expected_rule}


@pytest.mark.parametrize(
    "fixture",
    [
        "namespaces/valid.ttl",
        "namespaces/valid_external.ttl",
        "namespaces/valid_individual.ttl",
        "namespaces/valid_technical_bnode.ttl",
    ],
)
def test_namespace_lint_accepts_valid_internal_iris(fixture: str) -> None:
    dataset = dataset_from_fixture(fixture)

    assert SemanticLinter().lint_namespaces(dataset, context_for(dataset)) == ()


@pytest.mark.parametrize(
    ("fixture", "expected_rule"),
    [
        ("namespaces/invalid_dangling.ttl", "namespace.dangling_internal_iri"),
        ("namespaces/invalid_collision.ttl", "namespace.type_collision"),
        ("namespaces/invalid_naming.ttl", "namespace.class_name"),
        ("namespaces/invalid_internal_iri.ttl", "namespace.invalid_internal_iri"),
        ("namespaces/invalid_property_name.ttl", "namespace.property_name"),
        ("namespaces/invalid_individual_name.ttl", "namespace.individual_name"),
        ("namespaces/invalid_typed_individual_name.ttl", "namespace.individual_name"),
        (
            "namespaces/invalid_enterprise_bnode.ttl",
            "namespace.enterprise_individual_bnode",
        ),
        (
            "namespaces/invalid_external_business_bnode.ttl",
            "namespace.enterprise_individual_bnode",
        ),
    ],
)
def test_namespace_lint_detects_invalid_iris_and_collisions(
    fixture: str, expected_rule: str
) -> None:
    dataset = dataset_from_fixture(fixture)
    issues = SemanticLinter().lint_namespaces(dataset, context_for(dataset))

    assert expected_rule in rule_ids(issues)
    assert all(issue.severity is ValidationSeverity.ERROR for issue in issues)


@pytest.mark.parametrize(
    "fixture",
    [
        "namespaces/invalid_enterprise_bnode.ttl",
        "namespaces/invalid_external_business_bnode.ttl",
    ],
)
def test_enterprise_blank_node_is_rejected_with_a_stable_typed_resource(
    fixture: str,
) -> None:
    first_dataset = dataset_from_fixture(fixture)
    second_dataset = dataset_from_fixture(fixture)
    linter = SemanticLinter()

    first = linter.lint_namespaces(first_dataset, context_for(first_dataset))
    second = linter.lint_namespaces(second_dataset, context_for(second_dataset))

    assert rule_ids(first) == {"namespace.enterprise_individual_bnode"}
    assert first == second
    assert first[0].resource_type is ValidationResourceType.BNODE


def test_blank_node_typed_as_an_internal_class_is_an_enterprise_individual() -> None:
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/test/enterprise-bnode"))
    enterprise_class = URIRef(f"{BASE}ontology/fixture#EnterpriseEntity")
    graph.add((enterprise_class, RDF.type, OWL.Class))
    graph.add((BNode("enterprise"), RDF.type, enterprise_class))

    issues = SemanticLinter().lint_namespaces(dataset, context_for(dataset))

    assert rule_ids(issues) == {"namespace.enterprise_individual_bnode"}


def test_internal_iri_typed_as_an_enterprise_class_must_use_snake_case() -> None:
    dataset = canonical_with_fixture("namespaces/invalid_typed_individual_name.ttl")

    report = make_service().validate_dataset(dataset)

    assert not report.conforms
    assert rule_ids(report.issues) == {"namespace.individual_name"}


def test_internal_iri_typed_as_an_enterprise_class_accepts_snake_case() -> None:
    dataset = canonical_with_fixture("namespaces/valid_typed_individual.ttl")
    before = set(dataset.quads((None, None, None, None)))

    report = make_service().validate_dataset(dataset)

    assert report.conforms
    assert report.issues == ()
    assert set(dataset.quads((None, None, None, None))) == before


def test_external_business_class_blank_node_fails_end_to_end_deterministically() -> None:
    service = make_service()
    first_dataset = canonical_with_fixture("namespaces/invalid_external_business_bnode.ttl")
    second_dataset = canonical_with_fixture("namespaces/invalid_external_business_bnode.ttl")
    first_before = set(first_dataset.quads((None, None, None, None)))

    first = service.validate_dataset(first_dataset)
    second = service.validate_dataset(second_dataset)

    assert rule_ids(first.issues) == {"namespace.enterprise_individual_bnode"}
    assert first.to_json() == second.to_json()
    assert first.to_rdf() == second.to_rdf()
    assert first.issues[0].resource_type is ValidationResourceType.BNODE
    assert set(first_dataset.quads((None, None, None, None))) == first_before


def test_technical_owl_blank_node_is_not_governed_as_an_enterprise_term() -> None:
    dataset = dataset_from_fixture("namespaces/valid_technical_bnode.ttl")
    context = context_for(dataset)
    before = set(dataset.quads((None, None, None, None)))

    assert SemanticLinter().lint_namespaces(dataset, context) == ()
    assert make_service().validate_dataset(dataset, context=context).conforms
    assert set(dataset.quads((None, None, None, None))) == before


def test_external_vocabulary_terms_are_outside_internal_governance_rules() -> None:
    dataset = dataset_from_fixture("namespaces/valid_external.ttl")
    context = context_for(dataset)
    linter = SemanticLinter()

    assert linter.lint_namespaces(dataset, context) == ()
    assert linter.lint_module_ownership(dataset, context) == ()
    assert make_service().validate_dataset(dataset, context=context).conforms


def test_module_lint_accepts_one_responsible_module() -> None:
    dataset = dataset_from_fixture("modules/valid.trig")

    assert SemanticLinter().lint_module_ownership(dataset, context_for(dataset)) == ()


def test_module_lint_detects_definition_in_more_than_one_module() -> None:
    dataset = dataset_from_fixture("modules/invalid_multiple.trig")
    issues = SemanticLinter().lint_module_ownership(dataset, context_for(dataset))

    assert rule_ids(issues) == {"module.multiple_definitions"}
    assert "alpha" in issues[0].message and "beta" in issues[0].message


@pytest.mark.parametrize(
    ("fixture", "expected_rule"),
    [
        ("modules/invalid_owner_count.trig", "module.owner_count"),
        ("modules/invalid_unknown_owner.trig", "module.unknown_owner"),
        ("modules/invalid_owner_graph_mismatch.trig", "module.owner_graph_mismatch"),
    ],
)
def test_module_lint_covers_each_ownership_failure(fixture: str, expected_rule: str) -> None:
    dataset = dataset_from_fixture(fixture)
    issues = SemanticLinter().lint_module_ownership(dataset, context_for(dataset))

    assert rule_ids(issues) == {expected_rule}


def test_lexical_lint_accepts_distinct_normalized_labels() -> None:
    dataset = dataset_from_fixture("duplicates/valid.ttl")

    assert SemanticLinter().lint_lexical_duplicates(dataset, context_for(dataset)) == ()


def test_lexical_lint_matches_pref_and_alt_labels_after_normalization() -> None:
    dataset = dataset_from_fixture("duplicates/invalid.ttl")
    issues = SemanticLinter().lint_lexical_duplicates(dataset, context_for(dataset))

    assert len(issues) == 2
    assert rule_ids(issues) == {"lexical.duplicate_label"}
    assert all(issue.severity is ValidationSeverity.WARNING for issue in issues)
    assert all(dict(issue.details)["normalized"] == "area tecnica" for issue in issues)


def test_deprecation_lint_accepts_a_still_deprecated_published_iri() -> None:
    baseline = dataset_from_fixture("deprecations/baseline.ttl")
    candidate = dataset_from_fixture("deprecations/valid.ttl")

    assert SemanticLinter().lint_deprecations(candidate, context_for(candidate), baseline) == ()


def test_deprecation_lint_rejects_reuse_and_removal() -> None:
    baseline = dataset_from_fixture("deprecations/baseline.ttl")
    reused = dataset_from_fixture("deprecations/invalid_reused.ttl")
    linter = SemanticLinter()

    reused_issues = linter.lint_deprecations(reused, context_for(reused), baseline)
    removed_issues = linter.lint_deprecations(Dataset(), context_for(Dataset()), baseline)

    assert rule_ids(reused_issues) == {"deprecation.iri_reused"}
    assert rule_ids(removed_issues) == {"deprecation.published_term_removed"}


def test_deprecation_lint_rejects_a_published_type_change() -> None:
    baseline = dataset_from_fixture("deprecations/baseline.ttl")
    candidate = dataset_from_fixture("deprecations/invalid_type_changed.ttl")

    issues = SemanticLinter().lint_deprecations(candidate, context_for(candidate), baseline)

    assert rule_ids(issues) == {"deprecation.published_type_changed"}


def test_deprecation_lint_requires_a_reason() -> None:
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/test/deprecation"))
    term = URIRef(f"{BASE}ontology/fixture#DeprecatedWithoutReason")
    graph.add((term, RDF.type, OWL.Class))
    graph.add((term, EOW.status, Literal("deprecated")))

    issues = SemanticLinter().lint_deprecations(dataset, context_for(dataset), None)

    assert rule_ids(issues) == {"deprecation.missing_reason"}


def test_deprecation_rules_ignore_external_vocabulary_terms() -> None:
    baseline = dataset_from_fixture("namespaces/valid_external.ttl")
    candidate = Dataset()

    issues = SemanticLinter().lint_deprecations(candidate, context_for(candidate), baseline)

    assert issues == ()


def test_dangerous_property_lint_accepts_precise_names() -> None:
    dataset = dataset_from_fixture("properties/valid.ttl")

    assert SemanticLinter().lint_dangerous_properties(dataset, context_for(dataset)) == ()


def test_dangerous_property_lint_warns_generic_names_and_same_as() -> None:
    dataset = dataset_from_fixture("properties/invalid.ttl")
    issues = SemanticLinter().lint_dangerous_properties(dataset, context_for(dataset))

    assert rule_ids(issues) == {
        "property.generic_name",
        "property.owl_same_as",
        "property.related_to",
    }
    assert all(issue.severity is ValidationSeverity.WARNING for issue in issues)


def test_import_lint_accepts_an_acyclic_graph() -> None:
    dataset = dataset_from_fixture("imports/valid.ttl")

    assert SemanticLinter().lint_import_cycles(dataset, context_for(dataset)) == ()


def test_import_lint_reports_the_complete_cycle_chain() -> None:
    dataset = dataset_from_fixture("imports/invalid_cycle.ttl")
    issues = SemanticLinter().lint_import_cycles(dataset, context_for(dataset))

    assert rule_ids(issues) == {"imports.cycle"}
    chain = dict(issues[0].details)["chain"]
    assert chain == (
        f"{BASE}ontology/alpha -> {BASE}ontology/beta -> "
        f"{BASE}ontology/gamma -> {BASE}ontology/alpha"
    )


def test_proposed_relation_cannot_be_materialized_in_a_published_graph() -> None:
    dataset = Dataset()
    published = URIRef(f"{BASE}graph/source/published")
    metadata = dataset.graph(URIRef(f"{BASE}graph/metadata/source/published"))
    proposal = dataset.graph(URIRef(f"{BASE}graph/proposal/test"))
    subject = URIRef(f"{BASE}id/test/subject")
    predicate = URIRef(f"{BASE}ontology/test#relatesTo")
    obj = URIRef(f"{BASE}id/test/object")
    assertion = URIRef("urn:eow:proposal-statement:test")
    metadata.add((published, RDF.type, PROV.Entity))
    metadata.add((published, EOW.status, Literal("published")))
    proposal.add((assertion, RDF.type, RDF.Statement))
    proposal.add((assertion, RDF.subject, subject))
    proposal.add((assertion, RDF.predicate, predicate))
    proposal.add((assertion, RDF.object, obj))
    proposal.add((assertion, EOW.status, Literal("proposed")))
    dataset.graph(published).add((subject, predicate, obj))

    issues = SemanticLinter().lint_proposal_graph_separation(dataset, context_for(dataset))

    assert [issue.rule_id for issue in issues] == ["proposal.relation_in_published_graph"]
    assert issues[0].graph == str(published)

    dataset.graph(published).remove((subject, predicate, obj))
    proposal.add((subject, predicate, obj))
    assert SemanticLinter().lint_proposal_graph_separation(dataset, context_for(dataset)) == ()


def test_parser_failure_uses_the_common_report_contract(tmp_path: Path) -> None:
    copied_knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
    broken = copied_knowledge / "ontology" / "software" / "terms" / "broken.ttl"
    shutil.copyfile(KNOWLEDGE_ROOT / "examples" / "invalid" / "syntax_error.ttl", broken)

    report = make_service(copied_knowledge).validate_repository()

    assert not report.conforms
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.source is ValidationSource.PARSER
    assert issue.rule_id == "parser.syntax"
    assert issue.path == "ontology/software/terms/broken.ttl"
    assert str(tmp_path) not in issue.message
    assert json.loads(report.to_json())["issues"][0]["source"] == "parser"
    Graph().parse(data=report.to_rdf(), format="nt")


def test_parser_reports_are_reproducible_across_equivalent_checkouts(tmp_path: Path) -> None:
    reports: list[ValidationReport] = []
    for checkout_name in ("checkout-a", "checkout-b"):
        copied_knowledge = tmp_path / checkout_name / "knowledge"
        shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
        broken = copied_knowledge / "ontology" / "software" / "terms" / "broken.ttl"
        shutil.copyfile(KNOWLEDGE_ROOT / "examples" / "invalid" / "syntax_error.ttl", broken)
        reports.append(make_service(copied_knowledge).validate_repository())

    assert reports[0].issues[0].path == "ontology/software/terms/broken.ttl"
    assert str(tmp_path) not in reports[0].issues[0].message
    assert reports[0].to_json() == reports[1].to_json()
    assert reports[0].to_rdf() == reports[1].to_rdf()


def test_shacl_issue_reports_the_responsible_repository_file(tmp_path: Path) -> None:
    copied_knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
    term_path = copied_knowledge / "ontology" / "organization" / "terms" / "OrganizationUnit.ttl"
    source = term_path.read_text(encoding="utf-8")
    term_path.write_text(
        "\n".join(line for line in source.splitlines() if "skos:definition" not in line) + "\n",
        encoding="utf-8",
    )

    report = make_service(copied_knowledge).validate_repository()
    issue = next(issue for issue in report.issues if issue.rule_id == "shacl.definition")

    assert issue.resource == f"{BASE}ontology/organization#OrganizationUnit"
    assert issue.path == "ontology/organization/terms/OrganizationUnit.ttl"


def test_shacl_execution_errors_use_the_common_report_contract() -> None:
    shapes = governance_shapes("invalid_shape_constraint.ttl")

    report = make_service().validate_dataset(make_store().load(), shapes=shapes)

    assert not report.conforms
    execution = [issue for issue in report.issues if issue.rule_id == "shacl.execution"]
    assert len(execution) == 1
    assert execution[0].source is ValidationSource.SHACL
    assert "ReportableRuntimeError" in execution[0].message


@pytest.mark.parametrize("error_type", [ConstraintLoadError, ShapeLoadError])
def test_known_pyshacl_load_errors_are_unified_without_masking_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[ReportableRuntimeError],
) -> None:
    def fail_validation(**kwargs: object) -> None:
        del kwargs
        raise error_type("invalid SHACL fixture", "https://www.w3.org/TR/shacl/")

    monkeypatch.setattr("ontology_core.validation.pyshacl_validate", fail_validation)

    report = make_service().validate_dataset(make_store().load())

    assert rule_ids(report.issues) == {"shacl.execution"}
    assert error_type.__name__ in report.issues[0].message


def test_unexpected_pyshacl_errors_are_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_unexpectedly(**kwargs: object) -> None:
        del kwargs
        raise ValueError("unexpected implementation defect")

    monkeypatch.setattr("ontology_core.validation.pyshacl_validate", fail_unexpectedly)

    with pytest.raises(ValueError, match="unexpected implementation defect"):
        make_service().validate_dataset(make_store().load())


def test_blank_node_focus_is_typed_and_serializes_as_valid_deterministic_rdf() -> None:
    dataset = dataset_from_fixture("shacl/invalid_bnode_focus.ttl")
    service = make_service()
    shapes = governance_shapes("technical_bnode_shape.ttl")

    first = service.validate_dataset(dataset, shapes=shapes, context=context_for(dataset))
    second = service.validate_dataset(dataset, shapes=shapes, context=context_for(dataset))
    bnode_issues = [
        issue for issue in first.issues if issue.resource_type is ValidationResourceType.BNODE
    ]

    assert bnode_issues
    assert first.to_json() == second.to_json()
    assert first.to_rdf() == second.to_rdf()
    payload = json.loads(first.to_json())
    assert {item["resource_type"] for item in payload["issues"]} == {"bnode"}
    report_graph = Graph().parse(data=first.to_rdf(), format="nt")
    focus_nodes = set(report_graph.objects(None, SH.focusNode))
    assert focus_nodes and all(isinstance(node, BNode) for node in focus_nodes)


def test_missing_global_governance_shapes_fail_explicitly(tmp_path: Path) -> None:
    copied_knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
    (copied_knowledge / "shapes" / "governance.ttl").unlink()

    repository_report = make_service(copied_knowledge).validate_repository()
    explicit_report = make_service().validate_dataset(
        make_store().load(),
        shapes=Graph(),
    )

    for report in (repository_report, explicit_report):
        assert not report.conforms
        assert rule_ids(report.issues) == {"shacl.missing_governance"}
        assert report.issues[0].source is ValidationSource.SHACL
        assert report.issues[0].path == "shapes/governance.ttl"


def test_named_but_empty_global_shapes_cannot_disable_governance() -> None:
    shapes = Graph().parse(
        VALIDATION_FIXTURES / "shacl" / "invalid_empty_governance.ttl",
        format="turtle",
    )

    report = make_service().validate_dataset(make_store().load(), shapes=shapes)

    assert not report.conforms
    assert rule_ids(report.issues) == {"shacl.missing_governance"}
    missing = set(dict(report.issues[0].details)["missing"].split(","))
    assert "TermShape.property:prefLabel" in missing
    assert "PropertyShape.logical:domain-range-or-justification" in missing


def test_governance_contract_requires_every_target_class() -> None:
    shapes = governance_shapes()
    term_shape = URIRef(f"{BASE}shape/governance/TermShape")
    shapes.remove((term_shape, SH.targetClass, OWL.Class))

    report = make_service().validate_dataset(make_store().load(), shapes=shapes)

    assert rule_ids(report.issues) == {"shacl.missing_governance"}
    missing = dict(report.issues[0].details)["missing"]
    assert "TermShape.targetClasses" in missing


def test_governance_contract_requires_constraints_for_every_path() -> None:
    shapes = governance_shapes()
    label_property = next(shapes.subjects(SH.path, SKOS.prefLabel))
    shapes.remove((label_property, SH.minCount, None))

    report = make_service().validate_dataset(make_store().load(), shapes=shapes)

    assert rule_ids(report.issues) == {"shacl.missing_governance"}
    missing = dict(report.issues[0].details)["missing"]
    assert "TermShape.property:prefLabel" in missing


def test_governance_contract_rejects_deactivated_mandatory_shapes() -> None:
    shapes = governance_shapes()
    term_shape = URIRef(f"{BASE}shape/governance/TermShape")
    shapes.add((term_shape, SH.deactivated, Literal(True)))

    report = make_service().validate_dataset(make_store().load(), shapes=shapes)

    assert rule_ids(report.issues) == {"shacl.missing_governance"}
    missing = dict(report.issues[0].details)["missing"]
    assert "TermShape.active" in missing


def test_governance_contract_rejects_deactivated_required_property_component() -> None:
    dataset = aggregate_with_shacl_fixture("invalid_missing_label.ttl")
    shapes = governance_shapes()
    label_property = next(shapes.subjects(SH.path, SKOS.prefLabel))
    shapes.add((label_property, SH.deactivated, Literal(True)))

    assert_weakened_governance_is_rejected(dataset, shapes)
    assert (
        "GovernanceShape.components:active-violations"
        in dict(make_service().validate_dataset(dataset, shapes=shapes).issues[0].details)[
            "missing"
        ]
    )


def test_governance_contract_rejects_warning_severity_on_required_component() -> None:
    dataset = aggregate_with_shacl_fixture("invalid_missing_label.ttl")
    shapes = governance_shapes()
    label_property = next(shapes.subjects(SH.path, SKOS.prefLabel))
    shapes.add((label_property, SH.severity, SH.Warning))

    assert_weakened_governance_is_rejected(dataset, shapes)


def test_governance_contract_rejects_empty_date_alternative() -> None:
    dataset = aggregate_with_shacl_fixture("invalid_missing_date.ttl")
    shapes = governance_shapes()
    term_shape = URIRef(f"{BASE}shape/governance/TermShape")
    date_head = next(shapes.objects(term_shape, SH["or"]))
    Collection(shapes, date_head).append(BNode())

    assert_weakened_governance_is_rejected(dataset, shapes)
    assert (
        "TermShape.logical:date"
        in dict(make_service().validate_dataset(dataset, shapes=shapes).issues[0].details)[
            "missing"
        ]
    )


def test_governance_contract_rejects_empty_property_semantics_alternative() -> None:
    dataset = aggregate_with_shacl_fixture("invalid_missing_property_semantics.ttl")
    shapes = governance_shapes()
    property_shape = URIRef(f"{BASE}shape/governance/PropertyShape")
    semantics_head = next(shapes.objects(property_shape, SH["or"]))
    Collection(shapes, semantics_head).append(BNode())

    assert_weakened_governance_is_rejected(dataset, shapes)
    assert (
        "PropertyShape.logical:domain-range-or-justification"
        in dict(make_service().validate_dataset(dataset, shapes=shapes).issues[0].details)[
            "missing"
        ]
    )


def test_governance_contract_rejects_additional_allowed_status() -> None:
    dataset = aggregate_with_shacl_fixture("invalid_draft_status.ttl")
    shapes = governance_shapes()
    status_property = next(shapes.subjects(SH.path, EOW.status))
    status_head = next(shapes.objects(status_property, SH["in"]))
    Collection(shapes, status_head).append(Literal("draft"))

    assert_weakened_governance_is_rejected(dataset, shapes)
    assert (
        "TermShape.property:status"
        in dict(make_service().validate_dataset(dataset, shapes=shapes).issues[0].details)[
            "missing"
        ]
    )


def test_validation_preserves_every_input_quad() -> None:
    dataset = valid_aggregate()
    before = set(dataset.quads((None, None, None, None)))

    report = make_service().validate_dataset(dataset)

    assert report.conforms
    assert set(dataset.quads((None, None, None, None))) == before


def test_validation_reports_if_a_pipeline_stage_mutates_the_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = make_store().load()
    service = make_service()

    def mutate_input(
        candidate: Dataset,
        context: ValidationContext,
        baseline: Dataset | None,
    ) -> tuple[ValidationIssue, ...]:
        del context, baseline
        candidate.graph(URIRef(f"{BASE}graph/test/mutated")).add(
            (
                URIRef(f"{BASE}id/test/mutated"),
                DCTERMS.description,
                Literal("mutation"),
            )
        )
        return ()

    monkeypatch.setattr(service.linter, "lint", mutate_input)

    report = service.validate_dataset(dataset)

    assert "validation.dataset_mutated" in rule_ids(report.issues)


def test_shape_symlink_outside_knowledge_is_rejected(tmp_path: Path) -> None:
    copied_knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
    external = tmp_path / "external-shape.ttl"
    external.write_text(
        "<https://external.example/Shape> a <http://www.w3.org/ns/shacl#NodeShape> .\n",
        encoding="utf-8",
    )
    linked = copied_knowledge / "shapes" / "modules" / "external.ttl"
    linked.symlink_to(external)

    report = make_service(copied_knowledge).validate_repository()

    assert not report.conforms
    assert rule_ids(report.issues) == {"parser.path_escape"}
    assert report.issues[0].path == "shapes/modules/external.ttl"


@pytest.mark.parametrize(
    ("limits", "expected_rule"),
    [
        (RdfLoadLimits(max_file_bytes=1, parse_timeout_seconds=10), "parser.size_limit"),
        (
            RdfLoadLimits(
                max_file_bytes=8 * 1024 * 1024,
                parse_timeout_seconds=0.000001,
            ),
            "parser.timeout",
        ),
    ],
)
def test_repository_limits_use_the_common_report_contract(
    limits: RdfLoadLimits, expected_rule: str
) -> None:
    service = ValidationService(FilesystemRdfStore(KNOWLEDGE_ROOT, NAMESPACE_CONFIG, limits=limits))

    report = service.validate_repository()

    assert not report.conforms
    assert rule_ids(report.issues) == {expected_rule}
    Graph().parse(data=report.to_rdf(), format="nt")


def test_validation_does_not_dereference_remote_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = make_store().load()
    software_graph = dataset.graph(URIRef(f"{BASE}graph/ontology/software"))
    software_graph.add(
        (
            URIRef(f"{BASE}ontology/software"),
            OWL.imports,
            URIRef("https://remote.invalid/ontology/never-fetch"),
        )
    )

    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"unexpected network access: {args!r} {kwargs!r}")

    monkeypatch.setattr(urllib.request, "urlopen", reject_network)

    report = make_service().validate_dataset(dataset)

    assert report.conforms


def test_common_report_orders_parser_shacl_and_lint_issues_deterministically() -> None:
    issues = [
        ValidationIssue(
            source=ValidationSource.LINT,
            rule_id="lint.example",
            severity=ValidationSeverity.WARNING,
            message="Advertencia.",
        ),
        ValidationIssue(
            source=ValidationSource.PARSER,
            rule_id="parser.syntax",
            severity=ValidationSeverity.ERROR,
            message="Error de sintaxis.",
            path="fixture.ttl",
        ),
        ValidationIssue(
            source=ValidationSource.SHACL,
            rule_id="shacl.definition",
            severity=ValidationSeverity.ERROR,
            message="Falta definición.",
            resource=f"{BASE}ontology/fixture#Term",
        ),
    ]

    first = ValidationReport.from_issues(issues)
    second = ValidationReport.from_issues(reversed(issues))

    assert first.to_json() == second.to_json()
    assert first.to_rdf() == second.to_rdf()
    assert {issue.source for issue in first.issues} == set(ValidationSource)

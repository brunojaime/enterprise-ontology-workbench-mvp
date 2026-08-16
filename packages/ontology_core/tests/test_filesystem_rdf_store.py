from __future__ import annotations

import multiprocessing
import shutil
from pathlib import Path

import pytest
from ontology_core import FilesystemRdfStore, RdfLoadError, RdfLoadLimits
from rdflib import Dataset, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, XSD
from rdflib.term import Node

REPOSITORY_ROOT = Path(__file__).parents[3]
KNOWLEDGE_ROOT = REPOSITORY_ROOT / "knowledge"
NAMESPACE_CONFIG = REPOSITORY_ROOT / "config" / "namespace.yaml"
BASE = "https://knowledge.example.com/"
PROV = Namespace("http://www.w3.org/ns/prov#")
EOW = Namespace(f"{BASE}ontology/core#")


def make_store(knowledge_root: Path = KNOWLEDGE_ROOT) -> FilesystemRdfStore:
    return FilesystemRdfStore(knowledge_root, NAMESPACE_CONFIG)


def quad_set(dataset: Dataset) -> set[tuple[Node, Node, Node, Node]]:
    return set(dataset.quads((None, None, None, None)))


def internal_dangling_iris(dataset: Dataset) -> set[URIRef]:
    """Audit the bounded P02 fixtures without implementing the Plan 03 linter."""

    defined = {
        subject
        for subject, _, _, _ in dataset.quads((None, None, None, None))
        if isinstance(subject, URIRef)
    }
    defined.update(
        graph.identifier
        for graph in dataset.graphs()
        if len(graph) and isinstance(graph.identifier, URIRef)
    )
    referenced = {
        node
        for subject, predicate, obj, _ in dataset.quads((None, None, None, None))
        for node in (subject, predicate, obj)
        if isinstance(node, URIRef) and str(node).startswith(BASE)
    }
    return referenced - defined


def add_valid_fixtures(dataset: Dataset) -> tuple[Path, ...]:
    fixture_root = KNOWLEDGE_ROOT / "examples" / "valid"
    fixture_paths = tuple(sorted(fixture_root.glob("*.ttl")))
    for path in fixture_paths:
        dataset.graph(URIRef(f"{BASE}graph/example/valid/{path.stem}")).parse(path, format="turtle")
    return fixture_paths


def test_manifest_declares_version_namespace_and_loadable_modules() -> None:
    store = make_store()

    modules = store.discover_modules()

    assert [module.identifier for module in modules] == [
        "competency",
        "core",
        "knowledge_governance",
        "organization",
        "software",
    ]
    assert [module.source_path.as_posix() for module in modules] == [
        "ontology/competency",
        "ontology/core",
        "ontology/knowledge_governance",
        "ontology/organization",
        "ontology/software",
    ]
    assert all(module.graph_iri.startswith(f"{BASE}graph/ontology/") for module in modules)


def test_store_loads_turtle_modules_and_trig_sources_into_dataset() -> None:
    store = make_store()
    dataset = store.load()

    organization_class = URIRef(f"{BASE}ontology/organization#OrganizationUnit")
    application_class = URIRef(f"{BASE}ontology/software#Application")
    assert (organization_class, RDF.type, OWL.Class) in dataset.graph(
        URIRef(f"{BASE}graph/ontology/organization")
    )
    assert (application_class, RDF.type, OWL.Class) in dataset.graph(
        URIRef(f"{BASE}graph/ontology/software")
    )
    assert len(dataset.graph(URIRef(f"{BASE}graph/source/fixture_inventory"))) > 0
    assert len(dataset.default_graph) == 0
    assert store.source_paths_for(application_class) == (
        KNOWLEDGE_ROOT / "ontology/software/terms/Application.ttl",
    )
    assert store.source_paths_for(URIRef(f"{BASE}ontology/software#undefinedPredicate")) == ()


def test_each_module_and_source_keeps_its_declared_graph() -> None:
    dataset = make_store().load()
    graph_ids = {str(graph.identifier) for graph in dataset.graphs() if len(graph) > 0}

    assert graph_ids == {
        f"{BASE}graph/manifest",
        f"{BASE}graph/ontology/competency",
        f"{BASE}graph/ontology/core",
        f"{BASE}graph/ontology/knowledge_governance",
        f"{BASE}graph/ontology/organization",
        f"{BASE}graph/ontology/software",
        f"{BASE}graph/competency-questions/questions",
        f"{BASE}graph/source/fixture_inventory",
        f"{BASE}graph/metadata/source/fixture_inventory",
        f"{BASE}graph/proposal/p12-governed-knowledge-pilot/fixture_inventory",
        f"{BASE}graph/metadata/proposal/p12-governed-knowledge-pilot/fixture_inventory",
        f"{BASE}graph/source/p12_ontology_change_publication",
        f"{BASE}graph/source/p12_ontology_core_component",
        f"{BASE}graph/source/p12_enterprise_ontology_workbench_repository",
    }


def test_competency_questions_are_discovered_as_rdf_in_their_own_named_graph() -> None:
    store = make_store()
    dataset = store.load()
    files = store.discover_competency_question_files()
    graph = dataset.graph(URIRef(f"{BASE}graph/competency-questions/questions"))

    assert [path.name for path in files] == ["questions.ttl"]
    assert len(graph) > 0
    assert len(dataset.default_graph) == 0


def test_source_assertions_and_provenance_use_separate_named_graphs() -> None:
    dataset = make_store().load()
    source_graph_iri = URIRef(f"{BASE}graph/source/fixture_inventory")
    metadata_graph_iri = URIRef(f"{BASE}graph/metadata/source/fixture_inventory")
    source_graph = dataset.graph(source_graph_iri)
    metadata_graph = dataset.graph(metadata_graph_iri)
    activity = URIRef(f"{BASE}id/activity/generate_fixture_inventory")
    agent = URIRef(f"{BASE}id/agent/codex_generator")
    source = URIRef(f"{BASE}id/source/synthetic_fixture_inventory")

    organization_unit = URIRef(f"{BASE}id/organization/unit/architecture")

    proposal_graph_iri = URIRef(
        f"{BASE}graph/proposal/p12-governed-knowledge-pilot/fixture_inventory"
    )
    proposal_metadata_iri = URIRef(
        f"{BASE}graph/metadata/proposal/p12-governed-knowledge-pilot/fixture_inventory"
    )
    proposal_graph = dataset.graph(proposal_graph_iri)
    proposal_metadata = dataset.graph(proposal_metadata_iri)
    application = URIRef(f"{BASE}id/software/application/workbench")
    composition = URIRef(f"{BASE}ontology/software#isComposedOf")
    component = URIRef(f"{BASE}id/software/component/ontology_core")

    assert len(source_graph) == 5
    assert (organization_unit, RDF.type, OWL.NamedIndividual) in source_graph
    assert (
        organization_unit,
        RDF.type,
        URIRef(f"{BASE}ontology/organization#OrganizationUnit"),
    ) in source_graph
    assert (source_graph_iri, PROV.wasGeneratedBy, activity) not in source_graph
    assert (source_graph_iri, PROV.wasGeneratedBy, activity) in metadata_graph
    assert (source_graph_iri, PROV.wasDerivedFrom, source) in metadata_graph
    assert (source_graph_iri, EOW.status, Literal("published")) in metadata_graph
    assert (activity, PROV.wasAssociatedWith, agent) in metadata_graph
    generated = metadata_graph.value(source_graph_iri, PROV.generatedAtTime)
    assert isinstance(generated, Literal) and generated.datatype == XSD.dateTime
    assert metadata_graph.value(source, DCTERMS.title) is not None
    assert (application, composition, component) not in source_graph
    assert (application, composition, component) in proposal_graph
    assert (proposal_graph_iri, EOW.status, Literal("proposed")) in proposal_metadata
    assert (proposal_graph_iri, PROV.wasDerivedFrom, source_graph_iri) in proposal_metadata


def test_canonical_dataset_has_no_dangling_internal_iris() -> None:
    dataset = make_store().load()

    assert internal_dangling_iris(dataset) == set()


def test_new_term_is_discovered_without_python_changes(tmp_path: Path) -> None:
    copied_knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
    new_term = copied_knowledge / "ontology" / "software" / "terms" / "Discovered.ttl"
    new_term.write_text(
        """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix software: <https://knowledge.example.com/ontology/software#> .
software:Discovered a owl:Class .
""",
        encoding="utf-8",
    )

    store = make_store(copied_knowledge)
    module = next(item for item in store.discover_modules() if item.identifier == "software")
    assert new_term in store.discover_module_files(module)
    assert (
        URIRef(f"{BASE}ontology/software#Discovered"),
        RDF.type,
        OWL.Class,
    ) in store.load().graph(module.graph_iri)


def test_relevant_turtle_parse_error_names_the_source(tmp_path: Path) -> None:
    copied_knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
    broken = copied_knowledge / "ontology" / "software" / "terms" / "broken.ttl"
    shutil.copyfile(KNOWLEDGE_ROOT / "examples" / "invalid" / "syntax_error.ttl", broken)

    with pytest.raises(RdfLoadError) as error:
        make_store(copied_knowledge).load()

    assert error.value.path == broken
    assert str(broken) in str(error.value)


def test_relevant_trig_parse_error_names_the_source(tmp_path: Path) -> None:
    copied_knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
    broken = copied_knowledge / "data" / "sources" / "broken.trig"
    broken.write_text("<https://example.invalid/graph> { <broken>", encoding="utf-8")

    with pytest.raises(RdfLoadError) as error:
        make_store(copied_knowledge).load()

    assert error.value.path == broken


def test_store_rejects_an_rdf_symlink_that_escapes_knowledge(tmp_path: Path) -> None:
    copied_knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_ROOT, copied_knowledge)
    external = tmp_path / "external.ttl"
    external.write_text(
        '<https://external.example/resource> <https://external.example/p> "value" .\n',
        encoding="utf-8",
    )
    linked = copied_knowledge / "data" / "sources" / "linked.ttl"
    linked.symlink_to(external)

    with pytest.raises(RdfLoadError) as error:
        make_store(copied_knowledge).load()

    assert error.value.path == linked
    assert error.value.rule_id == "parser.path_escape"


def test_store_rejects_rdf_over_the_configured_size_limit() -> None:
    store = FilesystemRdfStore(
        KNOWLEDGE_ROOT,
        NAMESPACE_CONFIG,
        limits=RdfLoadLimits(max_file_bytes=1, parse_timeout_seconds=10),
    )

    with pytest.raises(RdfLoadError) as error:
        store.load()

    assert error.value.rule_id == "parser.size_limit"
    assert error.value.path == KNOWLEDGE_ROOT / "manifest.ttl"


def test_store_enforces_the_configured_parse_timeout() -> None:
    store = FilesystemRdfStore(
        KNOWLEDGE_ROOT,
        NAMESPACE_CONFIG,
        limits=RdfLoadLimits(max_file_bytes=8 * 1024 * 1024, parse_timeout_seconds=0.000001),
    )

    with pytest.raises(RdfLoadError) as error:
        store.load()

    assert error.value.rule_id == "parser.timeout"
    assert error.value.path == KNOWLEDGE_ROOT / "manifest.ttl"


def test_store_falls_back_to_spawn_when_fork_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiprocessing, "get_all_start_methods", lambda: ["spawn"])

    modules = make_store().discover_modules()

    assert [module.identifier for module in modules] == [
        "competency",
        "core",
        "knowledge_governance",
        "organization",
        "software",
    ]


def test_export_and_round_trip_preserve_every_quad(tmp_path: Path) -> None:
    store = make_store()
    loaded = store.load()
    destination = tmp_path / "export.trig"

    store.export(destination)
    restored = Dataset()
    restored.parse(destination, format="trig")

    assert quad_set(restored) == quad_set(loaded)
    assert len(restored.default_graph) == 0
    metadata_graph = restored.graph(URIRef(f"{BASE}graph/metadata/source/fixture_inventory"))
    source_graph = URIRef(f"{BASE}graph/source/fixture_inventory")
    activity = URIRef(f"{BASE}id/activity/generate_fixture_inventory")
    assert (source_graph, PROV.wasGeneratedBy, activity) in metadata_graph


def test_valid_resource_fixtures_round_trip_with_metadata_and_types(tmp_path: Path) -> None:
    fixture_dataset = make_store().load()
    fixture_paths = add_valid_fixtures(fixture_dataset)
    assert {path.stem for path in fixture_paths} == {
        "class",
        "concept",
        "individual",
        "module",
        "property",
        "shape",
    }
    assert internal_dangling_iris(fixture_dataset) == set()

    export = tmp_path / "valid-fixtures.trig"
    fixture_dataset.serialize(destination=export, format="trig")
    restored = Dataset().parse(export, format="trig")

    assert quad_set(restored) == quad_set(fixture_dataset)
    assert len(restored.default_graph) == 0
    assert len([graph for graph in restored.graphs() if len(graph)]) == 20
    assert internal_dangling_iris(restored) == set()


@pytest.mark.parametrize(
    "fixture",
    [
        "class_missing_definition.ttl",
        "property_missing_direction.ttl",
        "concept_invalid_status.ttl",
    ],
)
def test_directed_invalid_fixture_context_has_no_unrelated_dangling_iri(
    fixture: str,
) -> None:
    dataset = make_store().load()
    add_valid_fixtures(dataset)
    dataset.graph(URIRef(f"{BASE}graph/example/invalid/{Path(fixture).stem}")).parse(
        KNOWLEDGE_ROOT / "examples" / "invalid" / fixture,
        format="turtle",
    )

    assert internal_dangling_iris(dataset) == set()


def test_serialization_is_trig_and_preserves_graph_iris() -> None:
    store = make_store()
    store.load()

    serialized = store.serialize()

    assert f"<{BASE}graph/ontology/software>" in serialized
    assert f"<{BASE}graph/source/fixture_inventory>" in serialized


def test_named_graph_can_be_serialized_as_read_only_turtle() -> None:
    store = make_store()
    dataset = store.load()
    before = quad_set(dataset)

    turtle = store.serialize_graph(f"{BASE}graph/ontology/software")

    parsed = Dataset()
    parsed.default_graph.parse(data=turtle, format="turtle")
    assert (
        URIRef(f"{BASE}ontology/software#Application"),
        RDF.type,
        OWL.Class,
    ) in parsed.default_graph
    assert quad_set(dataset) == before

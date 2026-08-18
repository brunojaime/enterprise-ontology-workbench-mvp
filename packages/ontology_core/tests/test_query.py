from __future__ import annotations

from pathlib import Path

import pytest
from ontology_core import (
    FilesystemRdfStore,
    NeighborhoodFilter,
    NeighborhoodLimits,
    OntologyQueryService,
)
from ontology_core.search_receipts import SearchReceiptAuthority
from rdflib import BNode, Dataset, Literal, URIRef
from rdflib.namespace import OWL, PROV, RDF, RDFS, SKOS

ROOT = Path(__file__).parents[3]
BASE = "https://knowledge.example.com/"


def services() -> tuple[FilesystemRdfStore, OntologyQueryService]:
    store = FilesystemRdfStore(ROOT / "knowledge", ROOT / "config" / "namespace.yaml")
    return store, OntologyQueryService(store.load(), store.prefixes)


def test_search_matches_iri_local_name_preferred_and_alternative_labels() -> None:
    store, query = services()
    dataset = store.dataset
    resource = URIRef(f"{BASE}ontology/software#Application")
    graph = dataset.graph(URIRef(f"{BASE}graph/ontology/software"))
    graph.add((resource, SKOS.altLabel, Literal("Sistema aplicativo", lang="es")))
    query = OntologyQueryService(dataset, store.prefixes)

    assert query.search(str(resource))[0].iri == str(resource)
    assert query.search("Application")[0].iri == str(resource)
    assert query.search("aplicacion")[0].iri == str(resource)
    alternative = query.search("sistema aplicativo")[0]
    assert alternative.iri == str(resource)
    assert alternative.matched_fields == ("altLabel",)


def test_search_is_deterministic_bounded_and_handles_empty_text() -> None:
    _, query = services()

    first = [result.to_dict() for result in query.search("modulo", limit=3)]
    second = [result.to_dict() for result in query.search("módulo", limit=3)]

    assert first == second
    assert len(first) <= 3
    assert query.search(" -- ") == ()
    with pytest.raises(ValueError, match="limit"):
        query.search("application", limit=0)


def test_search_receipt_is_auditable_and_rejects_forgery_mismatch_and_staleness() -> None:
    store, _ = services()
    authority = SearchReceiptAuthority(b"receipt-test-secret" * 2)
    query = OntologyQueryService(
        store.dataset,
        store.prefixes,
        receipt_authority=authority,
        snapshot_id="snapshot-one",
    )

    first = query.search_page("Aplicación", limit=1)
    second = query.search_page("  aplicacion  ", limit=1)

    assert first.search_id == second.search_id
    assert query.validate_search_receipt("APLICACIÓN", first.search_id)
    assert not query.validate_search_receipt("unidad organizativa", first.search_id)
    tampered = first.search_id[:-1] + ("0" if first.search_id[-1] != "0" else "1")
    assert not query.validate_search_receipt("aplicación", tampered)
    other_authority = OntologyQueryService(
        store.dataset,
        store.prefixes,
        snapshot_id="snapshot-one",
    )
    stale_snapshot = OntologyQueryService(
        store.dataset,
        store.prefixes,
        receipt_authority=authority,
        snapshot_id="snapshot-two",
    )
    assert not other_authority.validate_search_receipt("aplicación", first.search_id)
    assert not stale_snapshot.validate_search_receipt("aplicación", first.search_id)
    receipt = authority.inspect(first.search_id)
    assert receipt is not None
    assert receipt.query == "aplicacion"
    assert receipt.snapshot == "snapshot-one"
    assert receipt.total >= 1
    assert receipt.result_count == 1
    assert receipt.rdf_types == ()
    assert receipt.modules == ()
    assert receipt.authoring_eligible
    with pytest.raises(ValueError, match="non-empty"):
        query.search_page("---")


def test_search_applies_type_and_module_filters_before_the_result_limit() -> None:
    _, query = services()

    result = query.search("ontology", modules=frozenset(("competency",)), limit=1)

    assert len(result) == 1
    assert result[0].modules == (f"{BASE}id/module/competency",)


def test_search_uses_effective_module_for_business_instances_and_paginates() -> None:
    _, query = services()

    page = query.search_page(
        "workbench",
        modules=frozenset(("software",)),
        limit=1,
    )
    second = query.search_page("ontology", limit=1, offset=1)
    complete = query.search_page("ontology", limit=500)

    assert page.total >= 1
    assert page.items[0].iri == f"{BASE}id/software/application/workbench"
    assert page.items[0].modules == (f"{BASE}id/module/software",)
    assert second.items == complete.items[1:2]
    assert second.total == complete.total


def test_search_receipts_bind_filters_and_authoring_requires_a_global_first_page() -> None:
    store, _ = services()
    authority = SearchReceiptAuthority(b"filter-receipt-secret" * 2)
    query = OntologyQueryService(
        store.dataset,
        store.prefixes,
        receipt_authority=authority,
        snapshot_id="filter-snapshot",
    )
    software = frozenset(("software",))
    class_type = frozenset((str(OWL.Class),))

    filtered = query.search_page("aplicación", modules=software, limit=20)
    typed = query.search_page("aplicación", rdf_types=class_type, limit=20)
    displaced = query.search_page("aplicación", offset=999, limit=20)
    empty_filtered = query.search_page(
        "aplicación",
        modules=frozenset(("missing-module",)),
        limit=20,
    )
    global_first_page = query.search_page("aplicación", limit=20)

    assert query.validate_search_receipt(
        "aplicación",
        filtered.search_id,
        modules=software,
        limit=20,
    )
    assert not query.validate_search_receipt("aplicación", filtered.search_id, limit=20)
    assert not query.validate_search_receipt(
        "aplicación",
        typed.search_id,
        modules=software,
        limit=20,
    )
    assert query.validate_search_receipt(
        "aplicación",
        displaced.search_id,
        offset=999,
        limit=20,
    )
    assert not query.validate_authoring_search_receipt("aplicación", filtered.search_id)
    assert not query.validate_authoring_search_receipt("aplicación", typed.search_id)
    assert not query.validate_authoring_search_receipt("aplicación", displaced.search_id)
    assert not query.validate_authoring_search_receipt("aplicación", empty_filtered.search_id)
    assert query.validate_authoring_search_receipt("aplicación", global_first_page.search_id)

    receipt = authority.inspect(filtered.search_id)
    assert receipt is not None
    assert receipt.modules == ("software",)
    assert receipt.rdf_types == ()


def test_search_indexes_iris_in_subject_predicate_and_object_positions() -> None:
    store, _ = services()
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/search/positions"))
    subject_only = URIRef(f"{BASE}id/search/subject_only")
    predicate_only = URIRef(f"{BASE}ontology/search#predicate_only")
    object_only = URIRef(f"{BASE}id/search/object_only")
    graph.add((subject_only, predicate_only, object_only))
    query = OntologyQueryService(dataset, store.prefixes)

    assert query.search(str(subject_only))[0].iri == str(subject_only)
    assert query.search("predicate_only")[0].iri == str(predicate_only)
    assert query.search(str(object_only))[0].iri == str(object_only)


def test_describe_exposes_proposal_status_for_a_reified_direct_relation() -> None:
    store, _ = services()
    dataset = store.load()
    graph_iri = URIRef(f"{BASE}graph/proposal-status")
    graph = dataset.graph(graph_iri)
    subject = URIRef(f"{BASE}id/software/application/proposal_status")
    predicate = URIRef(f"{BASE}ontology/software#supportsOrganizationUnit")
    obj = URIRef(f"{BASE}id/organization/unit/architecture")
    assertion = BNode()
    graph.add((subject, predicate, obj))
    graph.add((assertion, RDF.type, RDF.Statement))
    graph.add((assertion, RDF.subject, subject))
    graph.add((assertion, RDF.predicate, predicate))
    graph.add((assertion, RDF.object, obj))
    graph.add(
        (
            assertion,
            URIRef(f"{BASE}ontology/core#status"),
            Literal("proposed"),
        )
    )

    description = OntologyQueryService(dataset, store.prefixes).describe(subject)
    relation = next(quad for quad in description.outgoing if quad.predicate.value == str(predicate))

    assert relation.status == "proposed"


def test_describe_returns_metadata_types_and_graph_aware_relationships() -> None:
    _, query = services()
    application = f"{BASE}ontology/software#Application"

    description = query.describe(application)

    assert description is not None
    assert {item.value for item in description.types} == {str(OWL.Class)}
    assert any(item.value == "Aplicación" and item.language == "es" for item in description.labels)
    assert description.definitions
    assert {item.value for item in description.modules} == {f"{BASE}id/module/software"}
    assert {item.value for item in description.direct_modules} == {f"{BASE}id/module/software"}
    assert any(edge.predicate.value == str(RDF.type) for edge in description.outgoing)
    assert any(edge.predicate.value == str(RDFS.domain) for edge in description.incoming)
    assert all(edge.graph.kind == "iri" for edge in description.outgoing + description.incoming)
    assert query.describe(f"{BASE}id/missing") is None


def test_describe_exposes_effective_and_direct_module_ownership() -> None:
    _, query = services()

    description = query.describe(f"{BASE}id/software/application/workbench")

    assert description is not None
    assert {item.value for item in description.modules} == {f"{BASE}id/module/software"}
    assert description.direct_modules == ()


def test_describe_preserves_blank_nodes() -> None:
    store, _ = services()
    technical = BNode("technical")
    graph = store.dataset.graph(URIRef(f"{BASE}graph/ontology/software"))
    graph.add((technical, RDF.type, OWL.Class))
    graph.add((URIRef(f"{BASE}ontology/software#Application"), RDFS.subClassOf, technical))

    description = OntologyQueryService(store.dataset, store.prefixes).describe(technical)

    assert description is not None
    assert description.resource.kind == "bnode"
    assert any(edge.object.kind == "bnode" for edge in description.incoming)


def test_describe_includes_hierarchy_property_contract_provenance_and_usage() -> None:
    store, _ = services()
    graph = store.dataset.graph(URIRef(f"{BASE}graph/ontology/software"))
    parent = URIRef(f"{BASE}ontology/software#ParentApplication")
    child = URIRef(f"{BASE}ontology/software#ChildApplication")
    application = URIRef(f"{BASE}ontology/software#Application")
    supports = URIRef(f"{BASE}ontology/software#supportsOrganizationUnit")
    graph.add((application, RDFS.subClassOf, parent))
    graph.add((child, RDFS.subClassOf, application))
    query = OntologyQueryService(store.dataset, store.prefixes)

    class_detail = query.describe(application)
    property_detail = query.describe(supports)

    assert class_detail is not None and property_detail is not None
    assert {value.value for value in class_detail.superclasses} == {str(parent)}
    assert {value.value for value in class_detail.subclasses} == {str(child)}
    assert property_detail.domains and property_detail.ranges
    assert property_detail.provenance
    assert property_detail.predicate_uses


def test_describe_recognizes_predicate_only_resource_and_its_graph_provenance() -> None:
    store, _ = services()
    dataset = Dataset()
    graph_iri = URIRef(f"{BASE}graph/source/predicate-only")
    metadata_graph = dataset.graph(URIRef(f"{BASE}graph/metadata/predicate-only"))
    predicate = URIRef("https://external.example/vocabulary/predicate-only")
    activity = URIRef(f"{BASE}id/activity/predicate-only")
    dataset.graph(graph_iri).add(
        (URIRef(f"{BASE}id/predicate-only/subject"), predicate, Literal("value"))
    )
    metadata_graph.add((graph_iri, PROV.wasGeneratedBy, activity))

    description = OntologyQueryService(dataset, store.prefixes).describe(predicate)

    assert description is not None
    assert description.outgoing == ()
    assert description.incoming == ()
    assert len(description.predicate_uses) == 1
    assert [quad.graph.value for quad in description.predicate_uses] == [str(graph_iri)]
    assert any(
        quad.subject.value == str(graph_iri)
        and quad.predicate.value == str(PROV.wasGeneratedBy)
        and quad.object.value == str(activity)
        for quad in description.provenance
    )


def test_module_descriptions_include_owner_terms_and_import_cycles() -> None:
    store, query = services()
    software = next(
        module
        for module in query.modules(store.discover_modules())
        if module.identifier == "software"
    )

    assert {value.value for value in software.responsible} == {"Equipo de arquitectura de software"}
    assert {value.value for value in software.classes} == {
        f"{BASE}ontology/software#Application",
        f"{BASE}ontology/software#SoftwareComponent",
        f"{BASE}ontology/software#SourceCodeRepository",
    }
    assert {value.value for value in software.properties} == {
        f"{BASE}ontology/software#implementedByRepository",
        f"{BASE}ontology/software#isComposedOf",
        f"{BASE}ontology/software#supportsOrganizationUnit",
    }
    assert software.import_cycles == ()

    core = URIRef(f"{BASE}ontology/core")
    software_ontology = URIRef(f"{BASE}ontology/software")
    store.dataset.graph(URIRef(f"{BASE}graph/ontology/core")).add(
        (core, OWL.imports, software_ontology)
    )
    cyclic = OntologyQueryService(store.dataset, store.prefixes).modules(store.discover_modules())

    core_description = next(module for module in cyclic if module.identifier == "core")
    software_description = next(module for module in cyclic if module.identifier == "software")
    assert core_description.import_cycles
    assert software_description.import_cycles
    assert core_description.import_cycles == software_description.import_cycles


def test_neighborhood_supports_depth_filters_and_safe_limits() -> None:
    _, query = services()
    center = f"{BASE}ontology/software#Application"

    depth_zero = query.neighborhood(center, depth=0)
    depth_two = query.neighborhood(center, depth=2)
    filtered = query.neighborhood(
        center,
        depth=2,
        filters=NeighborhoodFilter(predicates=frozenset({str(RDFS.domain)})),
    )
    bounded = query.neighborhood(
        center,
        depth=2,
        limits=NeighborhoodLimits(max_depth=2, max_nodes=2, max_edges=1),
    )

    assert len(depth_zero.nodes) == 1 and not depth_zero.edges
    assert len(depth_two.nodes) > len(depth_zero.nodes)
    assert all(edge.predicate.value == str(RDFS.domain) for edge in filtered.edges)
    assert len(bounded.nodes) <= 2
    assert len(bounded.edges) <= 1
    assert bounded.truncated
    with pytest.raises(ValueError, match="depth"):
        query.neighborhood(center, depth=4)


def test_neighborhood_classifies_canonical_modules_and_business_individuals() -> None:
    _, query = services()
    module = query.neighborhood(f"{BASE}id/module/software", depth=0)
    individual = query.neighborhood(
        f"{BASE}id/software/application/workbench",
        depth=0,
    )
    application = query.neighborhood(f"{BASE}ontology/software#Application", depth=0)

    assert module.center.category == "module"
    assert module.center.module == "software"
    assert individual.center.category == "individual"
    assert individual.center.module == "software"
    assert application.center.category == "class"
    assert application.center.module == "software"


def test_category_counts_use_the_same_business_individual_classification() -> None:
    store, query = services()
    workbench = URIRef(f"{BASE}id/software/application/workbench")

    assert query.resource_category(workbench) == "individual"
    assert query.category_counts().individuals == sum(
        query.resource_category(node) == "individual"
        for node in {
            value
            for subject, _, obj, _ in store.dataset.quads((None, None, None, None))
            for value in (subject, obj)
            if isinstance(value, (URIRef, BNode))
        }
    )


def test_resource_category_recognizes_instance_of_declared_business_class() -> None:
    store, _ = services()
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/classification/business"))
    business_class = URIRef(f"{BASE}ontology/business#BusinessEntity")
    instance = URIRef(f"{BASE}id/business/entity/example")
    graph.add((business_class, RDF.type, OWL.Class))
    graph.add((instance, RDF.type, business_class))
    query = OntologyQueryService(dataset, store.prefixes)

    assert query.resource_category(instance) == "individual"


def test_neighborhood_filters_graph_and_rdf_type_without_losing_center() -> None:
    _, query = services()
    center = f"{BASE}ontology/software#Application"
    graph = f"{BASE}graph/ontology/software"

    result = query.neighborhood(
        center,
        depth=1,
        filters=NeighborhoodFilter(
            graph_iris=frozenset({graph}),
            rdf_types=frozenset({str(OWL.ObjectProperty)}),
        ),
    )

    assert result.center in result.nodes
    assert all(edge.graph.value == graph for edge in result.edges)


def test_neighborhood_omits_edges_to_nodes_excluded_by_type_or_node_limit() -> None:
    store, _ = services()
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/neighborhood/consistent"))
    center = URIRef(f"{BASE}id/neighborhood/center")
    class_node = URIRef(f"{BASE}ontology/neighborhood#ClassNode")
    property_node = URIRef(f"{BASE}ontology/neighborhood#propertyNode")
    relates = URIRef(f"{BASE}ontology/neighborhood#relates")
    graph.add((center, relates, class_node))
    graph.add((center, relates, property_node))
    graph.add((class_node, RDF.type, OWL.Class))
    graph.add((property_node, RDF.type, OWL.ObjectProperty))
    query = OntologyQueryService(dataset, store.prefixes)

    filtered = query.neighborhood(
        center,
        depth=1,
        filters=NeighborhoodFilter(rdf_types=frozenset({str(OWL.ObjectProperty)})),
    )
    bounded = query.neighborhood(
        center,
        depth=1,
        limits=NeighborhoodLimits(max_depth=1, max_nodes=1, max_edges=10),
    )

    filtered_nodes = {(node.kind, node.value) for node in filtered.nodes}
    assert ("iri", str(property_node)) in filtered_nodes
    assert ("iri", str(class_node)) not in filtered_nodes
    assert all(
        (edge.subject.kind, edge.subject.value) in filtered_nodes
        and (edge.object.kind, edge.object.value) in filtered_nodes
        for edge in filtered.edges
    )
    assert {node.value for node in bounded.nodes} == {str(center)}
    assert bounded.edges == ()
    assert bounded.truncated


def test_neighborhood_includes_and_counts_literal_endpoints() -> None:
    store, _ = services()
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/neighborhood/literals"))
    center = URIRef(f"{BASE}id/neighborhood/literal_center")
    predicate = URIRef(f"{BASE}ontology/neighborhood#literalValue")
    value = Literal("valor", lang="es")
    graph.add((center, predicate, value))
    query = OntologyQueryService(dataset, store.prefixes)

    included = query.neighborhood(
        center,
        depth=1,
        limits=NeighborhoodLimits(max_depth=1, max_nodes=2, max_edges=1),
    )
    excluded = query.neighborhood(
        center,
        depth=1,
        limits=NeighborhoodLimits(max_depth=1, max_nodes=1, max_edges=1),
    )

    node_keys = {(node.kind, node.value) for node in included.nodes}
    assert node_keys == {("iri", str(center)), ("literal", "valor")}
    assert len(included.edges) == 1
    assert all(
        (edge.subject.kind, edge.subject.value) in node_keys
        and (edge.object.kind, edge.object.value) in node_keys
        for edge in included.edges
    )
    assert {(node.kind, node.value) for node in excluded.nodes} == {("iri", str(center))}
    assert excluded.edges == ()
    assert excluded.truncated


def test_neighborhood_assigns_and_orders_mandatory_relationship_priorities() -> None:
    store, _ = services()
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/relationship-priority"))
    center = URIRef(f"{BASE}ontology/priority#Center")
    internal = URIRef(f"{BASE}ontology/priority#relatesTo")
    other = URIRef("https://external.example/vocabulary/related")
    predicates = (
        RDFS.subClassOf,
        RDFS.subPropertyOf,
        RDFS.domain,
        RDFS.range,
        OWL.imports,
        internal,
        other,
    )
    graph.add((internal, RDF.type, OWL.ObjectProperty))
    for index, predicate in enumerate(reversed(predicates)):
        graph.add((center, predicate, URIRef(f"{BASE}id/priority/target_{index}")))

    neighborhood = OntologyQueryService(dataset, store.prefixes).neighborhood(
        center,
        depth=1,
        limits=NeighborhoodLimits(max_depth=1, max_nodes=8, max_edges=7),
    )

    assert [edge.priority for edge in neighborhood.edges] == list(range(1, 8))
    assert [edge.relationship_kind for edge in neighborhood.edges] == [
        "subclass",
        "subproperty",
        "domain",
        "range",
        "import",
        "internal_object_property",
        "other",
    ]


def test_stats_count_dataset_modules_and_types_without_default_graph_collapse() -> None:
    store, query = services()

    stats = query.stats(store.discover_modules())

    assert stats.quads == sum(len(graph) for graph in store.dataset.graphs())
    assert stats.named_graphs == 14
    assert stats.resources > 0
    assert dict(stats.types)[str(OWL.Class)] >= 3
    assert [module.module_id for module in stats.modules] == [
        "competency",
        "core",
        "knowledge_governance",
        "organization",
        "software",
    ]
    software = next(module for module in stats.modules if module.module_id == "software")
    assert software.graph_iri == f"{BASE}graph/ontology/software"
    assert dict(software.types)[str(OWL.ObjectProperty)] == 3
    assert len(store.dataset.default_graph) == 0


def test_stats_count_identified_nodes_in_all_rdf_positions() -> None:
    store, _ = services()
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/stats/positions"))
    subject = URIRef(f"{BASE}id/stats/subject")
    predicate = URIRef(f"{BASE}ontology/stats#predicate")
    obj = URIRef(f"{BASE}id/stats/object")
    graph.add((subject, predicate, obj))
    graph.add((subject, predicate, Literal("literal")))

    stats = OntologyQueryService(dataset, store.prefixes).stats()

    assert stats.resources == 3


def test_neighborhood_limit_configuration_rejects_unsafe_values() -> None:
    with pytest.raises(ValueError):
        NeighborhoodLimits(max_nodes=0)
    with pytest.raises(ValueError):
        NeighborhoodLimits(max_edges=15001)
    with pytest.raises(ValueError):
        NeighborhoodLimits(max_depth=11)


def test_queries_remain_bounded_on_the_initial_fifty_thousand_triple_target() -> None:
    store, _ = services()
    dataset = Dataset()
    graph = dataset.graph(URIRef(f"{BASE}graph/performance/fixture"))
    predicate = URIRef(f"{BASE}ontology/performance#value")
    for index in range(50_000):
        graph.add((URIRef(f"{BASE}id/performance/item_{index}"), predicate, Literal(index)))
    query = OntologyQueryService(dataset, store.prefixes)

    stats = query.stats()
    neighborhood = query.neighborhood(
        f"{BASE}id/performance/item_1",
        depth=1,
        limits=NeighborhoodLimits(max_nodes=5, max_edges=5),
    )

    assert stats.quads == 50_000
    assert len(neighborhood.nodes) <= 5
    assert len(neighborhood.edges) <= 5

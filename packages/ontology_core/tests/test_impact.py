from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from ontology_core import FilesystemRdfStore, ImpactService
from rdflib import BNode, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

ROOT = Path(__file__).parents[3]
BASE = "https://knowledge.example.com/"


def impact_service() -> tuple[FilesystemRdfStore, ImpactService]:
    store = FilesystemRdfStore(ROOT / "knowledge", ROOT / "config" / "namespace.yaml")
    dataset = store.load()
    return store, ImpactService(dataset, store.prefixes, store=store)


def test_impact_returns_incoming_and_outgoing_references_with_graph_identity() -> None:
    _, impact = impact_service()
    application = f"{BASE}ontology/software#Application"

    report = impact.analyze(application)

    assert any(item.predicate.value == str(RDF.type) for item in report.outgoing)
    assert any(item.predicate.value == str(RDFS.domain) for item in report.incoming)
    assert all(item.graph.kind == "iri" for item in report.outgoing + report.incoming)


def test_impact_reports_property_uses_in_predicate_position() -> None:
    _, impact = impact_service()
    property_iri = f"{BASE}ontology/software#supportsOrganizationUnit"

    report = impact.analyze(property_iri)

    assert len(report.predicate_uses) == 1
    use = report.predicate_uses[0]
    assert use.subject.value == f"{BASE}id/software/application/workbench"
    assert use.predicate.value == property_iri
    assert use.object.value == f"{BASE}id/organization/unit/architecture"


def test_impact_walks_class_and_property_hierarchies_transitively() -> None:
    store, _ = impact_service()
    graph = store.dataset.graph(URIRef(f"{BASE}graph/ontology/software"))
    parent = URIRef(f"{BASE}ontology/software#SoftwareSystem")
    child = URIRef(f"{BASE}ontology/software#BusinessApplication")
    application = URIRef(f"{BASE}ontology/software#Application")
    graph.add((application, RDFS.subClassOf, parent))
    graph.add((child, RDFS.subClassOf, application))
    impact = ImpactService(store.dataset, store.prefixes, store=store)

    report = impact.analyze(application)

    assert {node.value for node in report.ancestors} == {str(parent)}
    assert {node.value for node in report.descendants} == {str(child)}


def test_impact_identifies_shapes_and_separates_dependencies_from_importers() -> None:
    _, impact = impact_service()

    application = impact.analyze(f"{BASE}ontology/software#Application")
    organization = impact.analyze(f"{BASE}ontology/organization#OrganizationUnit")

    assert f"{BASE}shape/governance/TermShape" in {shape.value for shape in application.shapes}
    assert {question.value.rsplit("/", 1)[-1] for question in application.competency_questions} == {
        "applications_exist",
        "missing_domain_fixture",
    }
    assert {module.value for module in application.import_dependencies} == {
        f"{BASE}ontology/core",
        f"{BASE}ontology/organization",
    }
    assert {module.value for module in application.affected_importers} == {
        f"{BASE}ontology/knowledge_governance"
    }
    assert {module.value for module in organization.import_dependencies} == {f"{BASE}ontology/core"}
    assert {module.value for module in organization.affected_importers} == {
        f"{BASE}ontology/knowledge_governance",
        f"{BASE}ontology/software",
    }


def test_import_impact_is_transitive_directional_and_cycle_safe() -> None:
    store, _ = impact_service()
    graph = store.dataset.graph(URIRef(f"{BASE}graph/ontology/import-impact"))
    module_c = URIRef(f"{BASE}id/module/import_c")
    term_c = URIRef(f"{BASE}ontology/import_c#TermC")
    ontology_a = URIRef(f"{BASE}ontology/import_a")
    ontology_b = URIRef(f"{BASE}ontology/import_b")
    ontology_c = URIRef(f"{BASE}ontology/import_c")
    ontology_d = URIRef(f"{BASE}ontology/import_d")
    ontology_e = URIRef(f"{BASE}ontology/import_e")
    graph.add((term_c, DCTERMS.isPartOf, module_c))
    graph.add((ontology_c, RDF.type, OWL.Ontology))
    graph.add((ontology_c, DCTERMS.isPartOf, module_c))
    graph.add((ontology_a, OWL.imports, ontology_b))
    graph.add((ontology_b, OWL.imports, ontology_c))
    graph.add((ontology_c, OWL.imports, ontology_d))
    graph.add((ontology_d, OWL.imports, ontology_e))
    graph.add((ontology_e, OWL.imports, ontology_d))
    impact = ImpactService(store.dataset, store.prefixes, store=store)

    first = impact.analyze(term_c)
    second = impact.analyze(term_c)

    assert {node.value for node in first.import_dependencies} == {
        str(ontology_d),
        str(ontology_e),
    }
    assert {node.value for node in first.affected_importers} == {
        str(ontology_a),
        str(ontology_b),
    }
    assert first.to_dict() == second.to_dict()


def test_impact_preserves_technical_blank_nodes_and_is_deterministic() -> None:
    store, _ = impact_service()
    technical = BNode("restriction")
    application = URIRef(f"{BASE}ontology/software#Application")
    graph = store.dataset.graph(URIRef(f"{BASE}graph/ontology/software"))
    graph.add((application, RDFS.subClassOf, technical))
    graph.add((technical, RDF.type, OWL.Restriction))
    impact = ImpactService(store.dataset, store.prefixes, store=store)

    first = impact.analyze(application)
    second = impact.analyze(application)

    assert any(node.kind == "bnode" for node in first.ancestors)
    assert first.to_dict() == second.to_dict()


def test_impact_rejects_a_partial_local_shape_catalog(tmp_path: Path) -> None:
    copied = tmp_path / "knowledge"
    shutil.copytree(ROOT / "knowledge", copied)
    (copied / "shapes" / "governance.ttl").unlink()
    irrelevant = copied / "shapes" / "modules" / "irrelevant.ttl"
    irrelevant.write_text(
        """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix shape: <https://knowledge.example.com/shape/modules/> .
shape:IrrelevantShape a sh:NodeShape .
""",
        encoding="utf-8",
    )
    store = FilesystemRdfStore(copied, ROOT / "config" / "namespace.yaml")

    with pytest.raises(ValueError, match="complete local SHACL shape catalog"):
        ImpactService(store.load(), store.prefixes, store=store)


def test_impact_loads_every_applicable_local_module_shape(tmp_path: Path) -> None:
    copied = tmp_path / "knowledge"
    shutil.copytree(ROOT / "knowledge", copied)
    module_shape = copied / "shapes" / "modules" / "application.ttl"
    module_shape.write_text(
        """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix shape: <https://knowledge.example.com/shape/modules/> .
@prefix software: <https://knowledge.example.com/ontology/software#> .
shape:ApplicationShape a sh:NodeShape ;
    sh:targetNode software:Application .
""",
        encoding="utf-8",
    )
    store = FilesystemRdfStore(copied, ROOT / "config" / "namespace.yaml")
    impact = ImpactService(store.load(), store.prefixes, store=store)

    report = impact.analyze(f"{BASE}ontology/software#Application")

    assert f"{BASE}shape/modules/ApplicationShape" in {shape.value for shape in report.shapes}
    assert tuple(path.relative_to(copied).as_posix() for path in impact.shape_sources) == (
        "shapes/governance.ttl",
        "shapes/modules/application.ttl",
    )

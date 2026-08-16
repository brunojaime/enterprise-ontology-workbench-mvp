from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from ontology_core import (
    AgentContextService,
    ContextBudget,
    ContextBudgetError,
    ContextRequest,
    FilesystemRdfStore,
    ImpactService,
)
from rdflib import Dataset, URIRef
from rdflib.namespace import OWL, RDF

ROOT = Path(__file__).parents[3]
BASE = "https://knowledge.example.com/"


def context_service() -> tuple[FilesystemRdfStore, AgentContextService]:
    store = FilesystemRdfStore(ROOT / "knowledge", ROOT / "config" / "namespace.yaml")
    service = AgentContextService(store)
    return store, service


def test_context_constructs_every_collaborator_from_one_store_dataset() -> None:
    store = FilesystemRdfStore(ROOT / "knowledge", ROOT / "config" / "namespace.yaml")
    service = AgentContextService(store)
    pack = service.generate(ContextRequest(task="Describir aplicación", terms=("aplicación",)))

    assert service.dataset is store.dataset
    assert service.query.dataset is service.dataset
    assert service.impact.dataset is service.dataset
    assert service.questions.dataset is service.dataset
    assert service.query.prefixes is store.prefixes
    assert service.impact.prefixes is store.prefixes
    assert f"{BASE}shape/governance/TermShape" in pack.payload["shapes"]
    assert (
        URIRef(f"{BASE}shape/governance/TermShape"),
        RDF.type,
        URIRef("http://www.w3.org/ns/shacl#NodeShape"),
    ) in service.impact.shapes_graph
    assert (
        URIRef(f"{BASE}shape/governance/PropertyShape"),
        RDF.type,
        URIRef("http://www.w3.org/ns/shacl#NodeShape"),
    ) in service.impact.shapes_graph


def test_impact_rejects_a_different_dataset_even_with_the_same_store_root() -> None:
    store = FilesystemRdfStore(ROOT / "knowledge", ROOT / "config" / "namespace.yaml")
    store.load()
    empty_dataset = Dataset()

    with pytest.raises(ValueError, match="current Dataset loaded by its store"):
        ImpactService(empty_dataset, store.prefixes, store=store)

    other_store = FilesystemRdfStore(ROOT / "knowledge", ROOT / "config" / "namespace.yaml")
    with pytest.raises(ValueError, match="PrefixResolver owned by its store"):
        ImpactService(store.dataset, other_store.prefixes, store=store)


def test_context_does_not_expose_injection_paths_for_mismatched_collaborators() -> None:
    store = FilesystemRdfStore(ROOT / "knowledge", ROOT / "config" / "namespace.yaml")

    with pytest.raises(TypeError, match="unexpected keyword argument 'impact'"):
        AgentContextService(store, impact=object())  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="unexpected keyword argument 'query'"):
        AgentContextService(store, query=object())  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="unexpected keyword argument 'questions'"):
        AgentContextService(store, questions=object())  # type: ignore[call-arg]


def test_context_canonical_construction_loads_additional_module_shapes(tmp_path: Path) -> None:
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
    service = AgentContextService(store)

    pack = service.generate(ContextRequest(task="Describir aplicación", terms=("aplicación",)))

    assert f"{BASE}shape/modules/ApplicationShape" in pack.payload["shapes"]


def test_context_pack_contains_the_structured_contract_in_json_and_markdown() -> None:
    _, service = context_service()
    request = ContextRequest(
        task="Relacionar una aplicación con una unidad organizativa",
        terms=("aplicación", "unidad organizativa"),
        modules=("organization", "software"),
        budget=ContextBudget(max_bytes=128 * 1024),
    )

    pack = service.generate(request)
    parsed = json.loads(pack.json)

    assert parsed == pack.payload
    assert set(parsed) == {
        "task",
        "retrieval",
        "rules",
        "prefixes",
        "modules",
        "terms",
        "similar_terms",
        "neighborhoods",
        "shapes",
        "competency_questions",
        "examples",
        "counterexamples",
        "validation_commands",
        "limits",
    }
    assert parsed["retrieval"] == "structured_rdf"
    assert {term["iri"] for term in parsed["terms"]} >= {
        f"{BASE}ontology/software#Application",
        f"{BASE}ontology/organization#OrganizationUnit",
    }
    assert f"{BASE}shape/governance/TermShape" in parsed["shapes"]
    assert "# Contexto de agente" in pack.markdown
    assert "software:Application" in pack.markdown
    for key, value in parsed.items():
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert serialized in pack.markdown, f"Markdown omitted the {key} contract"


def test_context_is_deterministic_and_preserves_the_dataset() -> None:
    store, service = context_service()
    request = ContextRequest(task="Describir aplicación", terms=("aplicación",))
    before = set(store.dataset.quads((None, None, None, None)))

    first = service.generate(request)
    second = service.generate(request)

    assert first.json == second.json
    assert first.markdown == second.markdown
    assert set(store.dataset.quads((None, None, None, None))) == before
    assert len(store.dataset.default_graph) == 0


def test_context_respects_term_depth_and_byte_budgets() -> None:
    _, service = context_service()
    budget = ContextBudget(max_terms=1, depth=0, max_bytes=8192)
    request = ContextRequest(
        task="Revisar módulos, aplicación y unidad organizativa",
        terms=("módulo", "aplicación", "unidad organizativa"),
        budget=budget,
    )

    pack = service.generate(request)

    assert len(pack.payload["terms"]) <= 1
    assert all(neighborhood["depth"] == 0 for neighborhood in pack.payload["neighborhoods"])
    assert len(pack.json.encode("utf-8")) <= budget.max_bytes
    assert len(pack.markdown.encode("utf-8")) <= budget.max_bytes
    assert pack.truncated


def test_context_module_filter_expands_imports_for_modules_terms_and_questions() -> None:
    _, service = context_service()
    request = ContextRequest(
        task="Consultar el módulo software",
        terms=("aplicación", "unidad organizativa"),
        modules=("software",),
    )

    pack = service.generate(request)

    assert [module["id"] for module in pack.payload["modules"]] == [
        "core",
        "organization",
        "software",
    ]
    allowed_owners = {
        f"{BASE}id/module/core",
        f"{BASE}id/module/organization",
        f"{BASE}id/module/software",
    }
    assert all(allowed_owners.intersection(term["modules"]) for term in pack.payload["terms"])
    assert all(
        question["module"] in allowed_owners for question in pack.payload["competency_questions"]
    )


def test_context_import_expansion_respects_depth_and_cycles_deterministically() -> None:
    _, service = context_service()
    core = URIRef(f"{BASE}ontology/core")
    software = URIRef(f"{BASE}ontology/software")
    core_graph = service.dataset.graph(URIRef(f"{BASE}graph/ontology/core"))
    core_graph.add((core, OWL.imports, software))

    depth_zero = service.generate(
        ContextRequest(
            task="Consultar software",
            modules=("software",),
            budget=ContextBudget(depth=0),
        )
    )
    request = ContextRequest(
        task="Consultar software con imports cíclicos",
        modules=("software",),
        budget=ContextBudget(depth=5),
    )
    first = service.generate(request)
    second = service.generate(request)

    assert [module["id"] for module in depth_zero.payload["modules"]] == ["software"]
    expanded_ids = [module["id"] for module in first.payload["modules"]]
    assert expanded_ids == ["core", "organization", "software"]
    assert len(expanded_ids) == len(set(expanded_ids))
    assert first.json == second.json
    assert first.markdown == second.markdown


def test_context_budget_rejects_unsafe_or_impossible_configuration() -> None:
    with pytest.raises(ContextBudgetError, match="max_terms"):
        ContextBudget(max_terms=0)
    with pytest.raises(ContextBudgetError, match="depth"):
        ContextBudget(depth=6)
    with pytest.raises(ContextBudgetError, match="max_bytes"):
        ContextBudget(max_bytes=4095)
    with pytest.raises(ValueError, match="task"):
        ContextRequest(task="   ")


def test_context_uses_no_vector_or_document_retrieval_contract() -> None:
    _, service = context_service()

    pack = service.generate(ContextRequest(task="Buscar aplicación", terms=("aplicación",)))
    lowered = pack.json.casefold()

    assert "embedding" not in lowered
    assert '"rag"' not in lowered
    assert pack.payload["retrieval"] == "structured_rdf"

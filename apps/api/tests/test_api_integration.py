from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from enterprise_ontology_api.config import ApiSettings
from enterprise_ontology_api.main import app, create_app
from enterprise_ontology_api.runtime import (
    RepositoryRevision,
    RuntimeManager,
    read_repository_revision,
)
from fastapi.testclient import TestClient
from ontology_core import GitWorkspaceError, GitWorkspaceService
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF

ROOT = Path(__file__).parents[3]
BASE = "https://knowledge.example.com/"
APPLICATION = f"{BASE}ontology/software#Application"
SUPPORTS = f"{BASE}ontology/software#supportsOrganizationUnit"
WORKBENCH = f"{BASE}id/software/application/workbench"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as active:
        yield active


def assert_error(response: object, status: int, code: str) -> None:
    assert response.status_code == status
    payload = response.json()
    assert payload["code"] == code
    assert isinstance(payload["message"], str)
    assert isinstance(payload["details"], dict)


def search_receipt(client: TestClient, query: str) -> str:
    response = client.get("/api/resources/search", params={"q": query, "limit": 20})
    assert response.status_code == 200
    value = response.json()["search_id"]
    assert isinstance(value, str)
    return value


def test_workspace_modules_and_status_share_one_snapshot(client: TestClient) -> None:
    workspace = client.get("/api/workspace")
    modules = client.get("/api/modules")
    status = client.get("/api/workspace/status")

    assert workspace.status_code == modules.status_code == status.status_code == 200
    assert workspace.json()["runtime"] == status.json()
    assert [module["id"] for module in modules.json()["items"]] == [
        "competency",
        "core",
        "knowledge_governance",
        "organization",
        "software",
    ]
    assert workspace.json()["stats"]["named_graphs"] == 14
    assert workspace.json()["agent_contract_status"] == "synchronized"
    assert workspace.json()["module_count"] == 5
    assert workspace.json()["class_count"] >= 3
    assert workspace.json()["property_count"] >= 1
    assert workspace.json()["concept_count"] == 1
    assert workspace.json()["individual_count"] >= 1
    assert workspace.json()["pending_changes"] == workspace.json()["runtime"]["revision"]["dirty"]
    assert modules.json() == {
        **modules.json(),
        "total": 5,
        "offset": 0,
        "limit": 20,
        "has_next": False,
    }


def test_readiness_fails_when_the_git_worktree_is_unavailable(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    local_app = create_app(
        settings,
        revision_provider=lambda: RepositoryRevision(None, None, False, "fixture"),
    )

    with TestClient(local_app) as local:
        response = local.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["api"]["status"] == "pass"
    assert payload["checks"]["dataset"]["status"] == "pass"
    assert payload["checks"]["worktree"]["status"] == "fail"


def test_readiness_reloads_current_rdf_and_normalizes_parser_failure(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    revision = RepositoryRevision("main", "a" * 40, True, "fixture")
    local_app = create_app(settings, revision_provider=lambda: revision)
    with TestClient(local_app) as local:
        assert local.get("/ready").status_code == 200
        source = tmp_path / "knowledge/ontology/software/terms/Application.ttl"
        source.write_text("@prefix broken: <not closed", encoding="utf-8")
        response = local.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["dataset"]["status"] == "fail"
    assert payload["checks"]["worktree"]["status"] == "pass"
    assert "Application.ttl" not in response.text


def test_readiness_reloads_parseable_but_nonconforming_rdf(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    revision = RepositoryRevision("main", "a" * 40, True, "fixture")
    local_app = create_app(settings, revision_provider=lambda: revision)
    with TestClient(local_app) as local:
        assert local.get("/ready").status_code == 200
        source = tmp_path / "knowledge/ontology/software/terms/Application.ttl"
        original = source.read_text(encoding="utf-8")
        changed = original.replace('    skos:prefLabel "Aplicación"@es ;\n', "")
        assert changed != original
        source.write_text(changed, encoding="utf-8")
        response = local.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["dataset"]["status"] == "fail"
    assert payload["checks"]["worktree"]["status"] == "pass"
    assert "Application.ttl" not in response.text


def test_module_list_paginates_deterministically(client: TestClient) -> None:
    first = client.get("/api/modules", params={"offset": 0, "limit": 2}).json()
    second = client.get("/api/modules", params={"offset": 2, "limit": 2}).json()
    third = client.get("/api/modules", params={"offset": 4, "limit": 2}).json()

    assert first["total"] == second["total"] == third["total"] == 5
    assert first["has_next"] is True
    assert second["has_next"] is True
    assert third["has_next"] is False
    assert [item["id"] for item in first["items"] + second["items"] + third["items"]] == [
        "competency",
        "core",
        "knowledge_governance",
        "organization",
        "software",
    ]


def test_module_metadata_and_bounded_named_graph(client: TestClient) -> None:
    module = client.get("/api/modules/software")
    graph = client.get("/api/modules/software/graph", params={"limit": 2})
    raw = client.get("/api/modules/software/raw")

    assert module.status_code == graph.status_code == raw.status_code == 200
    assert module.json()["imports"] == [
        f"{BASE}ontology/core",
        f"{BASE}ontology/organization",
    ]
    assert module.json()["responsible"][0]["value"] == ("Equipo de arquitectura de software")
    assert {item["value"] for item in module.json()["classes"]} == {
        APPLICATION,
        f"{BASE}ontology/software#SoftwareComponent",
        f"{BASE}ontology/software#SourceCodeRepository",
    }
    assert {item["value"] for item in module.json()["properties"]} == {
        SUPPORTS,
        f"{BASE}ontology/software#implementedByRepository",
        f"{BASE}ontology/software#isComposedOf",
    }
    assert module.json()["import_cycles"] == []
    assert len(graph.json()["quads"]) == 2
    assert graph.json()["truncated"] is True
    assert {quad["graph"]["value"] for quad in graph.json()["quads"]} == {
        f"{BASE}graph/ontology/software"
    }
    assert raw.headers["content-type"].startswith("text/turtle")
    assert "software:Application" in raw.text
    assert "software:supportsOrganizationUnit" in raw.text
    assert_error(client.get("/api/modules/absent"), 404, "module.not_found")
    assert_error(client.get("/api/modules/absent/raw"), 404, "module.not_found")


def test_module_terms_paginate_as_one_deterministic_list(client: TestClient) -> None:
    first = client.get("/api/modules/software", params={"term_offset": 0, "term_limit": 1}).json()
    second = client.get("/api/modules/software", params={"term_offset": 1, "term_limit": 1}).json()
    last = client.get("/api/modules/software", params={"term_offset": 5, "term_limit": 1}).json()

    assert first["term_total"] == second["term_total"] == last["term_total"] == 6
    assert first["terms_has_next"] is True
    assert second["terms_has_next"] is True
    assert last["terms_has_next"] is False
    assert [item["value"] for item in first["classes"] + first["properties"]] == [APPLICATION]
    assert [item["value"] for item in second["classes"] + second["properties"]] == [
        f"{BASE}ontology/software#SoftwareComponent"
    ]
    assert [item["value"] for item in last["classes"] + last["properties"]] == [SUPPORTS]


def test_search_describe_and_filters(client: TestClient) -> None:
    search = client.get("/api/resources/search", params={"q": "aplicacion"})
    by_module = client.get(
        "/api/resources/search", params={"q": "Application", "module": "software"}
    )
    description = client.get("/api/resources/describe", params={"iri": APPLICATION})
    filtered_before_limit = client.get(
        "/api/resources/search",
        params={"q": "ontology", "module": "competency", "limit": 1},
    )
    property_description = client.get("/api/resources/describe", params={"iri": SUPPORTS})

    assert search.status_code == by_module.status_code == description.status_code == 200
    assert any(result["iri"] == APPLICATION for result in search.json()["items"])
    assert all(result["modules"] for result in by_module.json()["items"])
    assert description.json()["resource"]["value"] == APPLICATION
    assert description.json()["outgoing"]
    assert filtered_before_limit.json()["total"] >= 1
    assert len(filtered_before_limit.json()["items"]) == 1
    assert filtered_before_limit.json()["items"][0]["modules"] == [f"{BASE}id/module/competency"]
    detail = property_description.json()
    expected_fields = {
        "superclasses",
        "subclasses",
        "domains",
        "ranges",
        "shapes",
        "provenance",
        "git_history",
        "usage",
        "predicate_uses",
        "direct_modules",
    }
    assert expected_fields <= detail.keys()
    assert detail["domains"] and detail["ranges"] and detail["shapes"]
    assert detail["provenance"] and detail["predicate_uses"]
    assert detail["git_history"] == []
    assert detail["usage"]["predicate_uses"] >= 1
    assert_error(
        client.get("/api/resources/describe", params={"iri": f"{BASE}id/missing"}),
        404,
        "resource.not_found",
    )


def test_effective_module_is_consistent_across_stats_search_and_describe(
    client: TestClient,
) -> None:
    workspace = client.get("/api/workspace").json()
    search = client.get(
        "/api/resources/search",
        params={"q": "workbench", "module": "software", "limit": 1},
    ).json()
    description = client.get("/api/resources/describe", params={"iri": WORKBENCH}).json()

    assert workspace["individual_count"] >= 1
    assert search["total"] >= 1
    assert search["items"][0]["iri"] == WORKBENCH
    assert search["items"][0]["modules"] == [f"{BASE}id/module/software"]
    assert description["modules"] == [
        {
            "kind": "iri",
            "value": f"{BASE}id/module/software",
            "compact": "module:software",
            "datatype": None,
            "language": None,
        }
    ]
    assert description["direct_modules"] == []


def test_search_page_exposes_total_and_stable_offsets(client: TestClient) -> None:
    full = client.get("/api/resources/search", params={"q": "ontology", "limit": 100}).json()
    first = client.get(
        "/api/resources/search", params={"q": "ontology", "limit": 1, "offset": 0}
    ).json()
    second = client.get(
        "/api/resources/search", params={"q": "ontology", "limit": 1, "offset": 1}
    ).json()

    assert full["total"] > 1
    assert first["total"] == second["total"] == full["total"]
    assert first["items"] + second["items"] == full["items"][:2]
    assert first["has_next"] is True


def test_describe_supports_resource_used_only_as_a_predicate(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    predicate = "https://external.example/vocabulary/predicate-only"
    source = settings.knowledge_root / "data/sources/predicate_only.trig"
    source.write_text(
        f"""@prefix prov: <http://www.w3.org/ns/prov#> .
<{BASE}graph/source/predicate-only> {{
  <{BASE}id/predicate-only/subject> <{predicate}> "value" .
}}
<{BASE}graph/metadata/predicate-only> {{
  <{BASE}graph/source/predicate-only> prov:wasDerivedFrom
    <https://external.example/source/predicate-only> .
}}
""",
        encoding="utf-8",
    )
    local_app = create_app(
        settings,
        revision_provider=lambda: RepositoryRevision("proposal", "a" * 40, True),
    )

    with TestClient(local_app) as local:
        search = local.get("/api/resources/search", params={"q": predicate})
        description = local.get("/api/resources/describe", params={"iri": predicate})

    assert search.status_code == 200
    assert search.json()["items"][0]["iri"] == predicate
    assert description.status_code == 200
    payload = description.json()
    assert payload["incoming"] == payload["outgoing"] == []
    assert len(payload["predicate_uses"]) == 1
    assert payload["usage"] == {
        "incoming_references": 0,
        "outgoing_statements": 0,
        "predicate_uses": 1,
    }
    assert payload["provenance"][0]["subject"]["value"] == (f"{BASE}graph/source/predicate-only")
    assert payload["git_history"] == []


def test_describe_returns_real_git_history_or_empty_for_unversioned_term(
    tmp_path: Path,
) -> None:
    settings = _copy_settings(tmp_path)
    subprocess.run(("git", "init", "--quiet"), cwd=tmp_path, check=True)
    subprocess.run(("git", "config", "user.name", "API History Author"), cwd=tmp_path, check=True)
    subprocess.run(
        ("git", "config", "user.email", "api-history@example.test"),
        cwd=tmp_path,
        check=True,
    )
    relative = "knowledge/ontology/software/terms/Application.ttl"
    subprocess.run(("git", "add", relative), cwd=tmp_path, check=True)
    commit_env = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-08-11T09:10:11-03:00",
        "GIT_COMMITTER_DATE": "2026-08-11T09:10:11-03:00",
    }
    subprocess.run(
        ("git", "commit", "--quiet", "-m", "Version application term"),
        cwd=tmp_path,
        check=True,
        env=commit_env,
    )
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    local_app = create_app(settings)

    with TestClient(local_app) as local:
        versioned = local.get("/api/resources/describe", params={"iri": APPLICATION})
        unversioned = local.get("/api/resources/describe", params={"iri": SUPPORTS})

    assert versioned.status_code == unversioned.status_code == 200
    assert versioned.json()["git_history"] == [
        {
            "commit": revision,
            "author": "API History Author",
            "date": "2026-08-11T09:10:11-03:00",
            "subject": "Version application term",
            "path": relative,
        }
    ]
    assert unversioned.json()["git_history"] == []


def test_graph_endpoints_apply_limits_and_filters(client: TestClient) -> None:
    neighborhood = client.get(
        "/api/graph/neighborhood",
        params={"center": APPLICATION, "max_nodes": 2, "max_edges": 1},
    )
    filtered = client.get(
        "/api/graph/neighborhood",
        params={"center": APPLICATION, "predicate": SUPPORTS, "max_nodes": 20},
    )
    stats = client.get("/api/graph/stats")

    assert neighborhood.status_code == filtered.status_code == stats.status_code == 200
    assert len(neighborhood.json()["nodes"]) <= 2
    assert len(neighborhood.json()["edges"]) <= 1
    assert neighborhood.json()["truncated"] is True
    assert all(
        1 <= edge["priority"] <= 7 and edge["relationship_kind"]
        for edge in neighborhood.json()["edges"]
    )
    assert all(edge["predicate"]["value"] == SUPPORTS for edge in filtered.json()["edges"])
    assert stats.json()["quads"] == 497
    assert_error(
        client.get(
            "/api/graph/neighborhood",
            params={"center": APPLICATION, "max_nodes": 501},
        ),
        422,
        "request.invalid",
    )


def test_graph_contract_exposes_core_classification_for_canonical_resources(
    client: TestClient,
) -> None:
    module = client.get(
        "/api/graph/neighborhood",
        params={"center": f"{BASE}id/module/software", "depth": 0},
    )
    individual = client.get(
        "/api/graph/neighborhood",
        params={"center": f"{BASE}id/software/application/workbench", "depth": 0},
    )

    assert module.status_code == individual.status_code == 200
    assert module.json()["center"]["category"] == "module"
    assert module.json()["center"]["module"] == "software"
    assert module.json()["nodes"][0]["category"] == "module"
    assert individual.json()["center"]["category"] == "individual"
    assert individual.json()["center"]["module"] == "software"
    assert individual.json()["nodes"][0]["category"] == "individual"


def test_validation_impact_and_initial_import_diff_contract(client: TestClient) -> None:
    validation = client.post("/api/validation/run")
    latest = client.get("/api/validation/latest")
    impact = client.get("/api/impact", params={"iri": SUPPORTS})

    assert validation.status_code == latest.status_code == impact.status_code == 200
    assert validation.json() == latest.json()
    assert validation.json()["conforms"] is True
    assert impact.json()["predicate_uses"]
    diff = client.get("/api/diff")
    assert diff.status_code == 200
    assert len(diff.json()["added_quads"]) == 497
    assert diff.json()["removed_quads"] == []
    diff_responses = client.get("/openapi.json").json()["paths"]["/api/diff"]["get"]["responses"]
    assert diff_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SemanticDiffModel"
    }


def test_sparql_is_read_only_bounded_and_reports_errors(client: TestClient) -> None:
    valid = client.post(
        "/api/sparql/query",
        json={
            "query": "SELECT ?s WHERE { ?s ?p ?o } ORDER BY ?s",
            "max_results": 1,
            "timeout_seconds": 2,
        },
    )
    update = client.post(
        "/api/sparql/query",
        json={"query": f"DELETE WHERE {{ <{APPLICATION}> ?p ?o }}"},
    )
    service = client.post(
        "/api/sparql/query",
        json={"query": "SELECT * WHERE { SERVICE <https://example.net/sparql> { ?s ?p ?o } }"},
    )

    assert valid.status_code == 200
    assert len(valid.json()["rows"]) == 1
    assert valid.json()["truncated"] is True
    assert_error(update, 422, "sparql.syntax")
    assert_error(service, 422, "sparql.service")


def test_competency_question_results_use_closed_statuses(client: TestClient) -> None:
    questions = client.get("/api/competency_questions")
    results = client.post("/api/competency_questions/run", json={})

    assert questions.status_code == results.status_code == 200
    assert questions.json()["total"] == len(results.json()) == 4
    first = client.get("/api/competency_questions", params={"limit": 1, "offset": 0}).json()
    second = client.get("/api/competency_questions", params={"limit": 1, "offset": 1}).json()
    assert first["total"] == second["total"] == 4
    assert first["items"][0] != second["items"][0]
    assert {result["status"] for result in results.json()} == {
        "failed",
        "not_executable",
        "passed",
    }
    assert_error(
        client.post("/api/competency_questions/run", json={"iri": f"{BASE}id/question/missing"}),
        404,
        "competency.not_found",
    )


def test_agent_context_rules_and_canonical_skill_status(client: TestClient) -> None:
    context = client.post(
        "/api/agent/context",
        json={
            "task": "analizar Application",
            "terms": [APPLICATION],
            "modules": ["software"],
            "max_terms": 3,
            "depth": 1,
            "max_bytes": 65536,
        },
    )
    rules = client.get("/api/agent/rules")
    skills = client.get("/api/agent/skills")
    status = client.get("/api/agent/status")

    assert {context.status_code, rules.status_code, skills.status_code, status.status_code} == {200}
    assert context.json()["payload"]["retrieval"] == "structured_rdf"
    assert context.json()["json"]
    assert context.json()["markdown"]
    assert {rule["id"] for rule in rules.json()} == {
        "principles",
        "modeling_decision_tree",
        "change_protocol",
        "prohibited_patterns",
    }
    assert all(rule["content"] for rule in rules.json())
    assert skills.json() == {
        "available": ["ontology_discover", "ontology_author", "ontology_review"],
        "status": "synchronized",
        "version": "1.0.0",
    }
    assert status.json()["canonical_contract_available"] is True
    assert status.json()["synchronized"] is True
    assert status.json()["mcp_status"] == "available_stdio"


def test_all_framework_errors_follow_the_public_contract(client: TestClient) -> None:
    assert_error(client.get("/route-that-does-not-exist"), 404, "request.not_found")
    assert_error(client.get("/api/resources/search"), 422, "request.invalid")
    openapi = client.get("/openapi.json").json()
    for path, path_item in openapi["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            validation = operation["responses"].get("422")
            if validation is None:
                continue
            schema = validation["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ApiError"}, (path, method)


def _copy_settings(tmp_path: Path) -> ApiSettings:
    shutil.copytree(ROOT / "knowledge", tmp_path / "knowledge")
    (tmp_path / "config").mkdir()
    shutil.copy2(ROOT / "config" / "namespace.yaml", tmp_path / "config" / "namespace.yaml")
    return ApiSettings(
        repository_root=tmp_path,
        knowledge_root=tmp_path / "knowledge",
        namespace_config=tmp_path / "config" / "namespace.yaml",
    )


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_p07_proposal_authoring_review_and_structured_commit(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    settings = ApiSettings(
        settings.repository_root,
        settings.knowledge_root,
        settings.namespace_config,
        write_enabled=True,
    )
    _git(tmp_path, "init", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "API Author")
    _git(tmp_path, "config", "user.email", "api@example.test")
    _git(tmp_path, "add", "knowledge", "config")
    _git(tmp_path, "commit", "-m", "chore: seed API fixture")
    local_app = create_app(settings)
    payload = {
        "iri": f"{BASE}ontology/software#BusinessCapability",
        "module_id": "software",
        "kind": "class",
        "preferred_label_es": "Capacidad empresarial",
        "alternative_labels_es": ["Capacidad de negocio"],
        "definition_es": "Capacidad mínima propuesta mediante el contrato HTTP controlado.",
        "evidence": "Catálogo de capacidades aprobado para el fixture",
        "author": "API Author",
        "search": {
            "query": "capacidad empresarial",
            "confirmed": True,
            "search_id": "eow-search-v2:invalid." + "0" * 64,
        },
        "status": "proposed",
    }
    with TestClient(local_app) as local:
        main_receipt = search_receipt(local, "capacidad empresarial")
        payload["search"]["search_id"] = main_receipt
        protected = local.post("/api/resources", json=payload)
        branch = local.post(
            "/api/git/branch",
            json={"branch": "proposal/api-authoring", "create": True},
        )
        stale_receipt = local.post("/api/resources", json=payload)
        missing_receipt = local.post(
            "/api/resources",
            json={
                **payload,
                "search": {"query": "capacidad empresarial", "confirmed": True},
            },
        )
        payload["search"]["search_id"] = search_receipt(local, "capacidad empresarial")
        valid_receipt = payload["search"]["search_id"]
        assert isinstance(valid_receipt, str)
        forged_receipt = valid_receipt[:-1] + ("0" if valid_receipt[-1] != "0" else "1")
        forged = local.post(
            "/api/resources",
            json={
                **payload,
                "search": {
                    "query": "capacidad empresarial",
                    "confirmed": True,
                    "search_id": forged_receipt,
                },
            },
        )
        other_receipt = search_receipt(local, "consulta diferente")
        mismatched_receipt = local.post(
            "/api/resources",
            json={
                **payload,
                "search": {
                    "query": "capacidad empresarial",
                    "confirmed": True,
                    "search_id": other_receipt,
                },
            },
        )
        filtered_search_id = local.get(
            "/api/resources/search",
            params={
                "q": "capacidad empresarial",
                "module": "missing-module",
                "limit": 20,
            },
        ).json()["search_id"]
        filtered_receipt = local.post(
            "/api/resources",
            json={
                **payload,
                "search": {
                    "query": "capacidad empresarial",
                    "confirmed": True,
                    "search_id": filtered_search_id,
                },
            },
        )
        displaced_search_id = local.get(
            "/api/resources/search",
            params={"q": "capacidad empresarial", "offset": 999, "limit": 20},
        ).json()["search_id"]
        displaced_receipt = local.post(
            "/api/resources",
            json={
                **payload,
                "search": {
                    "query": "capacidad empresarial",
                    "confirmed": True,
                    "search_id": displaced_search_id,
                },
            },
        )
        created = local.post("/api/resources", json=payload)
        review = local.get("/api/review")
        diff = local.get("/api/diff")
        committed = local.post(
            "/api/git/commit",
            json={"module": "software", "summary": "add business capability"},
        )
        status = local.get("/api/git/status")
        pull_request = local.post(
            "/api/git/pull_request",
            json={"title": "Add business capability", "body": "Evidence and validation"},
        )

    assert_error(protected, 409, "git.protected_branch")
    assert_error(stale_receipt, 422, "authoring.invalid_search_id")
    assert_error(missing_receipt, 422, "request.invalid")
    assert_error(forged, 422, "authoring.invalid_search_id")
    assert_error(mismatched_receipt, 422, "authoring.invalid_search_id")
    assert_error(filtered_receipt, 422, "authoring.invalid_search_id")
    assert_error(displaced_receipt, 422, "authoring.invalid_search_id")
    assert branch.status_code == created.status_code == review.status_code == 200
    assert branch.json()["editable"] is True
    assert created.json()["path"].endswith("BusinessCapability.ttl")
    assert review.json()["ready_to_commit"] is True
    assert review.json()["evidence"]
    assert diff.json() == review.json()["diff"]
    assert committed.status_code == 200
    assert committed.json()["subject"] == "ontology(software): add business capability"
    assert status.json()["dirty"] is False
    assert pull_request.json()["status"] == "not_configured"


def test_p07_models_require_search_and_reject_writes_when_disabled(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    _git(tmp_path, "init", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "Read Only API")
    _git(tmp_path, "config", "user.email", "readonly@example.test")
    _git(tmp_path, "add", "knowledge", "config")
    _git(tmp_path, "commit", "-m", "chore: seed read-only fixture")
    local_app = create_app(
        settings,
        revision_provider=lambda: RepositoryRevision("main", "a" * 40, False),
    )
    with TestClient(local_app) as local:
        disabled = local.get("/api/git/status")
        invalid = local.post(
            "/api/resources",
            json={
                "iri": f"{BASE}ontology/software#Incomplete",
                "module_id": "software",
                "kind": "class",
            },
        )
    assert disabled.status_code == 200
    assert disabled.json()["editable"] is False
    assert_error(invalid, 422, "request.invalid")


def test_api_writes_proposed_relation_from_published_subject_to_proposal_graph(
    tmp_path: Path,
) -> None:
    settings = _copy_settings(tmp_path)
    settings = ApiSettings(
        settings.repository_root,
        settings.knowledge_root,
        settings.namespace_config,
        write_enabled=True,
    )
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "API Graph Test")
    _git(tmp_path, "config", "user.email", "api-graph@example.test")
    _git(tmp_path, "add", "knowledge", "config")
    _git(tmp_path, "commit", "--quiet", "-m", "chore: seed graph fixture")
    _git(tmp_path, "switch", "--quiet", "--create", "proposal/api-graph")
    component = f"{BASE}id/software/component/api_graph_fixture"

    with TestClient(create_app(settings)) as local:
        created = local.post(
            "/api/resources/individual",
            json={
                "iri": component,
                "class_iri": f"{BASE}ontology/software#SoftwareComponent",
                "source_id": "api_graph_fixture",
                "preferred_label_es": "Componente API para graph de propuesta",
                "evidence": "Fixture adversarial API de separación de estados",
                "author": "API Graph Test",
                "search": {
                    "query": "componente api para graph de propuesta",
                    "confirmed": True,
                    "search_id": search_receipt(local, "componente api para graph de propuesta"),
                },
            },
        )
        relation = local.post(
            "/api/relations",
            json={
                "subject": WORKBENCH,
                "predicate": f"{BASE}ontology/software#isComposedOf",
                "object_iri": component,
                "evidence": "Fixture adversarial API de named graph propuesto",
            },
        )

    assert created.status_code == relation.status_code == 200
    document = Dataset().parse(
        tmp_path / relation.json()["path"],
        format="trig",
    )
    triple = (
        URIRef(WORKBENCH),
        URIRef(f"{BASE}ontology/software#isComposedOf"),
        URIRef(component),
    )
    published = URIRef(f"{BASE}graph/source/fixture_inventory")
    proposal = URIRef(f"{BASE}graph/proposal/api-graph/fixture_inventory")
    metadata = URIRef(f"{BASE}graph/metadata/proposal/api-graph/fixture_inventory")
    assert triple not in document.graph(published)
    assert triple in document.graph(proposal)
    assert (
        proposal,
        URIRef(f"{BASE}ontology/core#status"),
        Literal("proposed"),
    ) in document.graph(metadata)
    assert any(document.graph(proposal).triples((None, RDF.subject, URIRef(WORKBENCH))))


def test_p07_form_catalog_and_editable_state_preserve_property_contract(
    client: TestClient,
) -> None:
    forms = client.get("/api/authoring/forms")
    state = client.get("/api/authoring/state", params={"iri": SUPPORTS})

    assert forms.status_code == state.status_code == 200
    assert [item["kind"] for item in forms.json()] == [
        "ontology",
        "class",
        "object_property",
        "datatype_property",
        "annotation_property",
        "individual",
        "concept",
        "node_shape",
        "competency_question",
    ]
    property_schema = next(item for item in forms.json() if item["kind"] == "object_property")
    fields = {field["key"]: field for field in property_schema["fields"]}
    assert fields["direction"]["required"] is True
    assert fields["status"]["allowed_values"] == ["proposed", "active", "deprecated"]
    assert state.json() == {
        **state.json(),
        "kind": "object_property",
        "module_id": "software",
        "status": "active",
        "domain": APPLICATION,
        "range": f"{BASE}ontology/organization#OrganizationUnit",
    }
    assert state.json()["reading_direction_es"]
    assert state.json()["valid_example"]


def test_api_round_trips_multiple_shacl_form_values(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    settings = ApiSettings(
        settings.repository_root,
        settings.knowledge_root,
        settings.namespace_config,
        write_enabled=True,
    )
    shape = settings.knowledge_root / "shapes/modules/reviewer_fixture.ttl"
    shape.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        f"@prefix ex: <{BASE}ontology/software#> .\n"
        "@prefix fixture: <https://fixtures.example/reviewer#> .\n"
        f"<{BASE}shape/software/ReviewerFixtureShape> a sh:NodeShape ;\n"
        "  sh:targetClass owl:Class ; sh:property [\n"
        '    sh:path fixture:reviewer ; sh:minCount 2 ; sh:maxCount 3 ; sh:name "Revisores"@es\n'
        "  ] .\n"
        f"<{BASE}shape/software/IndividualReviewerFixtureShape> a sh:NodeShape ;\n"
        "  sh:targetClass owl:NamedIndividual ; sh:property [\n"
        "    sh:path fixture:reviewer ; sh:maxCount 3 ; sh:datatype xsd:string ;\n"
        '    sh:name "Revisores"@es\n'
        "  ] .\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "Multiple API Test")
    _git(tmp_path, "config", "user.email", "multiple@example.test")
    _git(tmp_path, "add", "knowledge", "config")
    _git(tmp_path, "commit", "--quiet", "-m", "chore: seed multiple fixture")
    _git(tmp_path, "switch", "--quiet", "--create", "proposal/multiple-values")
    iri = f"{BASE}ontology/software#ReviewedCapability"
    local_app = create_app(settings)

    with TestClient(local_app) as local:
        forms = local.get("/api/authoring/forms")
        class_schema = next(item for item in forms.json() if item["kind"] == "class")
        reviewer = next(item for item in class_schema["fields"] if item["key"] == "reviewer")
        assert reviewer["min_count"] == 2
        assert reviewer["max_count"] == 3
        base_payload = {
            "iri": iri,
            "module_id": "software",
            "kind": "class",
            "preferred_label_es": "Capacidad revisada",
            "definition_es": "Capacidad con revisores múltiples preservados.",
            "evidence": "Fixture API multivaluado",
            "author": "Multiple API Test",
            "search": {
                "query": "capacidad revisada",
                "confirmed": True,
                "search_id": search_receipt(local, "capacidad revisada"),
            },
        }
        too_few = local.post(
            "/api/resources",
            json={**base_payload, "form_values": {"reviewer": ["Ada"]}},
        )
        too_many = local.post(
            "/api/resources",
            json={
                **base_payload,
                "form_values": {"reviewer": ["Ada", "Grace", "Linus", "Margaret"]},
            },
        )
        created = local.post(
            "/api/resources",
            json={
                **base_payload,
                "form_values": {"reviewer": ["Ada", "Grace"]},
            },
        )
        state = local.get("/api/authoring/state", params={"iri": iri})
        individual_receipt = search_receipt(local, "aplicación revisada")
        individual_iri = f"{BASE}id/software/application/api_reviewed"
        individual_created = local.post(
            "/api/resources/individual",
            json={
                "iri": individual_iri,
                "class_iri": APPLICATION,
                "source_id": "api_reviewed",
                "preferred_label_es": "Aplicación revisada",
                "alternative_labels_es": ["Aplicación inspeccionada"],
                "evidence": "Fixture API individual multivaluado",
                "author": "Multiple API Test",
                "search": {
                    "query": "aplicación revisada",
                    "confirmed": True,
                    "search_id": individual_receipt,
                },
                "form_values": {"reviewer": ["Ada", "Grace"]},
            },
        )
        individual_state = local.get("/api/authoring/state", params={"iri": individual_iri})

    assert too_few.status_code == 422
    assert too_few.json()["code"] == "authoring.required_form_field"
    assert too_many.status_code == 422
    assert too_many.json()["code"] == "authoring.form_field_cardinality"
    assert created.status_code == state.status_code == 200
    assert state.json()["form_values"]["reviewer"] == ["Ada", "Grace"]
    assert individual_created.status_code == individual_state.status_code == 200
    assert individual_state.json()["alternative_labels_es"] == ["Aplicación inspeccionada"]
    assert individual_state.json()["form_values"]["reviewer"] == ["Ada", "Grace"]


def test_editable_state_is_available_from_rdf_without_a_git_checkout(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    local_app = create_app(
        settings,
        revision_provider=lambda: RepositoryRevision(None, None, False),
    )

    with TestClient(local_app) as local:
        state = local.get("/api/authoring/state", params={"iri": SUPPORTS})

    assert state.status_code == 200
    assert state.json()["kind"] == "object_property"
    assert state.json()["domain"] == APPLICATION


def test_feature_branch_rejects_every_authoring_and_publication_entrypoint(
    tmp_path: Path,
) -> None:
    settings = _copy_settings(tmp_path)
    settings = ApiSettings(
        settings.repository_root,
        settings.knowledge_root,
        settings.namespace_config,
        write_enabled=True,
    )
    _git(tmp_path, "init", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "Unsafe Branch Test")
    _git(tmp_path, "config", "user.email", "unsafe@example.test")
    _git(tmp_path, "add", "knowledge", "config")
    _git(tmp_path, "commit", "-m", "chore: seed unsafe branch fixture")
    _git(tmp_path, "switch", "--create", "feature/unsafe")
    local_app = create_app(settings)
    payload = {
        "iri": f"{BASE}ontology/software#UnsafeFeatureClass",
        "module_id": "software",
        "kind": "class",
        "preferred_label_es": "Clase insegura",
        "definition_es": "No debe poder escribirse fuera de proposal slash.",
        "evidence": "Fixture adversarial",
        "author": "Unsafe Branch Test",
        "search": {
            "query": "clase insegura",
            "confirmed": True,
            "search_id": "eow-search-v2:invalid." + "0" * 64,
        },
        "status": "proposed",
    }

    with TestClient(local_app) as local:
        payload["search"]["search_id"] = search_receipt(local, "clase insegura")
        status = local.get("/api/git/status")
        responses = [
            local.post("/api/resources", json=payload),
            local.get("/api/review"),
            local.post(
                "/api/git/commit",
                json={"module": "software", "summary": "unsafe feature change"},
            ),
            local.post(
                "/api/git/pull_request",
                json={"title": "Unsafe", "body": "Must not publish"},
            ),
        ]

    assert status.status_code == 200
    assert status.json()["editable"] is False
    for response in responses:
        assert_error(response, 409, "git.invalid_proposal_branch")
    assert not (tmp_path / "knowledge/ontology/software/terms/UnsafeFeatureClass.ttl").exists()


def test_runtime_reloads_on_commit_change_and_explicit_command(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    revision = [RepositoryRevision("proposal", "a" * 40, False)]
    local_app = create_app(settings, revision_provider=lambda: revision[0])
    with TestClient(local_app) as local:
        initial = local.get("/api/workspace/status").json()
        repeated = local.get("/api/workspace/status").json()
        revision[0] = RepositoryRevision("proposal", "b" * 40, True)
        commit_reload = local.get("/api/workspace/status").json()
        explicit_reload = local.post("/api/workspace/reload").json()

    assert initial["generation"] == repeated["generation"] == 1
    assert commit_reload["generation"] == 2
    assert commit_reload["revision"]["commit"] == "b" * 40
    assert explicit_reload["generation"] == 3


def test_revision_provider_reads_real_git_branch_commit_and_dirty_state(
    tmp_path: Path,
) -> None:
    settings = _copy_settings(tmp_path)
    subprocess.run(
        ("git", "init", "--quiet", "--initial-branch=proposal/test"), cwd=tmp_path, check=True
    )
    subprocess.run(("git", "config", "user.name", "Runtime Test"), cwd=tmp_path, check=True)
    subprocess.run(
        ("git", "config", "user.email", "runtime@example.test"),
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(("git", "add", "knowledge", "config"), cwd=tmp_path, check=True)
    subprocess.run(("git", "commit", "--quiet", "-m", "Seed runtime"), cwd=tmp_path, check=True)

    clean = read_repository_revision(settings)
    (settings.knowledge_root / "manifest.ttl").write_text(
        (settings.knowledge_root / "manifest.ttl").read_text() + "\n",
        encoding="utf-8",
    )
    dirty = read_repository_revision(settings)

    assert clean.branch == dirty.branch == "proposal/test"
    assert clean.commit == dirty.commit
    assert clean.commit is not None and len(clean.commit) == 40
    assert clean.dirty is False
    assert dirty.dirty is True


def test_runtime_reloads_branch_and_dirty_state_with_stable_head(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    revision = [RepositoryRevision("main", "a" * 40, False)]
    local_app = create_app(settings, revision_provider=lambda: revision[0])

    with TestClient(local_app) as local:
        initial = local.get("/api/workspace").json()
        revision[0] = RepositoryRevision("proposal/review", "a" * 40, True)
        changed = local.get("/api/workspace").json()
        repeated = local.get("/api/workspace").json()

    assert initial["branch"] == "main"
    assert initial["pending_changes"] is False
    assert changed["branch"] == "proposal/review"
    assert changed["pending_changes"] is True
    assert changed["runtime"]["generation"] == initial["runtime"]["generation"] + 1
    assert repeated["runtime"]["generation"] == changed["runtime"]["generation"]


def test_runtime_reloads_when_dirty_content_changes_without_status_transition(
    tmp_path: Path,
) -> None:
    settings = _copy_settings(tmp_path)
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "Fingerprint Test")
    _git(tmp_path, "config", "user.email", "fingerprint@example.test")
    _git(tmp_path, "add", "knowledge", "config")
    _git(tmp_path, "commit", "--quiet", "-m", "chore: seed fingerprint fixture")
    target = settings.knowledge_root / "ontology/software/terms/Application.ttl"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    manager = RuntimeManager(settings)
    first = manager.snapshot()

    target.write_text(target.read_text(encoding="utf-8") + "# second edit\n", encoding="utf-8")
    second = manager.snapshot()

    assert first.revision.dirty is second.revision.dirty is True
    assert first.revision.commit == second.revision.commit
    assert first.revision.fingerprint != second.revision.fingerprint
    assert second.generation == first.generation + 1


def test_commit_reloads_and_rejects_a_second_nonconforming_dirty_edit(
    tmp_path: Path,
) -> None:
    settings = _copy_settings(tmp_path)
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "Commit Fingerprint Test")
    _git(tmp_path, "config", "user.email", "commit-fingerprint@example.test")
    _git(tmp_path, "add", "knowledge", "config")
    _git(tmp_path, "commit", "--quiet", "-m", "chore: seed commit fixture")
    _git(tmp_path, "switch", "--quiet", "--create", "proposal/stale-validation")
    target = settings.knowledge_root / "ontology/software/terms/Application.ttl"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    manager = RuntimeManager(settings)
    assert manager.current().validation_report.conforms is True
    original_head = _git(tmp_path, "rev-parse", "HEAD")

    target.write_text(
        f"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<{APPLICATION}> a owl:Class .\n",
        encoding="utf-8",
    )
    workspace = GitWorkspaceService(tmp_path, settings.knowledge_root)
    with pytest.raises(GitWorkspaceError) as blocked:
        manager.commit_proposal(
            workspace,
            module="software",
            summary="publish stale invalid metadata",
            exception_reason=None,
        )

    assert blocked.value.code == "git.validation_failed"
    assert _git(tmp_path, "rev-parse", "HEAD") == original_head


def test_failed_reload_keeps_the_previous_snapshot(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    local_app = create_app(
        settings,
        revision_provider=lambda: RepositoryRevision("proposal", "a" * 40, True),
    )
    with TestClient(local_app, raise_server_exceptions=False) as local:
        initial = local.get("/api/workspace/status").json()
        (settings.knowledge_root / "manifest.ttl").write_text("not turtle [", encoding="utf-8")
        failure = local.post("/api/workspace/reload")
        after = local.get("/api/workspace/status").json()

    assert_error(failure, 422, "parser.syntax")
    assert after == initial


def test_module_endpoint_reports_import_cycles_from_the_core(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    core_module = settings.knowledge_root / "ontology/core/module.ttl"
    with core_module.open("a", encoding="utf-8") as stream:
        stream.write(
            "\n<https://knowledge.example.com/ontology/core> "
            "owl:imports <https://knowledge.example.com/ontology/software> .\n"
        )
    local_app = create_app(
        settings,
        revision_provider=lambda: RepositoryRevision("proposal", "a" * 40, True),
    )

    with TestClient(local_app) as local:
        core = local.get("/api/modules/core").json()
        software = local.get("/api/modules/software").json()

    assert core["import_cycles"]
    assert software["import_cycles"] == core["import_cycles"]


def test_commit_probes_and_publication_are_serialized(tmp_path: Path) -> None:
    settings = _copy_settings(tmp_path)
    old_probe_entered = threading.Event()
    release_old_probe = threading.Event()
    new_probe_entered = threading.Event()

    def revision_provider() -> RepositoryRevision:
        name = threading.current_thread().name
        if name == "old-request":
            old_probe_entered.set()
            assert release_old_probe.wait(timeout=5)
            return RepositoryRevision("proposal", "b" * 40, False)
        if name == "new-request":
            new_probe_entered.set()
            return RepositoryRevision("proposal", "c" * 40, False)
        return RepositoryRevision("proposal", "a" * 40, False)

    manager = RuntimeManager(settings, revision_provider=revision_provider)
    results: dict[str, str | None] = {}

    def read_snapshot(key: str) -> None:
        results[key] = manager.snapshot().revision.commit

    old_request = threading.Thread(target=read_snapshot, args=("old",), name="old-request")
    new_request = threading.Thread(target=read_snapshot, args=("new",), name="new-request")
    old_request.start()
    assert old_probe_entered.wait(timeout=5)
    new_request.start()
    time.sleep(0.05)
    assert not new_probe_entered.is_set()
    release_old_probe.set()
    old_request.join(timeout=15)
    new_request.join(timeout=15)

    assert not old_request.is_alive() and not new_request.is_alive()
    assert results == {"old": "b" * 40, "new": "c" * 40}
    assert manager.current().revision.commit == "c" * 40


def test_validation_and_reload_cannot_mix_generations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _copy_settings(tmp_path)
    revision = [RepositoryRevision("proposal", "a" * 40, False)]
    manager = RuntimeManager(settings, revision_provider=lambda: revision[0])
    source = manager.current()
    validation_entered = threading.Event()
    release_validation = threading.Event()
    reload_finished = threading.Event()
    original_validate = source.validation.validate_dataset

    def delayed_validation(*args: object, **kwargs: object) -> object:
        validation_entered.set()
        assert release_validation.wait(timeout=5)
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(source.validation, "validate_dataset", delayed_validation)
    validation_thread = threading.Thread(target=manager.validate_current)
    validation_thread.start()
    assert validation_entered.wait(timeout=5)
    revision[0] = RepositoryRevision("proposal", "b" * 40, False)

    def reload() -> None:
        manager.reload()
        reload_finished.set()

    reload_thread = threading.Thread(target=reload)
    reload_thread.start()
    time.sleep(0.05)
    assert not reload_finished.is_set()
    release_validation.set()
    validation_thread.join(timeout=15)
    reload_thread.join(timeout=15)

    assert not validation_thread.is_alive() and not reload_thread.is_alive()
    current = manager.current()
    assert current.generation == 2
    assert current.revision.commit == "b" * 40
    assert current.validation_report.conforms
    assert manager.update_validation(source, source.validation_report) is False
    assert manager.current() is current


def test_openapi_drives_the_only_frontend_dto_contract() -> None:
    schema = (ROOT / "apps/web/src/lib/api/schema.d.ts").read_text()
    client = (ROOT / "apps/web/src/lib/api/client.ts").read_text()
    openapi = (ROOT / "apps/web/openapi.json").read_text()

    assert "This file was auto-generated by openapi-typescript" in schema
    assert "'/api/workspace'" in schema
    assert "createClient<paths>" in client
    assert "from './schema'" in client
    assert '"ApiError"' in openapi

from __future__ import annotations

import base64
import hashlib
import json
import unicodedata
import zipfile
from pathlib import Path

from ontology_core import (
    CompetencyQuestionRepository,
    CompetencyQuestionService,
    FilesystemRdfStore,
    GitWorkspaceService,
    ProposalReviewService,
    ReadOnlySparqlService,
    content_fingerprint,
)
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, RDF, SKOS

ROOT = Path(__file__).parents[1]
BASE = "https://knowledge.example.com/"
EOW_STATUS = URIRef(f"{BASE}ontology/core#status")
P12_PROPOSAL_GRAPH = URIRef(f"{BASE}graph/proposal/p12-governed-knowledge-pilot/fixture_inventory")
P12_PROPOSAL_METADATA_GRAPH = URIRef(
    f"{BASE}graph/metadata/proposal/p12-governed-knowledge-pilot/fixture_inventory"
)

P12_SEARCH_QUERIES = {
    f"{BASE}ontology/knowledge_governance": "gobernanza del conocimiento",
    f"{BASE}ontology/knowledge_governance#EnterpriseKnowledgeGovernance": (
        "gobernanza del conocimiento empresarial"
    ),
    f"{BASE}ontology/knowledge_governance#KnowledgePublicationProcess": (
        "proceso de publicación de conocimiento"
    ),
    f"{BASE}ontology/software#SoftwareComponent": "componente de software",
    f"{BASE}ontology/software#SourceCodeRepository": "repositorio de código fuente",
    f"{BASE}ontology/knowledge_governance#governedThrough": "se gobierna mediante",
    f"{BASE}ontology/knowledge_governance#supportedByApplication": ("es soportado por aplicación"),
    f"{BASE}ontology/software#isComposedOf": "se compone de",
    f"{BASE}ontology/software#implementedByRepository": ("es implementado por repositorio"),
    f"{BASE}id/knowledge_governance/process/ontology_change_publication": (
        "publicación de cambios ontológicos"
    ),
    f"{BASE}id/software/component/ontology_core": "ontology core",
    f"{BASE}id/software/repository/enterprise_ontology_workbench_mvp": (
        "enterprise ontology workbench mvp"
    ),
    f"{BASE}id/competency-question/governed_knowledge_traceability": (
        "trazabilidad del conocimiento gobernado"
    ),
}


def _store() -> FilesystemRdfStore:
    return FilesystemRdfStore(
        ROOT / "knowledge",
        ROOT / "config" / "namespace.yaml",
    )


def test_p12_pilot_keeps_the_transversal_traversal_in_named_graphs() -> None:
    store = _store()
    dataset = store.load()
    concept = URIRef(f"{BASE}ontology/knowledge_governance#EnterpriseKnowledgeGovernance")
    process = URIRef(f"{BASE}id/knowledge_governance/process/ontology_change_publication")
    application = URIRef(f"{BASE}id/software/application/workbench")
    component = URIRef(f"{BASE}id/software/component/ontology_core")
    repository = URIRef(f"{BASE}id/software/repository/enterprise_ontology_workbench_mvp")

    triples = (
        (
            concept,
            URIRef(f"{BASE}ontology/knowledge_governance#governedThrough"),
            process,
        ),
        (
            process,
            URIRef(f"{BASE}ontology/knowledge_governance#supportedByApplication"),
            application,
        ),
        (
            application,
            URIRef(f"{BASE}ontology/software#isComposedOf"),
            component,
        ),
        (
            component,
            URIRef(f"{BASE}ontology/software#implementedByRepository"),
            repository,
        ),
    )
    published_graphs = {
        graph_iri
        for graph_iri, _, _, _ in dataset.quads((None, EOW_STATUS, Literal("published"), None))
    }
    for subject, predicate, obj in triples:
        direct = tuple(dataset.quads((subject, predicate, obj, None)))
        assert len(direct) == 1
        graph_iri = direct[0][3]
        assert graph_iri not in published_graphs
        if subject == application:
            assert graph_iri == P12_PROPOSAL_GRAPH
            assert any(dataset.quads((graph_iri, EOW_STATUS, Literal("proposed"), None)))
        assertions = {
            assertion
            for assertion, _, _, assertion_graph in dataset.quads(
                (None, RDF.subject, subject, None)
            )
            if assertion_graph == graph_iri
            and str(assertion).startswith("urn:eow:proposal-statement:")
            and (assertion, RDF.predicate, predicate, graph_iri) in dataset
            and (assertion, RDF.object, obj, graph_iri) in dataset
            and (assertion, EOW_STATUS, Literal("proposed"), graph_iri) in dataset
            and any(dataset.quads((assertion, DCTERMS.source, None, graph_iri)))
        }
        assert len(assertions) == 1

    assert any(
        dataset.quads(
            (
                process,
                RDF.type,
                URIRef(f"{BASE}ontology/knowledge_governance#KnowledgePublicationProcess"),
                None,
            )
        )
    )
    assert any(dataset.quads((component, EOW_STATUS, Literal("proposed"), None)))
    assert any(dataset.quads((repository, EOW_STATUS, Literal("proposed"), None)))
    assert any(
        dataset.quads(
            (
                P12_PROPOSAL_GRAPH,
                URIRef("http://www.w3.org/ns/prov#wasDerivedFrom"),
                URIRef(f"{BASE}graph/source/fixture_inventory"),
                P12_PROPOSAL_METADATA_GRAPH,
            )
        )
    )
    assert all("mcp-stage" not in str(graph_iri) for graph_iri in dataset.graphs())
    assert len(dataset.default_graph) == 0


def test_p12_has_no_proposed_relation_materialized_in_a_published_graph() -> None:
    dataset = _store().load()
    published_graphs = {
        graph_iri
        for graph_iri, _, _, _ in dataset.quads((None, EOW_STATUS, Literal("published"), None))
    }
    for assertion, _, _, _ in dataset.quads((None, RDF.type, RDF.Statement, None)):
        if not any(dataset.quads((assertion, EOW_STATUS, Literal("proposed"), None))):
            continue
        subjects = {obj for _, _, obj, _ in dataset.quads((assertion, RDF.subject, None, None))}
        predicates = {obj for _, _, obj, _ in dataset.quads((assertion, RDF.predicate, None, None))}
        objects = {obj for _, _, obj, _ in dataset.quads((assertion, RDF.object, None, None))}
        assert len(subjects) == len(predicates) == len(objects) == 1
        triple = (next(iter(subjects)), next(iter(predicates)), next(iter(objects)))
        assert all(triple not in dataset.graph(graph_iri) for graph_iri in published_graphs)


def _receipt_payload(token: str) -> dict[str, object]:
    encoded = token.removeprefix("eow-search-v2:").split(".", 1)[0]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


def _normalized_query(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    unaccented = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(unaccented.split())


def test_p12_codex_authoring_evidence_proves_search_before_every_mcp_creation() -> None:
    evidence = json.loads(
        (ROOT / "docs/pilot/p12-authoring-evidence.json").read_text(encoding="utf-8")
    )
    expected = set(P12_SEARCH_QUERIES)
    resources = evidence["resources"]
    assert evidence["artifact_scope"]["status"] == "retained_pre_domain_review_ledger"
    assert evidence["current_snapshot"]["semantic_diff"]["added_quads"] == 497
    assert evidence["current_snapshot"]["knowledge_config_fingerprint"] == content_fingerprint(
        ROOT / "knowledge", ROOT / "config"
    )
    assert {entry["iri"] for entry in resources} == expected
    assert [entry["ordinal"] for entry in resources] == list(range(1, len(expected) + 1))
    prior_snapshot = evidence["initial_snapshot"]
    for entry in resources:
        search = entry["search"]
        receipt = _receipt_payload(search["search_id"])
        assert entry["query"] == P12_SEARCH_QUERIES[entry["iri"]]
        assert entry["tool"] == "ontology_propose_term"
        assert entry["write"]["operation"] == "created"
        assert entry["write"]["snapshot"].startswith("proposal/p12-governed-knowledge-pilot|")
        assert search["offset"] == 0
        assert search["limit"] == 50
        assert receipt["o"] == 0 and receipt["l"] == 50
        assert receipt["m"] == [] and receipt["y"] == []
        assert receipt["q"] == _normalized_query(entry["query"])
        assert receipt["s"] == entry["search_snapshot"] == prior_snapshot
        assert all(item["iri"] != entry["iri"] for item in search["items"])
        assert search["total"] == (11 if entry["query"] == "ontology core" else 0)
        prior_snapshot = entry["write"]["snapshot"]

    final_fingerprint = content_fingerprint(ROOT / "knowledge", ROOT / "config")
    domain_review = json.loads(
        (ROOT / "docs/pilot/p12-domain-review.json").read_text(encoding="utf-8")
    )
    assert prior_snapshot != evidence["relations"][-1]["write"]["snapshot"]
    assert evidence["relations"][-1]["write"]["snapshot"].endswith(
        domain_review["application"]["prior_knowledge_config_fingerprint"]
    )
    assert domain_review["application"]["knowledge_config_fingerprint"] == final_fingerprint

    post_write = evidence["post_write_verification"]
    assert {entry["iri"] for entry in post_write} == expected
    for entry in post_write:
        search = entry["search"]
        assert entry["query"] == P12_SEARCH_QUERIES[entry["iri"]]
        assert entry["target_found"] is True
        assert search["offset"] == 0 and search["limit"] == 50
        assert any(item["iri"] == entry["iri"] for item in search["items"])

    writes = [*resources, *evidence["relations"]]
    assert len(evidence["relations"]) == 10
    assert [entry["tool"] for entry in evidence["audit"]] == [entry["tool"] for entry in writes]
    assert all(
        entry["result"] == "success" and entry["agent"] == evidence["agent"]
        for entry in evidence["audit"]
    )
    assert all(
        entry["write"]["snapshot"].startswith("proposal/p12-governed-knowledge-pilot|")
        for entry in evidence["relations"]
    )
    assert evidence["validation"]["conforms"] is True


def test_p12_initial_import_diff_artifact_covers_every_current_quad() -> None:
    store = _store()
    workspace = GitWorkspaceService(ROOT, ROOT / "knowledge")
    current = ProposalReviewService(store, workspace).review(base_ref="main").to_dict()
    artifact = json.loads((ROOT / "docs/pilot/p12-semantic-diff.json").read_text(encoding="utf-8"))

    assert artifact["diff"] == current["diff"]
    assert artifact["validation"] == current["validation"]
    assert artifact["evidence"] == current["evidence"]
    assert artifact["ready_to_commit"] == current["ready_to_commit"]
    assert current["diff"]["removed_quads"] == []
    assert len(current["diff"]["added_quads"]) == len(store.load())
    assert current["ready_to_commit"] is True


def test_p12_competency_question_is_executable_but_remains_proposed() -> None:
    store = _store()
    dataset = store.load()
    repository = CompetencyQuestionRepository(dataset, BASE)
    service = CompetencyQuestionService(
        repository,
        ReadOnlySparqlService(dataset, store.prefixes),
        ROOT / "knowledge",
    )
    iri = f"{BASE}id/competency-question/governed_knowledge_traceability"
    question = repository.get(iri)

    assert question is not None
    assert question.state == "proposed"
    result = service.execute(question)
    assert result.status == "passed"
    assert result.result is not None
    assert len(result.result.rows) == 1
    assert {
        variable: value.value
        for variable, value in zip(result.result.variables, result.result.rows[0], strict=True)
        if value is not None
    } == {
        "application": f"{BASE}id/software/application/workbench",
        "component": f"{BASE}id/software/component/ontology_core",
        "domainConcept": f"{BASE}ontology/knowledge_governance#EnterpriseKnowledgeGovernance",
        "process": f"{BASE}id/knowledge_governance/process/ontology_change_publication",
        "repository": f"{BASE}id/software/repository/enterprise_ontology_workbench_mvp",
    }


def test_p12_domain_review_is_applied_and_bound_to_the_current_rdf() -> None:
    path = ROOT / "docs/pilot/p12-domain-review.json"
    raw = path.read_text(encoding="utf-8")
    review = json.loads(raw)
    dataset = _store().load()
    module = URIRef(f"{BASE}ontology/knowledge_governance")
    concept = URIRef(f"{BASE}ontology/knowledge_governance#EnterpriseKnowledgeGovernance")
    component = URIRef(f"{BASE}id/software/component/ontology_core")

    assert review["task"] == "P12_T05"
    assert review["status"] == "approved_and_applied"
    assert review["required_application"] == []
    assert review["evidence"]["reviewer_role"] == "human_domain_authority"
    assert review["evidence"]["reviewer_identity"] == "not_disclosed"
    assert review["application"]["knowledge_config_fingerprint"] == content_fingerprint(
        ROOT / "knowledge", ROOT / "config"
    )
    assert review["application"]["semantic_diff"]["added_quads"] == 497
    diff_path = ROOT / review["application"]["semantic_diff"]["path"]
    assert (
        hashlib.sha256(diff_path.read_bytes()).hexdigest()
        == review["application"]["semantic_diff"]["sha256"]
    )
    decisions = {item["id"]: item for item in review["decisions"]}
    assert decisions["module_owner"]["value"] == "Bruno Jaime"
    assert decisions["enterprise_knowledge_governance_type"]["value"] == str(SKOS.Concept)
    assert any(
        dataset.quads((module, DCTERMS.rightsHolder, Literal("Bruno Jaime", lang="es"), None))
    )
    assert not any(
        "pendiente de confirmación" in str(value).casefold()
        for value in dataset.objects(module, DCTERMS.rightsHolder)
    )
    assert any(dataset.quads((concept, RDF.type, SKOS.Concept, None)))
    assert any(
        dataset.quads(
            (
                component,
                RDF.type,
                URIRef(f"{BASE}ontology/software#SoftwareComponent"),
                None,
            )
        )
    )
    assert raw == json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def test_p12_handoff_separates_historical_and_current_codex_reviews() -> None:
    handoff = (ROOT / "docs" / "pilot" / "p12-pilot.md").read_text(encoding="utf-8")

    assert "p12-codex-review-provenance.json" in handoff
    assert "p12-codex-review-ce2cefec.superseded.json" in handoff
    assert "segundo Codex 0.144.5" in handoff
    assert "`gpt-5.6-sol`" in handoff
    assert "`requires_changes`" in handoff
    assert "`superseded`" in handoff
    assert "no está disponible" in handoff
    assert "copia temporal aislada" in handoff
    assert "revisión humana de dominio" in handoff
    assert "contenido permanece `proposed`" in handoff
    assert "p12-codex-review-current.json" in handoff
    assert "p12-codex-review-current-provenance.json" in handoff
    assert "p12-codex-review-resolution-496.superseded.json" in handoff
    assert "Codex CLI 0.114.0" in handoff
    assert "emitió `approve`" in handoff
    assert "P12_T01–P12_T05 están `done`" in handoff
    assert "P12_T06 queda" in handoff
    assert "P12_T07–P12_T11" in handoff
    assert "p12-claude-review-gate.json" in handoff
    assert "no participa en el cierre de P12_T04" in handoff


def test_p12_superseded_codex_review_preserves_bytes_and_declares_provenance() -> None:
    provenance_path = ROOT / "docs" / "pilot" / "p12-codex-review-provenance.json"
    provenance_raw = provenance_path.read_text(encoding="utf-8")
    provenance = json.loads(provenance_raw)
    historical = provenance["historical_review"]
    current = provenance["current_snapshot"]
    path = ROOT / historical["artifact"]["path"]
    raw = path.read_text(encoding="utf-8")
    artifact = json.loads(raw)

    assert not (ROOT / "docs" / "pilot" / "p12-codex-review.json").exists()
    assert historical["status"] == "superseded"
    assert historical["exact_input_available"] is False
    assert historical["reviewed_head"] == "30e85558acfc32ae8487a71a5f0628291e6d5b8f"
    assert historical["reviewed_snapshot_fingerprint"] is None
    assert "must not be reconstructed" in historical["input_availability_note"]
    assert historical["reviewed_semantic_diff"] == {
        "added_quads": 493,
        "change_groups": 60,
        "claimed_digest": "c57af17d9c90145d9450423abf0343d1ffce720f4a793b75f7c521459a5b1f64",
        "digest_scope": (
            "Digest stated by the superseded review output; the exact historical input "
            "is unavailable for independent verification."
        ),
        "removed_quads": 0,
    }
    assert historical["artifact"]["bytes_preserved"] is True
    assert hashlib.sha256(path.read_bytes()).hexdigest() == historical["artifact"]["sha256"]
    assert historical["artifact"]["sha256"] == (
        "ce2cefecfc9255e56118d98b22fdcbb03893621a835802075ffc121b449bc39b"
    )
    assert not (path.parent / "p12-semantic-diff.json").exists()

    assert set(artifact) == {"checks", "findings", "reviewer", "summary", "verdict"}
    assert artifact["reviewer"] == "codex"
    assert artifact["verdict"] == "requires_changes"
    assert len(artifact["checks"]) == 16
    assert {item["status"] for item in artifact["checks"]} <= {
        "passed",
        "failed",
        "not_available",
    }
    checks = {item["id"]: item for item in artifact["checks"]}
    assert checks["required_validation"]["status"] == "passed"
    assert checks["semantic_diff_artifact"]["status"] == "passed"
    assert checks["search_receipts"]["status"] == "passed"
    assert checks["duplicates_and_internal_iris"]["status"] == "passed"
    assert checks["resource_type_review"]["status"] == "failed"
    assert checks["proposal_state_separation"]["status"] == "failed"
    assert [item["severity"] for item in artifact["findings"]] == [
        "high",
        "medium",
        "medium",
    ]
    assert {item["rule_id"] for item in artifact["findings"]} == {
        "enterprise_ontology_workbench_mvp_spec.md#6.5-6.6",
        "agent_contract/rules/modeling_decision_tree.md#5-8",
        "agent_contract/rules/principles.md#4",
    }
    assert raw == json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert "session id" not in raw.casefold()
    assert "session_id" not in raw

    current_diff_path = ROOT / current["semantic_diff"]["path"]
    current_evidence_path = ROOT / current["authoring_evidence"]["path"]
    current_diff = json.loads(current_diff_path.read_text(encoding="utf-8"))["diff"]
    assert (
        hashlib.sha256(current_diff_path.read_bytes()).hexdigest()
        == current["semantic_diff"]["sha256"]
    )
    assert (
        hashlib.sha256(current_evidence_path.read_bytes()).hexdigest()
        == current["authoring_evidence"]["sha256"]
    )
    assert len(current_diff["added_quads"]) == current["semantic_diff"]["added_quads"] == 497
    assert len(current_diff["removed_quads"]) == current["semantic_diff"]["removed_quads"] == 0
    assert len(current_diff["changes"]) == current["semantic_diff"]["change_groups"] == 61
    assert (
        historical["reviewed_semantic_diff"]["claimed_digest"] != current["semantic_diff"]["sha256"]
    )

    disposition = {item["check_id"]: item["status"] for item in provenance["finding_disposition"]}
    assert disposition == {
        "ownership_and_imports": "resolved",
        "proposal_state_separation": "resolved",
        "resource_type_review": "resolved",
    }
    assert (
        provenance_raw
        == json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def test_p12_codex_review_contract_uses_reproducible_read_only_inputs() -> None:
    prompt = (ROOT / "docs" / "pilot" / "p12-codex-review-prompt.md").read_text(encoding="utf-8")
    schema = json.loads(
        (ROOT / "docs" / "pilot" / "p12-codex-review-output.schema.json").read_text(
            encoding="utf-8"
        )
    )
    backlog = (ROOT / "enterprise_ontology_workbench_mvp_backlog.yaml").read_text(encoding="utf-8")

    assert "No modifiques archivos" in prompt
    assert "./.venv/bin/ontology context --task" in prompt
    assert "./.venv/bin/ontology validate --json" in prompt
    assert "./.venv/bin/ontology diff --base main --json" in prompt
    assert "Claude" not in prompt
    assert schema["additionalProperties"] is False
    assert schema["properties"]["reviewer"]["const"] == "codex"
    assert schema["required"] == [
        "reviewer",
        "verdict",
        "summary",
        "findings",
        "checks",
    ]
    assert "title: Segundo Codex revisa la propuesta" in backlog
    assert (
        "title: Segundo Codex revisa la propuesta\n    priority: must\n    status: done" in backlog
    )
    assert "title: Revisión de dominio\n    priority: must\n    status: done" in backlog
    assert (
        "title: Publicar primer módulo de dominio\n    priority: must\n    status: in_progress"
    ) in backlog


def test_p12_current_codex_review_is_bound_to_the_current_snapshot() -> None:
    review_path = ROOT / "docs" / "pilot" / "p12-codex-review-current.json"
    provenance_path = ROOT / "docs" / "pilot" / "p12-codex-review-current-provenance.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

    assert review["reviewer"] == "codex"
    assert review["verdict"] == "approve"
    assert review["findings"] == []
    assert len(review["checks"]) >= 9
    assert {check["status"] for check in review["checks"]} == {"passed"}
    assert provenance["status"] == "current"
    assert provenance["reviewer"] == {
        "authentication": "ChatGPT",
        "client": "codex-cli",
        "version": "0.114.0",
    }
    assert provenance["reviewed_revision"] == {
        "branch": "proposal/p12-governed-knowledge-pilot",
        "head": "30e85558acfc32ae8487a71a5f0628291e6d5b8f",
        "knowledge_config_fingerprint": content_fingerprint(ROOT / "knowledge", ROOT / "config"),
    }
    assert provenance["semantic_diff"]["counts"] == {
        "added_quads": 497,
        "change_groups": 61,
        "removed_quads": 0,
    }
    reviewed_planning_inputs = {
        "enterprise_ontology_workbench_mvp_spec.md": (
            "740fa783ddae90d91d4e67b7229c1117c7aa88b8de2e5cb5717be01561615e4b"
        ),
        "enterprise_ontology_workbench_mvp_backlog.yaml": (
            "beb590dd94b6b5bf6f312f4066477901e8c8941b55f1dbffc0e4ae89f9fb7e28"
        ),
    }
    for artifact in provenance["artifacts"]:
        path = ROOT / artifact["path"]
        if artifact["path"] in reviewed_planning_inputs:
            assert artifact["sha256"] == reviewed_planning_inputs[artifact["path"]]
            assert hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]
        else:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    assert provenance["post_review_specification_extension"] == {
        "affected_plans": [f"P{number:02d}" for number in range(13, 24)],
        "p12_acceptance_changed": False,
        "review_scope": (
            "The review remains evidence for the P12 RDF snapshot and the "
            "specification/backlog digests captured on 2026-08-15."
        ),
        "status": "not_part_of_this_p12_review",
    }
    assert provenance["execution"]["isolated_copy"] is False
    assert provenance["execution"]["canonical_checkout_modified"] is False
    assert all(command["exit_code"] == 0 for command in provenance["execution"]["commands"])
    assert provenance["claude_compatibility"]["executed_for_acceptance"] is False

    assert not (ROOT / "docs/pilot/p12-codex-review-resolution.json").exists()
    assert (ROOT / "docs/pilot/archive/p12-codex-review-resolution-496.superseded.json").exists()


def test_p12_claude_artifact_is_only_sanitized_compatibility_evidence() -> None:
    artifact = json.loads(
        (ROOT / "docs" / "pilot" / "p12-claude-review-gate.json").read_text(encoding="utf-8")
    )

    assert artifact["client"] == {
        "distribution": "@anthropic-ai/claude-code",
        "subcommand": "--version",
        "version": "2.1.231",
        "version_exit_code": 0,
    }
    assert artifact["authentication"]["subcommand"] == "auth status"
    assert artifact["authentication"]["command_exit_code"] == 1
    assert artifact["authentication"]["loggedIn"] is False
    assert artifact["review_attempt"]["subcommand"] == "--print"
    assert artifact["review_attempt"]["command_exit_code"] == 1
    assert artifact["review_attempt"]["num_turns"] == 1
    assert artifact["review_attempt"]["duration_api_ms"] == 0
    assert artifact["review_attempt"]["total_cost_usd"] == 0
    assert sum(artifact["review_attempt"]["usage"].values()) == 0
    assert artifact["review_attempt"]["modelUsage"] == {}
    assert artifact["sanitization"]["secrets_included"] is False


def test_spec_preserves_the_source_baseline_and_records_the_codex_amendment() -> None:
    archive = ROOT / "source/enterprise_ontology_workbench_mvp_package.zip"
    with zipfile.ZipFile(archive) as package:
        original = package.read("enterprise_ontology_workbench_mvp_spec.md")
    current = (ROOT / "enterprise_ontology_workbench_mvp_spec.md").read_bytes()

    assert current != original
    assert hashlib.sha256(original).hexdigest() == (
        "c40fbf3a1efa557ed505d496270a73637b74e53a7cfc3cc86d41b3e1e015212c"
    )
    text = current.decode("utf-8")
    assert "Enmienda de aceptación del piloto (15 de agosto de 2026)" in text
    assert "Una segunda ejecución independiente de Codex" in text
    assert "P12 T04 | Hacer que un segundo Codex revise la propuesta" in text
    assert (ROOT / "docs/adr/013-revision-independiente-codex-en-piloto.md").exists()

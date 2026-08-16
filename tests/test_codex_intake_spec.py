import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]
SPEC_PATH = ROOT / "enterprise_ontology_workbench_mvp_spec.md"
BACKLOG_PATH = ROOT / "enterprise_ontology_workbench_mvp_backlog.yaml"


def _backlog() -> dict[str, Any]:
    document = yaml.safe_load(BACKLOG_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_codex_first_extension_has_complete_ordered_backlog() -> None:
    backlog = _backlog()
    plans = backlog["plans"]
    plan_by_id = {plan["id"]: plan for plan in plans}

    assert backlog["spec_version"] == "2.0"
    assert [plan["id"] for plan in plans] == [f"P{number:02d}" for number in range(24)]
    assert sum(len(plan["tasks"]) for plan in plans) == 250

    future_ids = [f"P{number:02d}" for number in range(13, 24)]
    assert sum(len(plan_by_id[plan_id]["tasks"]) for plan_id in future_ids) == 123
    assert plan_by_id["P13"]["depends_on"] == ["P12"]
    for previous, current in zip(future_ids[:-1], future_ids[1:], strict=True):
        assert plan_by_id[current]["depends_on"] == [previous]
    assert all(plan_by_id[plan_id]["status"] == "todo" for plan_id in future_ids)
    assert all(
        task["status"] == "todo" for plan_id in future_ids for task in plan_by_id[plan_id]["tasks"]
    )

    p12 = plan_by_id["P12"]
    assert p12["status"] == "in_progress"
    assert {task["id"]: task["status"] for task in p12["tasks"]} == {
        "P12_T01": "done",
        "P12_T02": "done",
        "P12_T03": "done",
        "P12_T04": "done",
        "P12_T05": "in_progress",
        "P12_T06": "in_progress",
        "P12_T07": "todo",
        "P12_T08": "todo",
        "P12_T09": "todo",
        "P12_T10": "todo",
        "P12_T11": "todo",
    }


def test_spec_and_backlog_have_the_same_task_ids() -> None:
    spec = SPEC_PATH.read_text(encoding="utf-8")
    spec_ids = {f"P{plan}_T{task}" for plan, task in re.findall(r"\| P(\d{2}) T(\d{2}) \|", spec)}
    backlog_ids = {task["id"] for plan in _backlog()["plans"] for task in plan["tasks"]}

    assert spec_ids == backlog_ids


def test_codex_first_contract_preserves_canonical_boundaries() -> None:
    spec = SPEC_PATH.read_text(encoding="utf-8")
    principles = _backlog()["principles"]

    assert principles["codex_is_primary_intake_interface"] is True
    assert principles["web_is_viewer_first"] is True
    assert principles["source_material_is_evidence_not_canonical"] is True
    assert principles["external_content_is_untrusted"] is True
    assert principles["human_decisions_gate_semantics"] is True
    assert principles["source_systems_are_read_only"] is True

    required_contracts = (
        "KnowledgeProject",
        "SourceRecord",
        "EvidenceRecord",
        "IntakeRun",
        "KnowledgeCandidate",
        "HumanDecision",
        "knowledge_intake",
        "knowledge_align",
        "knowledge_decide",
        "knowledge_publish",
    )
    assert all(contract in spec for contract in required_contracts)
    assert re.search(r"RDF y Git\s+continúan siendo la representación canónica", spec)
    assert "La web será viewer-first y read-only por defecto" in spec
    assert "Todo contenido fuente será tratado como datos" in spec
    assert "Nunca publicará o fusionará directamente" in spec


def test_all_required_source_modalities_and_adversarials_are_specified() -> None:
    spec = SPEC_PATH.read_text(encoding="utf-8")

    for source_type in ("PDF", "DOCX", "XLSX", "CSV", "GitHub", "PostgreSQL"):
        assert source_type in spec
    for guardrail in (
        "Prompt injection",
        "Path traversal",
        "Secret o PII",
        "SQL de escritura",
        "Receipt filtrado",
        "Decisión humana stale",
        "sin publicación parcial",
        "Reprocesamiento idéntico",
    ):
        assert guardrail in spec

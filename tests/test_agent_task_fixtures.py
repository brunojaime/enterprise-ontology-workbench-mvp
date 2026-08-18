from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _evaluate() -> dict[str, object]:
    result = subprocess.run(
        ["uv", "run", "python", "scripts/evaluate_agent_tasks.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def test_agent_task_fixtures_are_repeatable_and_cover_the_decision_rules() -> None:
    first = _evaluate()
    second = _evaluate()

    assert first == second
    assert first["passed"] is True
    fixtures = first["fixtures"]
    assert isinstance(fixtures, list)
    assert len(fixtures) == 8
    assert {fixture["decision"] for fixture in fixtures} >= {
        "reuse",
        "reject",
        "class",
        "individual",
        "concept",
        "property",
    }
    assert all(
        assertion["passed"] is True for fixture in fixtures for assertion in fixture["assertions"]
    )


def _fixture_checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    root.mkdir()
    for relative in ("agent_contract", "knowledge", "config"):
        shutil.copytree(ROOT / relative, root / relative)
    return root


def _evaluate_checkout(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/evaluate_agent_tasks.py",
            "--repository",
            str(root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_evaluator_rejects_a_tampered_expected_decision(tmp_path: Path) -> None:
    root = _fixture_checkout(tmp_path)
    fixture = root / "agent_contract/fixtures/class_vs_individual.yaml"
    fixture.write_text(
        fixture.read_text(encoding="utf-8").replace(
            "expected_decision: class",
            "expected_decision: concept",
        ),
        encoding="utf-8",
    )

    result = _evaluate_checkout(root)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["passed"] is False
    outcome = next(
        item for item in payload["fixtures"] if item["id"] == "choose_class_for_capability"
    )
    assert outcome["decision"] == "class"
    assert any("decision mismatch" in item for item in outcome["diagnostics"])


def test_evaluator_rejects_an_unknown_or_unproved_assertion(tmp_path: Path) -> None:
    root = _fixture_checkout(tmp_path)
    fixture = root / "agent_contract/fixtures/reuse_existing.yaml"
    fixture.write_text(
        fixture.read_text(encoding="utf-8").replace(
            "assertions: [search_before_create, reuse_matching_definition]",
            "assertions: [search_before_create, assertion_that_does_not_exist]",
        ),
        encoding="utf-8",
    )

    result = _evaluate_checkout(root)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["passed"] is False
    outcome = next(
        item for item in payload["fixtures"] if item["id"] == "reuse_existing_application"
    )
    assert outcome["assertions"][-1] == {
        "id": "assertion_that_does_not_exist",
        "passed": False,
    }


def test_evaluator_rejects_task_or_query_that_contradicts_declared_facts(
    tmp_path: Path,
) -> None:
    root = _fixture_checkout(tmp_path)
    fixture = root / "agent_contract/fixtures/class_vs_individual.yaml"
    text = fixture.read_text(encoding="utf-8")
    fixture.write_text(
        text.replace(
            "task: Modelar la categoría reutilizable de capacidades de despliegue.",
            "task: Modelar una entidad concreta identificable del inventario.",
        ).replace(
            "query: capacidad de despliegue",
            "query: texto irrelevante",
        ),
        encoding="utf-8",
    )

    result = _evaluate_checkout(root)
    payload = json.loads(result.stdout)
    outcome = next(
        item for item in payload["fixtures"] if item["id"] == "choose_class_for_capability"
    )

    assert result.returncode == 1
    assert payload["passed"] is False
    assert any("task does not demonstrate" in item for item in outcome["diagnostics"])
    assert any("query does not demonstrate" in item for item in outcome["diagnostics"])


def test_evaluator_derives_a_different_decision_when_independent_facts_change(
    tmp_path: Path,
) -> None:
    root = _fixture_checkout(tmp_path)
    fixture = root / "agent_contract/fixtures/class_vs_individual.yaml"
    fixture.write_text(
        fixture.read_text(encoding="utf-8").replace(
            "reusable_category: true",
            "concrete_identity: true",
        ),
        encoding="utf-8",
    )

    result = _evaluate_checkout(root)
    payload = json.loads(result.stdout)
    outcome = next(
        item for item in payload["fixtures"] if item["id"] == "choose_class_for_capability"
    )

    assert result.returncode == 1
    assert payload["passed"] is False
    assert outcome["decision"] == "individual"
    assert any("decision mismatch" in item for item in outcome["diagnostics"])
    assert any("assertion contract mismatch" in item for item in outcome["diagnostics"])

#!/usr/bin/env python3
"""Execute repeatable P08 decisions and assertions against canonical services."""

from __future__ import annotations

import argparse
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml
from ontology_core import (
    AgentContextService,
    AgentContractService,
    ContextRequest,
    FilesystemRdfStore,
    OntologyQueryService,
    ValidationService,
)
from ontology_core.search_receipts import normalize_search_query
from rdflib import URIRef
from rdflib.namespace import OWL, SKOS

ROOT = Path(__file__).parents[1]
ALLOWED_DECISIONS = {"reuse", "class", "individual", "concept", "property", "reject"}
CLASSIFIER_FACTS = {
    "reusable_category": "class",
    "concrete_identity": "individual",
    "controlled_vocabulary": "concept",
    "relation_between_resources": "property",
}
FACT_KEYS = frozenset(
    {
        "existing_match_iri",
        "candidate_iri",
        "requested_module",
        "reusable_category",
        "concrete_identity",
        "controlled_vocabulary",
        "relation_between_resources",
        "requires_validation",
        "task_signals",
        "query_signals",
    }
)


def _mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"fixture must be a mapping: {path.relative_to(path.parents[2])}")
    return value


def _local_name(iri: str) -> str:
    return iri.rsplit("#", 1)[-1].rstrip("/").rsplit("/", 1)[-1]


def _signals(raw: object, *, name: str, identifier: str) -> tuple[str, ...]:
    if (
        not isinstance(raw, list)
        or not raw
        or not all(isinstance(item, str) and item.strip() for item in raw)
    ):
        raise ValueError(f"fixture {name} are invalid: {identifier}")
    return tuple(raw)


def _facts(fixture: dict[str, Any], identifier: str) -> dict[str, Any]:
    raw = fixture.get("facts")
    if not isinstance(raw, dict) or set(raw) - FACT_KEYS:
        raise ValueError(f"fixture facts are invalid: {identifier}")
    for key in ("existing_match_iri", "candidate_iri", "requested_module"):
        value = raw.get(key)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"fixture fact {key} is invalid: {identifier}")
    for key in (*CLASSIFIER_FACTS, "requires_validation"):
        if key in raw and not isinstance(raw[key], bool):
            raise ValueError(f"fixture fact {key} is invalid: {identifier}")
    result = dict(raw)
    result["task_signals"] = _signals(
        raw.get("task_signals"), name="task_signals", identifier=identifier
    )
    if fixture.get("query") is not None:
        result["query_signals"] = _signals(
            raw.get("query_signals"), name="query_signals", identifier=identifier
        )
    elif raw.get("query_signals") not in (None, []):
        raise ValueError(f"fixture query_signals require a query: {identifier}")
    return result


def _required_assertions(facts: dict[str, Any]) -> set[str]:
    if facts.get("requires_validation"):
        return {"parser_executed", "shacl_executed", "linter_executed"}
    existing = facts.get("existing_match_iri")
    candidate = facts.get("candidate_iri")
    if isinstance(existing, str) and isinstance(candidate, str) and candidate != existing:
        return {"duplicate_detected", "no_new_iri"}
    if isinstance(existing, str) and facts.get("requested_module"):
        return {"owner_module_detected", "import_instead_of_duplicate"}
    if isinstance(existing, str):
        return {"search_before_create", "reuse_matching_definition"}
    if facts.get("reusable_category"):
        return {"category_has_possible_instances", "pascal_case_required"}
    if facts.get("concrete_identity"):
        return {"concrete_identity", "business_class_explicit", "snake_case_iri"}
    if facts.get("controlled_vocabulary"):
        return {"controlled_vocabulary", "no_automatic_owl_class"}
    if facts.get("relation_between_resources"):
        return {"lower_camel_case", "reading_direction", "valid_example"}
    return set()


def _derive_decision(
    facts: dict[str, Any], search_results: tuple[Any, ...]
) -> tuple[str, list[str]]:
    diagnostics: list[str] = []
    existing = facts.get("existing_match_iri")
    if isinstance(existing, str):
        if not any(result.iri == existing for result in search_results):
            diagnostics.append(f"existing match was not observed in search: {existing}")
            return "undetermined", diagnostics
        candidate = facts.get("candidate_iri")
        return (
            "reject" if isinstance(candidate, str) and candidate != existing else "reuse",
            diagnostics,
        )
    active = [decision for fact, decision in CLASSIFIER_FACTS.items() if facts.get(fact)]
    if len(active) != 1:
        diagnostics.append("facts must identify exactly one modeling category")
        return "undetermined", diagnostics
    return active[0], diagnostics


def _signal_diagnostics(task: str, search_text: str | None, facts: dict[str, Any]) -> list[str]:
    task_normalized = normalize_search_query(task)
    query_normalized = normalize_search_query(search_text or "")
    diagnostics = [
        f"task does not demonstrate declared fact: {signal}"
        for signal in facts["task_signals"]
        if normalize_search_query(signal) not in task_normalized
    ]
    diagnostics.extend(
        f"query does not demonstrate declared observation: {signal}"
        for signal in facts.get("query_signals", ())
        if normalize_search_query(signal) not in query_normalized
    )
    return diagnostics


def _assertion_result(
    assertion: str,
    *,
    facts: dict[str, Any],
    fixture: dict[str, Any],
    query: OntologyQueryService,
    search_id: str | None,
    validation_conforms: bool,
    modules: dict[str, tuple[str, ...]],
) -> tuple[bool, str]:
    expected_iri = fixture.get("expected_iri")
    iri = expected_iri if isinstance(expected_iri, str) else facts.get("candidate_iri")
    description = query.describe(iri) if isinstance(iri, str) else None
    search_text = fixture.get("query")
    search_results = (
        query.search_page(search_text, limit=20).items if isinstance(search_text, str) else ()
    )
    found = isinstance(expected_iri, str) and any(
        result.iri == expected_iri for result in search_results
    )
    expected_module = fixture.get("expected_module")
    module_iri = (
        f"{query.prefixes.configuration.base}id/module/{expected_module}"
        if isinstance(expected_module, str)
        else None
    )
    module_ontology_iri = (
        f"{query.prefixes.configuration.base}ontology/{expected_module}"
        if isinstance(expected_module, str)
        else None
    )

    checks: dict[str, bool] = {
        "search_before_create": (
            isinstance(search_text, str)
            and search_id is not None
            and query.validate_authoring_search_receipt(search_text, search_id)
        ),
        "reuse_matching_definition": found
        and facts.get("existing_match_iri") == expected_iri
        and description is not None
        and bool(description.definitions),
        "duplicate_detected": facts.get("existing_match_iri") == expected_iri
        and isinstance(facts.get("candidate_iri"), str)
        and facts.get("candidate_iri") != expected_iri
        and found,
        "no_new_iri": isinstance(facts.get("candidate_iri"), str)
        and query.describe(facts["candidate_iri"]) is None,
        "category_has_possible_instances": facts.get("reusable_category") is True,
        "pascal_case_required": facts.get("reusable_category") is True
        and isinstance(iri, str)
        and re.fullmatch(r"[A-Z][A-Za-z0-9]*", _local_name(iri)) is not None,
        "concrete_identity": facts.get("concrete_identity") is True
        and isinstance(expected_iri, str),
        "business_class_explicit": facts.get("concrete_identity") is True
        and isinstance(expected_iri, str)
        and query.resource_category(URIRef(expected_iri)) == "individual"
        and description is not None
        and any(value.value != str(OWL.NamedIndividual) for value in description.types),
        "snake_case_iri": isinstance(expected_iri, str)
        and re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", _local_name(expected_iri)) is not None,
        "controlled_vocabulary": facts.get("controlled_vocabulary") is True,
        "no_automatic_owl_class": facts.get("controlled_vocabulary") is True
        and (not isinstance(iri, str) or query.describe(iri) is None),
        "lower_camel_case": facts.get("relation_between_resources") is True
        and isinstance(expected_iri, str)
        and re.fullmatch(r"[a-z][A-Za-z0-9]*", _local_name(expected_iri)) is not None,
        "reading_direction": description is not None
        and any(quad.predicate.value == str(SKOS.scopeNote) for quad in description.outgoing),
        "valid_example": description is not None
        and any(quad.predicate.value == str(SKOS.example) for quad in description.outgoing),
        "owner_module_detected": found
        and module_iri is not None
        and any(
            result.iri == expected_iri and module_iri in result.modules for result in search_results
        ),
        "import_instead_of_duplicate": module_ontology_iri is not None
        and isinstance(facts.get("requested_module"), str)
        and module_ontology_iri in modules.get(facts["requested_module"], ()),
        "parser_executed": validation_conforms,
        "shacl_executed": validation_conforms,
        "linter_executed": validation_conforms,
    }
    passed = checks.get(assertion, False)
    detail = "passed" if passed else f"assertion {assertion} was not demonstrated"
    return passed, detail


def evaluate(repository_root: Path = ROOT) -> dict[str, object]:
    root = repository_root.resolve(strict=True)
    contract = AgentContractService(root)
    store = FilesystemRdfStore(root / "knowledge", root / "config/namespace.yaml")
    query = OntologyQueryService(store.load(), store.prefixes)
    validation = ValidationService(store).validate_repository()
    module_imports = {
        module.identifier: module.imports for module in query.modules(store.discover_modules())
    }
    entries = contract.manifest.get("task_fixtures")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest task_fixtures must be a non-empty list")

    outcomes: list[dict[str, object]] = []
    seen: set[str] = set()
    for relative in entries:
        if not isinstance(relative, str):
            raise ValueError("fixture paths must be strings")
        path = contract.contract_root / relative
        if path.is_symlink():
            raise ValueError(f"unsafe fixture path: {relative}")
        path = path.resolve(strict=True)
        if not path.is_relative_to(contract.contract_root) or not path.is_file():
            raise ValueError(f"unsafe fixture path: {relative}")
        fixture = _mapping(path)
        identifier = fixture.get("id")
        expected_decision = fixture.get("expected_decision")
        assertions = fixture.get("assertions")
        task = fixture.get("task")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError(f"fixture id is missing or duplicated: {relative}")
        seen.add(identifier)
        if expected_decision not in ALLOWED_DECISIONS:
            raise ValueError(f"fixture decision is invalid: {identifier}")
        if not isinstance(task, str) or not task.strip():
            raise ValueError(f"fixture task is empty: {identifier}")
        if (
            not isinstance(assertions, list)
            or not assertions
            or not all(isinstance(item, str) and item for item in assertions)
        ):
            raise ValueError(f"fixture assertions are invalid: {identifier}")

        facts = _facts(fixture, identifier)
        search_text = fixture.get("query")
        search_page = (
            query.search_page(search_text, limit=20) if isinstance(search_text, str) else None
        )
        expected_iri = fixture.get("expected_iri")
        search_results = search_page.items if search_page else ()
        actual_decision, diagnostics = _derive_decision(facts, search_results)
        diagnostics.extend(
            _signal_diagnostics(
                task,
                search_text if isinstance(search_text, str) else None,
                facts,
            )
        )
        required_assertions = _required_assertions(facts)
        if not required_assertions:
            diagnostics.append("facts do not select a supported assertion contract")
        if set(assertions) != required_assertions or len(assertions) != len(required_assertions):
            diagnostics.append(
                "assertion contract mismatch: required " + ", ".join(sorted(required_assertions))
            )
        if actual_decision != expected_decision:
            diagnostics.append(
                f"decision mismatch: expected {expected_decision}, evaluated {actual_decision}"
            )
        if isinstance(expected_iri, str) and (
            search_page is None or not any(item.iri == expected_iri for item in search_page.items)
        ):
            diagnostics.append(f"expected IRI was not returned: {expected_iri}")
        if fixture.get("repository_conforms") is True and not validation.conforms:
            diagnostics.append("repository validation did not conform")

        assertion_results: list[dict[str, object]] = []
        for assertion in assertions:
            passed, detail = _assertion_result(
                assertion,
                facts=facts,
                fixture=fixture,
                query=query,
                search_id=search_page.search_id if search_page else None,
                validation_conforms=validation.conforms,
                modules=module_imports,
            )
            assertion_results.append({"id": assertion, "passed": passed})
            if not passed:
                diagnostics.append(detail)

        context = AgentContextService(store).generate(
            ContextRequest(task=task, terms=(search_text,) if isinstance(search_text, str) else ())
        )
        outcomes.append(
            {
                "id": identifier,
                "decision": actual_decision,
                "expected_decision": expected_decision,
                "assertions": assertion_results,
                "search_results": len(search_page.items) if search_page else 0,
                "context_digest": sha256(context.json.encode()).hexdigest(),
                "diagnostics": diagnostics,
                "passed": not diagnostics,
            }
        )
    return {
        "contract_version": contract.version,
        "passed": all(bool(outcome["passed"]) for outcome in outcomes),
        "fixtures": outcomes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=ROOT)
    arguments = parser.parse_args(argv)
    payload = evaluate(arguments.repository)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

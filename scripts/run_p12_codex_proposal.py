#!/usr/bin/env python3
"""Materialize the P12 Codex proposal through one real MCP stdio session."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

BASE = "https://knowledge.example.com/"
ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / ".eow/audit/p12-codex.jsonl"
EVIDENCE = ROOT / "docs/pilot/p12-authoring-evidence.json"
DIFF = ROOT / "docs/pilot/p12-semantic-diff.json"
CHECKPOINT = ROOT / ".eow/audit/p12-session.json"
AGENT = "Codex P12 governed pilot"

RESOURCE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "iri": f"{BASE}ontology/knowledge_governance",
        "module_id": "knowledge_governance",
        "kind": "ontology",
        "preferred_label_es": "Gobernanza del conocimiento",
        "definition_es": (
            "Módulo piloto mínimo para describir cómo una necesidad empresarial llega a "
            "conocimiento RDF gobernado y qué software soporta ese proceso."
        ),
        "evidence": "enterprise_ontology_workbench_mvp_spec.md, secciones 1 a 4, 8 y 34",
        "query": "gobernanza del conocimiento",
    },
    {
        "iri": f"{BASE}ontology/knowledge_governance#EnterpriseKnowledgeGovernance",
        "module_id": "knowledge_governance",
        "kind": "concept",
        "preferred_label_es": "Gobernanza del conocimiento empresarial",
        "definition_es": (
            "Disciplina que controla cómo el conocimiento empresarial se propone, valida, "
            "revisa y publica como información canónica trazable."
        ),
        "evidence": "enterprise_ontology_workbench_mvp_spec.md, secciones 1 a 4 y 34",
        "query": "gobernanza del conocimiento empresarial",
    },
    {
        "iri": f"{BASE}ontology/knowledge_governance#KnowledgePublicationProcess",
        "module_id": "knowledge_governance",
        "kind": "class",
        "preferred_label_es": "Proceso de publicación de conocimiento",
        "definition_es": (
            "Proceso gobernado que convierte una necesidad y su evidencia en una propuesta "
            "RDF validada, revisada y apta para publicación mediante Git."
        ),
        "evidence": "enterprise_ontology_workbench_mvp_spec.md, secciones 4 y 18",
        "query": "proceso de publicación de conocimiento",
    },
    {
        "iri": f"{BASE}ontology/software#SoftwareComponent",
        "module_id": "software",
        "kind": "class",
        "preferred_label_es": "Componente de software",
        "definition_es": (
            "Unidad identificable de software que forma parte de una aplicación y encapsula "
            "una responsabilidad técnica."
        ),
        "evidence": "packages/ontology_core/ y especificación canónica, sección 8",
        "query": "componente de software",
    },
    {
        "iri": f"{BASE}ontology/software#SourceCodeRepository",
        "module_id": "software",
        "kind": "class",
        "preferred_label_es": "Repositorio de código fuente",
        "definition_es": (
            "Repositorio versionado que contiene los artefactos fuente mediante los cuales "
            "se implementa software."
        ),
        "evidence": "Git del checkout y README.md",
        "query": "repositorio de código fuente",
    },
    {
        "iri": f"{BASE}ontology/knowledge_governance#governedThrough",
        "module_id": "knowledge_governance",
        "kind": "object_property",
        "preferred_label_es": "se gobierna mediante",
        "definition_es": (
            "Vincula un concepto de gobierno con el proceso concreto mediante el cual se aplica."
        ),
        "evidence": "enterprise_ontology_workbench_mvp_spec.md, sección 4",
        "query": "se gobierna mediante",
        "reading_direction_es": (
            "Se lee desde el concepto de gobernanza hacia un proceso de publicación "
            "de conocimiento."
        ),
        "valid_example": (
            "kg:EnterpriseKnowledgeGovernance kg:governedThrough kgid:ontology_change_publication ."
        ),
        "domain": "http://www.w3.org/2004/02/skos/core#Concept",
        "range": f"{BASE}ontology/knowledge_governance#KnowledgePublicationProcess",
    },
    {
        "iri": f"{BASE}ontology/knowledge_governance#supportedByApplication",
        "module_id": "knowledge_governance",
        "kind": "object_property",
        "preferred_label_es": "es soportado por aplicación",
        "definition_es": (
            "Indica la aplicación que ofrece soporte operativo a un proceso de publicación "
            "de conocimiento."
        ),
        "evidence": "enterprise_ontology_workbench_mvp_spec.md, secciones 4 y 8",
        "query": "es soportado por aplicación",
        "reading_direction_es": (
            "Se lee desde el proceso gobernado hacia la aplicación que lo soporta."
        ),
        "valid_example": (
            "kgid:ontology_change_publication kg:supportedByApplication app:workbench ."
        ),
        "domain": f"{BASE}ontology/knowledge_governance#KnowledgePublicationProcess",
        "range": f"{BASE}ontology/software#Application",
    },
    {
        "iri": f"{BASE}ontology/software#isComposedOf",
        "module_id": "software",
        "kind": "object_property",
        "preferred_label_es": "se compone de",
        "definition_es": (
            "Vincula una aplicación con un componente de software que forma parte de ella."
        ),
        "evidence": "enterprise_ontology_workbench_mvp_spec.md, secciones 4 y 8",
        "query": "se compone de",
        "reading_direction_es": (
            "Se lee desde la aplicación hacia uno de sus componentes de software."
        ),
        "valid_example": "app:workbench software:isComposedOf component:ontology_core .",
        "domain": f"{BASE}ontology/software#Application",
        "range": f"{BASE}ontology/software#SoftwareComponent",
    },
    {
        "iri": f"{BASE}ontology/software#implementedByRepository",
        "module_id": "software",
        "kind": "object_property",
        "preferred_label_es": "es implementado por repositorio",
        "definition_es": (
            "Indica el repositorio de código fuente que contiene la implementación de un "
            "componente de software."
        ),
        "evidence": "packages/ontology_core/ y Git del checkout",
        "query": "es implementado por repositorio",
        "reading_direction_es": (
            "Se lee desde el componente hacia el repositorio que contiene su implementación."
        ),
        "valid_example": (
            "component:ontology_core software:implementedByRepository "
            "repository:enterprise_ontology_workbench_mvp ."
        ),
        "domain": f"{BASE}ontology/software#SoftwareComponent",
        "range": f"{BASE}ontology/software#SourceCodeRepository",
    },
    {
        "iri": f"{BASE}id/knowledge_governance/process/ontology_change_publication",
        "module_id": "knowledge_governance",
        "kind": "individual",
        "preferred_label_es": "Publicación de cambios ontológicos",
        "definition_es": "",
        "evidence": "enterprise_ontology_workbench_mvp_spec.md, secciones 4 y 18",
        "query": "publicación de cambios ontológicos",
        "class_iri": f"{BASE}ontology/knowledge_governance#KnowledgePublicationProcess",
        "source_id": "p12_ontology_change_publication",
    },
    {
        "iri": f"{BASE}id/software/component/ontology_core",
        "module_id": "software",
        "kind": "individual",
        "preferred_label_es": "ontology_core",
        "definition_es": "",
        "evidence": "packages/ontology_core/pyproject.toml",
        "query": "ontology core",
        "class_iri": f"{BASE}ontology/software#SoftwareComponent",
        "source_id": "p12_ontology_core_component",
    },
    {
        "iri": f"{BASE}id/software/repository/enterprise_ontology_workbench_mvp",
        "module_id": "software",
        "kind": "individual",
        "preferred_label_es": "enterprise-ontology-workbench-mvp",
        "definition_es": "",
        "evidence": "Git 30e85558acfc32ae8487a71a5f0628291e6d5b8f y README.md",
        "query": "enterprise ontology workbench mvp",
        "class_iri": f"{BASE}ontology/software#SourceCodeRepository",
        "source_id": "p12_enterprise_ontology_workbench_repository",
    },
    {
        "iri": f"{BASE}id/competency-question/governed_knowledge_traceability",
        "module_id": "knowledge_governance",
        "kind": "competency_question",
        "preferred_label_es": "Trazabilidad del conocimiento gobernado",
        "definition_es": (
            "Pregunta transversal del piloto que comprueba el recorrido entre dominio, "
            "proceso y software."
        ),
        "evidence": "enterprise_ontology_workbench_mvp_spec.md, sección 34",
        "query": "trazabilidad del conocimiento gobernado",
        "question_text_es": (
            "¿Qué proceso gobierna el conocimiento empresarial y qué aplicación, componente "
            "y repositorio lo soportan?"
        ),
        "acceptance_criterion_es": (
            "La consulta devuelve el concepto, proceso, aplicación, componente y repositorio "
            "del piloto."
        ),
    },
)

RELATIONS: tuple[dict[str, Any], ...] = (
    {
        "subject": f"{BASE}ontology/knowledge_governance",
        "predicate": "http://purl.org/dc/terms/identifier",
        "literal": "knowledge_governance",
        "evidence": "Identificador del módulo declarado en knowledge/manifest.ttl",
    },
    {
        "subject": f"{BASE}ontology/knowledge_governance",
        "predicate": "http://purl.org/dc/terms/rightsHolder",
        "literal": "Equipo de gobernanza ontológica (pendiente de confirmación de dominio)",
        "language": "es",
        "evidence": "Owner provisional; requiere el gate humano P12_T05",
    },
    {
        "subject": f"{BASE}ontology/knowledge_governance",
        "predicate": "http://www.w3.org/2002/07/owl#imports",
        "object_iri": f"{BASE}ontology/core",
        "evidence": "Dependencia del contrato de gobernanza común",
    },
    {
        "subject": f"{BASE}ontology/knowledge_governance",
        "predicate": "http://www.w3.org/2002/07/owl#imports",
        "object_iri": f"{BASE}ontology/software",
        "evidence": "Dependencia de las categorías de aplicación y software reutilizadas",
    },
    {
        "subject": f"{BASE}ontology/knowledge_governance#EnterpriseKnowledgeGovernance",
        "predicate": f"{BASE}ontology/knowledge_governance#governedThrough",
        "object_iri": f"{BASE}id/knowledge_governance/process/ontology_change_publication",
        "evidence": "Recorrido transversal definido en la pregunta real del piloto P12",
    },
    {
        "subject": f"{BASE}id/knowledge_governance/process/ontology_change_publication",
        "predicate": f"{BASE}ontology/knowledge_governance#supportedByApplication",
        "object_iri": f"{BASE}id/software/application/workbench",
        "evidence": "El Workbench ejecuta el protocolo gobernado descrito por la especificación",
    },
    {
        "subject": f"{BASE}id/software/application/workbench",
        "predicate": f"{BASE}ontology/software#isComposedOf",
        "object_iri": f"{BASE}id/software/component/ontology_core",
        "evidence": "packages/ontology_core/ y arquitectura de la especificación, sección 8",
    },
    {
        "subject": f"{BASE}id/software/component/ontology_core",
        "predicate": f"{BASE}ontology/software#implementedByRepository",
        "object_iri": f"{BASE}id/software/repository/enterprise_ontology_workbench_mvp",
        "evidence": "packages/ontology_core/pyproject.toml y Git del checkout",
    },
    {
        "subject": f"{BASE}id/competency-question/governed_knowledge_traceability",
        "predicate": f"{BASE}ontology/competency#queryFile",
        "literal": "governed_knowledge_traceability.rq",
        "evidence": "Consulta SPARQL local confinada del piloto",
    },
    {
        "subject": f"{BASE}id/competency-question/governed_knowledge_traceability",
        "predicate": f"{BASE}ontology/competency#minimumResultCount",
        "literal": "1",
        "datatype": "http://www.w3.org/2001/XMLSchema#nonNegativeInteger",
        "evidence": "La pregunta transversal requiere al menos un recorrido completo",
    },
)


def _structured(result: CallToolResult, tool: str) -> dict[str, Any]:
    if result.is_error or not isinstance(result.structured_content, dict):
        raise RuntimeError(f"{tool} failed: {result.content}")
    return dict(result.structured_content)


def _receipt_snapshot(token: str) -> str:
    encoded = token.removeprefix("eow-search-v2:").split(".", 1)[0]
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    return str(payload["s"])


async def _run() -> None:
    if AUDIT.exists() or EVIDENCE.exists() or DIFF.exists() or CHECKPOINT.exists():
        raise RuntimeError("P12 evidence already exists; refusing to overwrite an audit trail")
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "ontology_mcp.server",
            "--repository",
            ROOT.as_posix(),
            "--audit-log",
            AUDIT.relative_to(ROOT).as_posix(),
            "--write-enabled",
        ],
        cwd=ROOT,
    )
    resources: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    async with stdio_client(parameters) as (read, write):  # noqa: SIM117
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            modules = _structured(
                await session.call_tool("ontology_list_modules", {"request": {}}),
                "ontology_list_modules",
            )
            context = _structured(
                await session.call_tool(
                    "ontology_get_context",
                    {"request": {"task": "Proponer el recorrido transversal real del piloto P12"}},
                ),
                "ontology_get_context",
            )
            reused = _structured(
                await session.call_tool(
                    "ontology_describe",
                    {"request": {"iri": f"{BASE}id/software/application/workbench"}},
                ),
                "ontology_describe",
            )
            previous_snapshot = str(modules["snapshot"])
            for ordinal, spec in enumerate(RESOURCE_SPECS, start=1):
                search = _structured(
                    await session.call_tool(
                        "ontology_search",
                        {
                            "request": {
                                "text": spec["query"],
                                "limit": 50,
                                "offset": 0,
                                "rdf_types": [],
                                "modules": [],
                            }
                        },
                    ),
                    "ontology_search",
                )
                receipt = str(search["search_id"])
                if _receipt_snapshot(receipt) != previous_snapshot:
                    raise RuntimeError(
                        "search receipt is not tied to the immediately prior snapshot"
                    )
                if any(item["iri"] == spec["iri"] for item in search["items"]):
                    raise RuntimeError(
                        f"resource already existed before its governed search: {spec['iri']}"
                    )
                request = {key: value for key, value in spec.items() if key not in {"query"}}
                request.update(
                    {
                        "agent": AGENT,
                        "author": "Codex",
                        "search_query": spec["query"],
                        "search_id": receipt,
                        "search_confirmed": True,
                    }
                )
                write_result = _structured(
                    await session.call_tool("ontology_propose_term", {"request": request}),
                    "ontology_propose_term",
                )
                if write_result.get("operation") != "created":
                    raise RuntimeError(f"MCP did not create {spec['iri']}")
                previous_snapshot = str(write_result["snapshot"])
                resources.append(
                    {
                        "ordinal": ordinal,
                        "iri": spec["iri"],
                        "kind": spec["kind"],
                        "query": spec["query"],
                        "search": search,
                        "search_snapshot": _receipt_snapshot(receipt),
                        "write": write_result,
                        "tool": "ontology_propose_term",
                    }
                )
                CHECKPOINT.write_text(
                    json.dumps({"resources": resources}, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )

            for ordinal, relation in enumerate(RELATIONS, start=1):
                result = _structured(
                    await session.call_tool(
                        "ontology_propose_relation",
                        {"request": {"agent": AGENT, **relation}},
                    ),
                    "ontology_propose_relation",
                )
                relations.append(
                    {
                        "ordinal": ordinal,
                        "request": relation,
                        "write": result,
                        "tool": "ontology_propose_relation",
                    }
                )
                CHECKPOINT.write_text(
                    json.dumps(
                        {"relations": relations, "resources": resources},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )

            post_write_verification: list[dict[str, Any]] = []
            for spec in RESOURCE_SPECS:
                search = _structured(
                    await session.call_tool(
                        "ontology_search",
                        {
                            "request": {
                                "text": spec["query"],
                                "limit": 50,
                                "offset": 0,
                                "rdf_types": [],
                                "modules": [],
                            }
                        },
                    ),
                    "ontology_search",
                )
                target_found = any(item["iri"] == spec["iri"] for item in search["items"])
                if not target_found:
                    raise RuntimeError(
                        "post-write duplicate search does not recover the created resource: "
                        f"{spec['iri']}"
                    )
                post_write_verification.append(
                    {
                        "iri": spec["iri"],
                        "query": spec["query"],
                        "search": search,
                        "target_found": True,
                    }
                )

            validation = _structured(
                await session.call_tool("ontology_validate", {"request": {}}),
                "ontology_validate",
            )
            semantic_diff = _structured(
                await session.call_tool("ontology_diff", {"request": {"base": "main"}}),
                "ontology_diff",
            )
            concept_review = _structured(
                await session.call_tool(
                    "ontology_describe",
                    {
                        "request": {
                            "iri": (
                                f"{BASE}ontology/knowledge_governance#EnterpriseKnowledgeGovernance"
                            )
                        }
                    },
                ),
                "ontology_describe",
            )
            server_name = initialized.server_info.name

    audit = [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines()]
    expected_tools = ["ontology_propose_term"] * len(resources) + [
        "ontology_propose_relation"
    ] * len(relations)
    if [entry["tool"] for entry in audit] != expected_tools:
        raise RuntimeError("MCP audit order does not match the governed authoring flow")
    if not all(entry["result"] == "success" and entry["agent"] == AGENT for entry in audit):
        raise RuntimeError("MCP audit contains a non-successful or foreign write")
    if validation.get("conforms") is not True:
        raise RuntimeError("the materialized P12 proposal is not conforming")
    diff_payload = semantic_diff.get("diff", semantic_diff)
    if diff_payload.get("removed_quads"):
        raise RuntimeError("initial import diff unexpectedly removed RDF quads")

    evidence = {
        "schema_version": "1.0",
        "agent": AGENT,
        "server": server_name,
        "base": "main",
        "initial_snapshot": modules["snapshot"],
        "context": {
            "task": "Proponer el recorrido transversal real del piloto P12",
            "bytes": len(str(context["markdown"]).encode("utf-8")),
            "reused_resource": reused["description"]["resource"]["value"],
        },
        "resources": resources,
        "post_write_verification": post_write_verification,
        "relations": relations,
        "audit": audit,
        "validation": validation,
        "diff": {
            "base": diff_payload["base"],
            "head": diff_payload["head"],
            "added_quads": len(diff_payload["added_quads"]),
            "removed_quads": len(diff_payload["removed_quads"]),
            "changes": len(diff_payload["changes"]),
        },
        "impact_review": concept_review["impact"],
    }
    EVIDENCE.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    DIFF.write_text(
        json.dumps(semantic_diff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    CHECKPOINT.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    asyncio.run(_run())


if __name__ == "__main__":
    main()

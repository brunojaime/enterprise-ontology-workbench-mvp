"""Bounded agent context endpoints backed by the semantic core."""

from typing import Annotated

from fastapi import APIRouter, Depends
from ontology_core import AgentContractService, ContextBudget, ContextRequest

from enterprise_ontology_api.dependencies import runtime_snapshot
from enterprise_ontology_api.errors import error_responses
from enterprise_ontology_api.models import (
    AgentRuleModel,
    AgentSkillStatusModel,
    AgentStatusModel,
    ContextRequestModel,
    ContextResponseModel,
)
from enterprise_ontology_api.runtime import RuntimeSnapshot

router = APIRouter(prefix="/api/agent", tags=["agent-context"])


@router.post(
    "/context",
    response_model=ContextResponseModel,
    responses=error_responses(422),
)
def agent_context(
    request: ContextRequestModel,
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    pack = snapshot.context.generate(
        ContextRequest(
            task=request.task,
            terms=tuple(request.terms),
            modules=tuple(request.modules),
            budget=ContextBudget(
                max_terms=request.max_terms,
                depth=request.depth,
                max_bytes=request.max_bytes,
            ),
        )
    )
    return {
        "payload": pack.payload,
        "json": pack.json,
        "markdown": pack.markdown,
        "truncated": pack.truncated,
    }


@router.get("/rules", response_model=list[AgentRuleModel])
def agent_rules(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> list[dict[str, str]]:
    contract = AgentContractService(snapshot.store.knowledge_root.parent)
    return [
        {
            "id": rule.identifier,
            "source": f"agent_contract/{rule.path}",
            "content": rule.content,
        }
        for rule in contract.rules
    ]


@router.get("/skills", response_model=AgentSkillStatusModel)
def agent_skills(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    contract = AgentContractService(snapshot.store.knowledge_root.parent)
    status = contract.status()
    return {
        "available": list(status.skills),
        "status": "synchronized" if status.synchronized else "stale",
        "version": status.version,
    }


@router.get("/status", response_model=AgentStatusModel)
def agent_status(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    contract = AgentContractService(snapshot.store.knowledge_root.parent)
    status = contract.status()
    return {
        "context_available": True,
        "rules_available": True,
        "skills_available": bool(status.skills),
        "canonical_contract_available": True,
        "version": status.version,
        "digest": status.digest,
        "synchronized": status.synchronized,
        "stale": list(status.stale),
        "generated": list(status.generated),
        "mcp_status": "available_stdio",
        "cli_commands": [
            "ontology status",
            "ontology modules",
            "ontology search",
            "ontology describe",
            "ontology context",
            "ontology validate",
            "ontology diff",
            "ontology impact",
            "ontology query",
            "ontology agent_sync",
        ],
        "validation_conforms": snapshot.validation_report.conforms,
    }

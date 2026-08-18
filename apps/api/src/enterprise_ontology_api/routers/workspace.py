"""Workspace and RDF module endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from ontology_core import AgentContractError, AgentContractService

from enterprise_ontology_api.dependencies import runtime_manager, runtime_snapshot
from enterprise_ontology_api.errors import error_responses
from enterprise_ontology_api.models import (
    ModuleGraphModel,
    ModuleModel,
    ModulePageModel,
    RuntimeStatusModel,
    WorkspaceModel,
)
from enterprise_ontology_api.routers.helpers import module_definition, module_payload, rdf_value
from enterprise_ontology_api.runtime import RuntimeManager, RuntimeSnapshot

router = APIRouter(prefix="/api", tags=["workspace"])


def _agent_contract_status(snapshot: RuntimeSnapshot) -> str:
    try:
        synchronized = (
            AgentContractService(snapshot.store.knowledge_root.parent).status().synchronized
        )
    except AgentContractError:
        return "not_available"
    return "synchronized" if synchronized else "stale"


def _status(snapshot: RuntimeSnapshot) -> dict[str, object]:
    stats = snapshot.query.stats(snapshot.context.modules)
    return {
        "ready": True,
        "generation": snapshot.generation,
        "loaded_at": snapshot.loaded_at,
        "revision": snapshot.revision.to_dict(),
        "quads": stats.quads,
        "modules": len(snapshot.context.modules),
        "validation_conforms": snapshot.validation_report.conforms,
    }


@router.get("/workspace", response_model=WorkspaceModel, responses=error_responses(500))
def get_workspace(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    categories = snapshot.query.category_counts()
    return {
        "runtime": _status(snapshot),
        "stats": snapshot.query.stats(snapshot.context.modules).to_dict(),
        "validation": snapshot.validation_report.to_dict(),
        "competency_questions": len(snapshot.questions.list()),
        "agent_contract_status": _agent_contract_status(snapshot),
        "branch": snapshot.revision.branch,
        "commit": snapshot.revision.commit,
        "pending_changes": snapshot.revision.dirty,
        "module_count": len(snapshot.context.modules),
        "class_count": categories.classes,
        "property_count": categories.properties,
        "concept_count": categories.concepts,
        "individual_count": categories.individuals,
        "validation_conforms": snapshot.validation_report.conforms,
    }


@router.get("/workspace/status", response_model=RuntimeStatusModel)
def get_status(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    return _status(snapshot)


@router.post(
    "/workspace/reload",
    response_model=RuntimeStatusModel,
    responses=error_responses(422, 500),
)
def reload_workspace(
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
) -> dict[str, object]:
    return _status(manager.reload())


@router.get(
    "/modules",
    response_model=ModulePageModel,
    responses=error_responses(422),
)
def list_modules(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    modules = snapshot.context.modules
    selected = modules[offset : offset + limit]
    return {
        "items": [module_payload(snapshot, module) for module in selected],
        "total": len(modules),
        "offset": offset,
        "limit": limit,
        "has_next": offset + len(selected) < len(modules),
    }


@router.get(
    "/modules/{module_id}",
    response_model=ModuleModel,
    responses=error_responses(404, 422),
)
def get_module(
    module_id: str,
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
    term_offset: Annotated[int, Query(ge=0)] = 0,
    term_limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    return module_payload(
        snapshot,
        module_definition(snapshot, module_id),
        term_offset=term_offset,
        term_limit=term_limit,
    )


def _module_graph(
    snapshot: RuntimeSnapshot,
    module_id: str,
    offset: int,
    limit: int,
) -> dict[str, object]:
    module = module_definition(snapshot, module_id)
    graph_iri = module.graph_iri
    quads = sorted(
        (quad for quad in snapshot.dataset.quads((None, None, None, None)) if quad[3] == graph_iri),
        key=lambda quad: tuple(str(node) for node in quad),
    )
    selected = quads[offset : offset + limit]
    return {
        "module_id": module_id,
        "graph_iri": str(graph_iri),
        "total": len(quads),
        "offset": offset,
        "limit": limit,
        "truncated": offset + len(selected) < len(quads),
        "quads": [
            {
                "subject": rdf_value(subject, snapshot),
                "predicate": rdf_value(predicate, snapshot),
                "object": rdf_value(obj, snapshot),
                "graph": rdf_value(graph, snapshot),
            }
            for subject, predicate, obj, graph in selected
            if graph is not None
        ],
    }


@router.get(
    "/modules/{module_id}/graph",
    response_model=ModuleGraphModel,
    responses=error_responses(404, 422),
)
def get_module_graph(
    module_id: str,
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1500)] = 500,
) -> dict[str, object]:
    return _module_graph(snapshot, module_id, offset, limit)


@router.get(
    "/modules/{module_id}/raw",
    response_model=None,
    responses={
        200: {
            "description": "Read-only Turtle serialization of the module graph.",
            "content": {"text/turtle": {"schema": {"type": "string"}}},
        },
        **error_responses(404, 422),
    },
)
def get_module_raw(
    module_id: str,
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> PlainTextResponse:
    """Return a read-only Turtle view generated by the semantic core."""

    module = module_definition(snapshot, module_id)
    return PlainTextResponse(
        snapshot.store.serialize_graph(module.graph_iri),
        media_type="text/turtle; charset=utf-8",
    )


@router.get(
    "/graph/module",
    response_model=ModuleGraphModel,
    responses=error_responses(404, 422),
    tags=["graph"],
)
def get_graph_module(
    module_id: str,
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1500)] = 500,
) -> dict[str, object]:
    return _module_graph(snapshot, module_id, offset, limit)

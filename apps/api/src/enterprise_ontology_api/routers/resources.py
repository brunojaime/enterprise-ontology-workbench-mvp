"""Search, describe and bounded graph endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from ontology_core import NeighborhoodFilter, NeighborhoodLimits

from enterprise_ontology_api.dependencies import runtime_snapshot
from enterprise_ontology_api.errors import ApiProblem, error_responses
from enterprise_ontology_api.models import (
    DatasetStatsModel,
    NeighborhoodModel,
    ResourceDescriptionModel,
    SearchPageModel,
)
from enterprise_ontology_api.runtime import RuntimeSnapshot

router = APIRouter(prefix="/api", tags=["resources"])


@router.get(
    "/resources/search",
    response_model=SearchPageModel,
    responses=error_responses(422),
)
def search_resources(
    q: Annotated[str, Query(min_length=1)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    rdf_type: Annotated[str | None, Query(alias="type")] = None,
    module: str | None = None,
) -> dict[str, object]:
    return snapshot.query.search_page(
        q,
        limit=limit,
        offset=offset,
        rdf_types=frozenset((rdf_type,)) if rdf_type else frozenset(),
        modules=frozenset((module,)) if module else frozenset(),
    ).to_dict()


@router.get(
    "/resources/describe",
    response_model=ResourceDescriptionModel,
    responses=error_responses(404, 422),
)
def describe_resource(
    iri: Annotated[str, Query(min_length=1)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    detail = snapshot.detail.describe(iri)
    if detail is None:
        raise ApiProblem(
            404,
            "resource.not_found",
            "The requested RDF resource does not exist.",
            details={"iri": iri},
        )
    payload = detail.to_dict()
    payload["git_history"] = [
        entry.to_dict()
        for entry in snapshot.history.read(
            snapshot.store.source_paths_for(iri),
            revision=snapshot.revision.commit,
        )
    ]
    return payload


@router.get(
    "/graph/neighborhood",
    response_model=NeighborhoodModel,
    responses=error_responses(422),
    tags=["graph"],
)
def neighborhood(
    center: Annotated[str, Query(min_length=1)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
    depth: Annotated[int, Query(ge=0, le=3)] = 1,
    max_nodes: Annotated[int, Query(ge=1, le=500)] = 500,
    max_edges: Annotated[int, Query(ge=0, le=1500)] = 1500,
    graph_iri: Annotated[list[str] | None, Query()] = None,
    predicate: Annotated[list[str] | None, Query()] = None,
    rdf_type: Annotated[list[str] | None, Query(alias="type")] = None,
) -> dict[str, object]:
    result = snapshot.query.neighborhood(
        center,
        depth=depth,
        filters=NeighborhoodFilter(
            graph_iris=frozenset(graph_iri or ()),
            predicates=frozenset(predicate or ()),
            rdf_types=frozenset(rdf_type or ()),
        ),
        limits=NeighborhoodLimits(
            max_depth=3,
            max_nodes=max_nodes,
            max_edges=max_edges,
        ),
    )
    return result.to_dict()


@router.get("/graph/stats", response_model=DatasetStatsModel, tags=["graph"])
def graph_stats(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    return snapshot.query.stats(snapshot.context.modules).to_dict()

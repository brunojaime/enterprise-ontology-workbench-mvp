"""Validation, impact, SPARQL and competency-question endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from ontology_core import ReadOnlySparqlService, SparqlLimits

from enterprise_ontology_api.dependencies import runtime_manager, runtime_snapshot
from enterprise_ontology_api.errors import ApiProblem, error_responses
from enterprise_ontology_api.models import (
    CompetencyQuestionPageModel,
    CompetencyResultModel,
    CompetencyRunRequest,
    ImpactModel,
    SparqlRequest,
    SparqlResultModel,
    ValidationReportModel,
)
from enterprise_ontology_api.runtime import RuntimeManager, RuntimeSnapshot

router = APIRouter(prefix="/api", tags=["semantic"])


@router.post(
    "/validation/run",
    response_model=ValidationReportModel,
    responses=error_responses(422, 500),
)
def run_validation(
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
) -> dict[str, object]:
    report = manager.validate_current()
    return report.to_dict()


@router.get("/validation/latest", response_model=ValidationReportModel)
def latest_validation(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    return snapshot.validation_report.to_dict()


@router.get("/impact", response_model=ImpactModel, responses=error_responses(422))
def impact(
    iri: Annotated[str, Query(min_length=1)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    return snapshot.impact.analyze(iri).to_dict()


@router.post(
    "/sparql/query",
    response_model=SparqlResultModel,
    responses=error_responses(422),
)
def sparql_query(
    request: SparqlRequest,
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    service = ReadOnlySparqlService(
        snapshot.dataset,
        snapshot.store.prefixes,
        limits=SparqlLimits(
            timeout_seconds=request.timeout_seconds,
            max_results=request.max_results,
            max_query_bytes=65536,
        ),
    )
    return service.execute(request.query).to_dict()


@router.get(
    "/competency_questions",
    response_model=CompetencyQuestionPageModel,
    responses=error_responses(422),
)
def list_competency_questions(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    module: str | None = None,
) -> dict[str, object]:
    questions = tuple(
        question
        for question in snapshot.questions.list()
        if module is None
        or question.module == module
        or question.module.endswith(f"/module/{module}")
    )
    selected = questions[offset : offset + limit]
    return {
        "items": [question.to_dict() for question in selected],
        "total": len(questions),
        "offset": offset,
        "limit": limit,
        "has_next": offset + len(selected) < len(questions),
    }


@router.post(
    "/competency_questions/run",
    response_model=list[CompetencyResultModel],
    responses=error_responses(404, 422),
)
def run_competency_questions(
    request: CompetencyRunRequest,
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> list[dict[str, object]]:
    if request.iri is None:
        return [result.to_dict() for result in snapshot.competency.execute_all()]
    question = snapshot.questions.get(request.iri)
    if question is None:
        raise ApiProblem(
            404,
            "competency.not_found",
            "The requested competency question does not exist.",
            details={"iri": request.iri},
        )
    return [snapshot.competency.execute(question).to_dict()]

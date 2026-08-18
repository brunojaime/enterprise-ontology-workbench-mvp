"""Uniform public error contract and exception translation."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from ontology_core import (
    AuthoringError,
    CompetencyQuestionError,
    ContextBudgetError,
    GitWorkspaceError,
    RdfLoadError,
    SparqlQueryError,
)
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any]


class ApiProblem(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = ApiError(code=code, message=message, details=details or {})


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        status: {"model": ApiError, "description": "Structured API error"}
        for status in status_codes
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def handle_problem(_request: Request, error: ApiProblem) -> JSONResponse:
        return JSONResponse(error.error.model_dump(mode="json"), status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        payload = ApiError(
            code="request.invalid",
            message="Request parameters or body are invalid.",
            details={"errors": jsonable_encoder(error.errors())},
        )
        return JSONResponse(payload.model_dump(mode="json"), status_code=422)

    @app.exception_handler(RdfLoadError)
    async def handle_rdf_load(_request: Request, error: RdfLoadError) -> JSONResponse:
        payload = ApiError(
            code=error.rule_id,
            message="The RDF repository could not be loaded.",
            details={"path": str(error.path), "reason": error.detail},
        )
        return JSONResponse(payload.model_dump(mode="json"), status_code=422)

    @app.exception_handler(SparqlQueryError)
    async def handle_sparql(_request: Request, error: SparqlQueryError) -> JSONResponse:
        payload = ApiError(code=error.code, message=str(error), details={})
        return JSONResponse(payload.model_dump(mode="json"), status_code=422)

    @app.exception_handler(CompetencyQuestionError)
    async def handle_question(_request: Request, error: CompetencyQuestionError) -> JSONResponse:
        payload = ApiError(
            code="competency.invalid",
            message=str(error),
            details={},
        )
        return JSONResponse(payload.model_dump(mode="json"), status_code=422)

    @app.exception_handler(ContextBudgetError)
    async def handle_context_budget(_request: Request, error: ContextBudgetError) -> JSONResponse:
        payload = ApiError(code="context.invalid_budget", message=str(error), details={})
        return JSONResponse(payload.model_dump(mode="json"), status_code=422)

    @app.exception_handler(ValueError)
    async def handle_value_error(_request: Request, error: ValueError) -> JSONResponse:
        payload = ApiError(code="request.invalid", message=str(error), details={})
        return JSONResponse(payload.model_dump(mode="json"), status_code=422)

    @app.exception_handler(AuthoringError)
    async def handle_authoring(_request: Request, error: AuthoringError) -> JSONResponse:
        payload = ApiError(code=error.code, message=str(error), details=error.details)
        return JSONResponse(payload.model_dump(mode="json"), status_code=422)

    @app.exception_handler(GitWorkspaceError)
    async def handle_git(_request: Request, error: GitWorkspaceError) -> JSONResponse:
        payload = ApiError(code=error.code, message=str(error), details=error.details)
        status = 409 if error.code.startswith("git.") else 422
        return JSONResponse(payload.model_dump(mode="json"), status_code=status)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = "request.not_found" if error.status_code == 404 else "request.http_error"
        payload = ApiError(code=code, message=str(error.detail), details={})
        return JSONResponse(payload.model_dump(mode="json"), status_code=error.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, _error: Exception) -> JSONResponse:
        payload = ApiError(
            code="internal.error",
            message="An unexpected server error occurred.",
            details={},
        )
        return JSONResponse(payload.model_dump(mode="json"), status_code=500)

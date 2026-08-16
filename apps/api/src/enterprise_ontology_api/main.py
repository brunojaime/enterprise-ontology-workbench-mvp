"""FastAPI adapter factory over the framework-independent semantic core."""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from enterprise_ontology_api.config import ApiSettings
from enterprise_ontology_api.errors import ApiError, install_error_handlers
from enterprise_ontology_api.models import HealthModel, OperationalMetricsModel, ReadinessModel
from enterprise_ontology_api.routers import agent, editing, resources, semantic, workspace
from enterprise_ontology_api.runtime import RepositoryRevision, RuntimeManager

REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
ACCESS_LOG = logging.getLogger("eow.api.access")


def create_app(
    settings: ApiSettings | None = None,
    *,
    revision_provider: Callable[[], RepositoryRevision] | None = None,
) -> FastAPI:
    """Create the HTTP adapter without embedding semantic domain logic."""
    active_settings = settings or ApiSettings.from_environment()
    manager = RuntimeManager(active_settings, revision_provider=revision_provider)
    app = FastAPI(
        title="Enterprise Ontology Workbench API",
        version="0.1.0",
        description=(
            "Stable API over the canonical RDF/Git workspace, including controlled proposal "
            "authoring, semantic review and the synchronized canonical agent contract."
        ),
    )
    app.state.runtime = manager
    install_error_handlers(app)

    @app.middleware("http")
    async def structured_access_log(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - normalize unexpected adapter failures
            payload = ApiError(
                code="internal.error",
                message="An unexpected server error occurred.",
                details={},
            )
            response = JSONResponse(payload.model_dump(mode="json"), status_code=500)
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        operation = getattr(route, "name", None) or "unmatched"
        status_code = response.status_code
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        if operation not in {"health", "readiness", "operational_metrics"}:
            manager.record_query(duration_ms, failed=status_code >= 400)
        ACCESS_LOG.log(
            logging.ERROR if status_code >= 500 else logging.INFO,
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "semantic_operation": operation,
            },
        )
        return response

    app.include_router(workspace.router)
    app.include_router(resources.router)
    app.include_router(semantic.router)
    app.include_router(editing.router)
    app.include_router(agent.router)

    @app.get("/health", tags=["operations"], response_model=HealthModel)
    def health() -> dict[str, str]:
        """Liveness only: the ASGI process can answer HTTP."""

        return {"status": "ok"}

    @app.get(
        "/ready",
        tags=["operations"],
        response_model=ReadinessModel,
        responses={503: {"model": ReadinessModel, "description": "Runtime is not ready"}},
    )
    def readiness() -> dict[str, object] | JSONResponse:
        """Verify the published dataset snapshot and its canonical Git worktree."""

        probe = manager.probe_readiness()
        dataset_ready = probe.quads > 0 and probe.conforms
        worktree_ready = probe.worktree_ready
        checks = {
            "api": {"status": "pass", "detail": "HTTP adapter is running."},
            "dataset": {
                "status": "pass" if dataset_ready else "fail",
                "detail": probe.dataset_detail,
            },
            "worktree": {
                "status": "pass" if worktree_ready else "fail",
                "detail": probe.worktree_detail,
            },
        }
        active_snapshot = probe.snapshot or manager.current()
        payload: dict[str, object] = {
            "status": "ready" if dataset_ready and worktree_ready else "not_ready",
            "checks": checks,
            "generation": active_snapshot.generation,
            "loaded_at": active_snapshot.loaded_at,
        }
        if payload["status"] == "not_ready":
            return JSONResponse(payload, status_code=503)
        return payload

    @app.get("/metrics", tags=["operations"], response_model=OperationalMetricsModel)
    def operational_metrics() -> dict[str, dict[str, int | float | None]]:
        """Expose bounded process-local load, validation and query metrics."""

        return manager.metrics()

    return app


app = create_app()

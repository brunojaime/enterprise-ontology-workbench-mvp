"""FastAPI-only access to the atomic semantic runtime."""

from fastapi import Request

from enterprise_ontology_api.runtime import RuntimeManager, RuntimeSnapshot


def runtime_manager(request: Request) -> RuntimeManager:
    manager = request.app.state.runtime
    if not isinstance(manager, RuntimeManager):
        raise RuntimeError("application runtime is not configured")
    return manager


def runtime_snapshot(request: Request) -> RuntimeSnapshot:
    return runtime_manager(request).snapshot()

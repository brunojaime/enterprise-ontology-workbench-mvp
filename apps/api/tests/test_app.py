from __future__ import annotations

import io
import json
import logging
from pathlib import Path

from enterprise_ontology_api.config import ApiSettings
from enterprise_ontology_api.logging import JsonFormatter
from enterprise_ontology_api.main import ACCESS_LOG, app, create_app
from enterprise_ontology_api.runtime import RepositoryRevision
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[3]


def _settings(root: Path) -> ApiSettings:
    return ApiSettings(
        repository_root=root,
        knowledge_root=root / "knowledge",
        namespace_config=root / "config/namespace.yaml",
        write_enabled=False,
    )


def test_health_endpoint_is_part_of_the_api_contract() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/health"]["get"]

    assert operation["tags"] == ["operations"]
    assert schema["paths"]["/metrics"]["get"]["tags"] == ["operations"]
    assert schema["paths"]["/metrics"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/OperationalMetricsModel"}


def test_readiness_checks_api_dataset_and_git_worktree() -> None:
    ready_app = create_app(
        revision_provider=lambda: RepositoryRevision("main", "a" * 40, False, "fixture")
    )
    with TestClient(ready_app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["api"]["status"] == "pass"
    assert payload["checks"]["dataset"]["status"] == "pass"
    assert payload["checks"]["worktree"]["status"] == "pass"
    assert payload["generation"] >= 1
    assert ready_app.openapi()["paths"]["/ready"]["get"]["responses"]["503"]


def test_readiness_reprobes_git_instead_of_trusting_the_cached_snapshot() -> None:
    revision = [RepositoryRevision("main", "a" * 40, False, "fixture")]
    local_app = create_app(_settings(ROOT), revision_provider=lambda: revision[0])
    with TestClient(local_app) as client:
        assert client.get("/ready").status_code == 200
        revision[0] = RepositoryRevision(None, None, False, "fixture")
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["worktree"]["status"] == "fail"


def test_readiness_publishes_a_fresh_snapshot_when_the_revision_changes() -> None:
    revision = [RepositoryRevision("main", "a" * 40, False, "first")]
    local_app = create_app(_settings(ROOT), revision_provider=lambda: revision[0])
    with TestClient(local_app) as client:
        first = client.get("/ready")
        revision[0] = RepositoryRevision("proposal/readiness", "b" * 40, True, "second")
        second = client.get("/ready")
        workspace = client.get("/api/workspace/status")

    assert first.status_code == second.status_code == workspace.status_code == 200
    assert second.json()["generation"] == first.json()["generation"] + 1
    assert workspace.json()["revision"] == {
        "branch": "proposal/readiness",
        "commit": "b" * 40,
        "dirty": True,
    }


def test_readiness_fails_closed_when_the_probe_raises() -> None:
    calls = 0

    def revision_provider() -> RepositoryRevision:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("private checkout detail")
        return RepositoryRevision("main", "a" * 40, False, "fixture")

    local_app = create_app(_settings(ROOT), revision_provider=revision_provider)
    with TestClient(local_app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert "private checkout detail" not in response.text
    assert response.json()["status"] == "not_ready"


def test_access_log_is_json_and_correlates_semantic_operation() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    previous_level = ACCESS_LOG.level
    ACCESS_LOG.setLevel(logging.INFO)
    ACCESS_LOG.addHandler(handler)
    try:
        with TestClient(app) as client:
            response = client.get("/api/workspace", headers={"X-Request-ID": "test-request-42"})
    finally:
        ACCESS_LOG.removeHandler(handler)
        ACCESS_LOG.setLevel(previous_level)

    assert response.headers["X-Request-ID"] == "test-request-42"
    record = json.loads(stream.getvalue().splitlines()[-1])
    assert record == {
        **record,
        "event": "http_request",
        "level": "info",
        "logger": "eow.api.access",
        "method": "GET",
        "path": "/api/workspace",
        "request_id": "test-request-42",
        "semantic_operation": "get_workspace",
        "status_code": 200,
    }
    assert isinstance(record["duration_ms"], float)


def test_client_error_keeps_the_correlated_access_log() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    previous_level = ACCESS_LOG.level
    ACCESS_LOG.setLevel(logging.INFO)
    ACCESS_LOG.addHandler(handler)
    try:
        with TestClient(app) as client:
            response = client.get("/missing", headers={"X-Request-ID": "missing-request-4"})
    finally:
        ACCESS_LOG.removeHandler(handler)
        ACCESS_LOG.setLevel(previous_level)

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "missing-request-4"
    assert len(records) == 1
    assert records[0]["request_id"] == "missing-request-4"
    assert records[0]["status_code"] == 404
    assert records[0]["semantic_operation"] == "unmatched"


def test_unexpected_error_keeps_one_sanitized_correlated_access_log() -> None:
    local_app = create_app(
        _settings(ROOT),
        revision_provider=lambda: RepositoryRevision("main", "a" * 40, False, "fixture"),
    )

    @local_app.get("/test/unexpected", name="unexpected_fixture")
    def unexpected_fixture() -> None:
        raise RuntimeError("sensitive internal detail")

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    previous_level = ACCESS_LOG.level
    ACCESS_LOG.setLevel(logging.INFO)
    ACCESS_LOG.addHandler(handler)
    try:
        with TestClient(local_app, raise_server_exceptions=False) as client:
            response = client.get(
                "/test/unexpected", headers={"X-Request-ID": "unexpected-request-7"}
            )
    finally:
        ACCESS_LOG.removeHandler(handler)
        ACCESS_LOG.setLevel(previous_level)

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "unexpected-request-7"
    assert response.json() == {
        "code": "internal.error",
        "message": "An unexpected server error occurred.",
        "details": {},
    }
    assert "sensitive internal detail" not in response.text
    assert len(records) == 1
    assert records[0] == {
        **records[0],
        "event": "http_request",
        "method": "GET",
        "path": "/test/unexpected",
        "request_id": "unexpected-request-7",
        "semantic_operation": "unexpected_fixture",
        "status_code": 500,
    }


def test_metrics_cover_load_validation_and_queries() -> None:
    local_app = create_app(
        _settings(ROOT),
        revision_provider=lambda: RepositoryRevision("main", "a" * 40, False, "fixture"),
    )
    with TestClient(local_app) as client:
        before = client.get("/metrics").json()
        assert client.get("/api/workspace").status_code == 200
        assert client.get("/missing").status_code == 404
        after = client.get("/metrics").json()

    assert before["load"]["count"] >= 1
    assert before["validation"]["count"] >= 1
    assert after["query"]["count"] == before["query"]["count"] + 2
    assert after["query"]["failures"] == before["query"]["failures"] + 1
    for operation in ("load", "validation", "query"):
        assert after[operation]["total_duration_ms"] >= 0

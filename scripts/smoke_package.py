#!/usr/bin/env python3
"""Build and smoke-test the final internal Compose package."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any


def _provider(requested: str | None) -> tuple[str, ...]:
    candidates = (
        ((requested, "compose"),) if requested else (("docker", "compose"), ("podman", "compose"))
    )
    for candidate in candidates:
        executable = candidate[0]
        if executable and shutil.which(executable):
            check = subprocess.run((*candidate, "version"), check=False, capture_output=True)
            if check.returncode == 0:
                return candidate
    raise RuntimeError("Docker Compose or Podman Compose is required")


def _run(
    command: tuple[str, ...],
    *,
    root: Path,
    environment: dict[str, str],
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        env=environment,
        check=True,
        capture_output=capture,
        text=True,
        timeout=900,
    )


def _get_json(url: str, request_id: str | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url)
    if request_id:
        request.add_header("X-Request-ID", request_id)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def _wait_json(url: str, *, attempts: int = 60) -> dict[str, Any]:
    error: Exception | None = None
    for _ in range(attempts):
        try:
            return _get_json(url)
        except Exception as current:  # noqa: BLE001 - retry boundary for container startup
            error = current
            time.sleep(1)
    raise RuntimeError(f"service did not become ready: {url}: {error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--provider", choices=("docker", "podman"))
    parser.add_argument("--api-port", type=int, default=48000)
    parser.add_argument("--web-port", type=int, default=43000)
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args()
    root = arguments.repository.resolve(strict=True)
    provider = _provider(arguments.provider)
    project = "eow-package-smoke"
    compose = (
        *provider,
        "--project-name",
        project,
        "--file",
        "compose.internal.yaml",
    )
    environment = {
        **os.environ,
        "EOW_REPOSITORY_PATH": root.as_posix(),
        "EOW_REPOSITORY_READ_ONLY": "true",
        "EOW_WRITE_ENABLED": "false",
        "EOW_BIND_ADDRESS": "127.0.0.1",
        "API_PORT": str(arguments.api_port),
        "WEB_PORT": str(arguments.web_port),
        "EOW_WEB_ORIGIN": f"http://127.0.0.1:{arguments.web_port}",
        "EOW_IMAGE_TAG": "smoke",
    }
    request_id = "eow-package-smoke"
    try:
        _run((*compose, "config", "--quiet"), root=root, environment=environment)
        _run((*compose, "up", "--build", "--detach"), root=root, environment=environment)
        health = _wait_json(f"http://127.0.0.1:{arguments.api_port}/health")
        ready = _wait_json(f"http://127.0.0.1:{arguments.api_port}/ready")
        workspace = _wait_json(f"http://127.0.0.1:{arguments.web_port}/api/workspace")
        _get_json(f"http://127.0.0.1:{arguments.api_port}/api/workspace", request_id)
        metrics = _get_json(f"http://127.0.0.1:{arguments.api_port}/metrics")

        uid = _run(
            (*compose, "exec", "-T", "api", "id", "-u"),
            root=root,
            environment=environment,
            capture=True,
        ).stdout.strip()
        cli = _run(
            (
                *compose,
                "exec",
                "-T",
                "api",
                "ontology",
                "--repository",
                "/repository",
                "validate",
                "--json",
            ),
            root=root,
            environment=environment,
            capture=True,
        )
        mcp = _run(
            (*compose, "exec", "-T", "api", "ontology-mcp-smoke", "--repository", "/repository"),
            root=root,
            environment=environment,
            capture=True,
        )
        logs = _run(
            (*compose, "logs", "--no-color", "--no-log-prefix", "api"),
            root=root,
            environment=environment,
            capture=True,
        ).stdout.splitlines()
        parsed_logs = []
        for line in logs:
            try:
                parsed_logs.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise RuntimeError(f"API emitted a non-JSON log line: {line}") from error
        matching = [item for item in parsed_logs if item.get("request_id") == request_id]

        cli_payload = json.loads(cli.stdout)
        mcp_payload = json.loads(mcp.stdout)
        if uid == "0":
            raise RuntimeError("packaged API is running as root")
        if health.get("status") != "ok" or ready.get("status") != "ready":
            raise RuntimeError("API health or readiness failed")
        if not cli_payload.get("conforms") or mcp_payload.get("status") != "passed":
            raise RuntimeError("packaged CLI or MCP smoke failed")
        if not matching or matching[-1].get("semantic_operation") != "get_workspace":
            raise RuntimeError("request ID and semantic operation were absent from JSON logs")
        if any(metrics[name]["count"] < 1 for name in ("load", "validation", "query")):
            raise RuntimeError("load, validation and query metrics were not populated")
        if workspace.get("runtime", {}).get("ready") is not True:
            raise RuntimeError("web proxy did not reach the packaged API")
        print(
            json.dumps(
                {
                    "api": ready,
                    "api_uid": int(uid),
                    "cli": {"conforms": cli_payload["conforms"]},
                    "logs": {"request_id": request_id, "semantic_operation": "get_workspace"},
                    "metrics": metrics,
                    "mcp": mcp_payload,
                    "status": "passed",
                    "web": {"api_proxy": "passed"},
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except Exception:
        subprocess.run(
            (*compose, "logs", "--no-color"),
            cwd=root,
            env=environment,
            check=False,
            timeout=30,
        )
        raise
    finally:
        if not arguments.keep:
            subprocess.run(
                (*compose, "down", "--remove-orphans"),
                cwd=root,
                env=environment,
                check=False,
                timeout=120,
            )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
cd "$REPOSITORY_ROOT"

bootstrap_workspace
uv run ruff check .
uv run ruff format --check .
uv run mypy apps/api/src packages/ontology_core/src packages/ontology_cli/src packages/ontology_mcp/src
uv run python scripts/validate_rdf.py
uv run python scripts/generate_agent_files.py --check
uv run python scripts/evaluate_agent_tasks.py
uv run python scripts/check_mcp_clients.py
uv run python scripts/generate_api_client.py --check
run_pnpm lint
run_pnpm check

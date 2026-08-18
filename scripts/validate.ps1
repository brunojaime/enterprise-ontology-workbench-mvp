. "$PSScriptRoot/lib.ps1"
Set-Location $script:RepositoryRoot

Initialize-Workspace
& uv run ruff check .
Assert-LastExitCode
& uv run ruff format --check .
Assert-LastExitCode
& uv run mypy apps/api/src packages/ontology_core/src packages/ontology_cli/src packages/ontology_mcp/src
Assert-LastExitCode
& uv run python scripts/validate_rdf.py
Assert-LastExitCode
& uv run python scripts/generate_agent_files.py --check
Assert-LastExitCode
& uv run python scripts/evaluate_agent_tasks.py
Assert-LastExitCode
& uv run python scripts/check_mcp_clients.py
Assert-LastExitCode
& uv run python scripts/generate_api_client.py --check
Assert-LastExitCode
Invoke-Pnpm lint
Invoke-Pnpm check

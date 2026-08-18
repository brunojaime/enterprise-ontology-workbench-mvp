$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "lib.ps1")
Set-Location $RepositoryRoot

Initialize-Workspace
uv run python scripts/run_local_gate.py @args

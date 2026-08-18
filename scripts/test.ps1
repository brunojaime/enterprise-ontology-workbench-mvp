. "$PSScriptRoot/lib.ps1"
Set-Location $script:RepositoryRoot

Initialize-Workspace
& uv run pytest
Assert-LastExitCode
Invoke-Pnpm test

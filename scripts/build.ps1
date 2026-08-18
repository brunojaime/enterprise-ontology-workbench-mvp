. "$PSScriptRoot/lib.ps1"
Set-Location $script:RepositoryRoot

Initialize-Workspace
& uv build --all-packages
Assert-LastExitCode
Invoke-Pnpm build

. "$PSScriptRoot/lib.ps1"
Set-Location $script:RepositoryRoot

Invoke-Compose up --build

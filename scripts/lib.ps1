$ErrorActionPreference = "Stop"
$script:RepositoryRoot = Split-Path -Parent $PSScriptRoot
$script:PnpmVersion = "9.15.5"

function Assert-LastExitCode {
    if ($LASTEXITCODE -ne 0) {
        throw "External command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-Pnpm {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        & pnpm @Arguments
    }
    elseif (Get-Command corepack -ErrorAction SilentlyContinue) {
        & corepack pnpm @Arguments
    }
    else {
        & npx --yes "pnpm@$script:PnpmVersion" @Arguments
    }
    Assert-LastExitCode
}

function Initialize-Workspace {
    & uv sync --frozen
    Assert-LastExitCode
    Invoke-Pnpm install --frozen-lockfile
}

function Test-ComposeProvider {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        return $false
    }

    & $Name compose version *> $null
    return $LASTEXITCODE -eq 0
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    if (Test-ComposeProvider -Name "docker") {
        & docker compose @Arguments
        Assert-LastExitCode
        return
    }

    if (Test-ComposeProvider -Name "podman") {
        & podman compose @Arguments
        Assert-LastExitCode
        return
    }

    throw "Docker Compose or Podman Compose is required."
}

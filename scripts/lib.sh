#!/usr/bin/env bash

set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PNPM_VERSION="9.15.5"

run_pnpm() {
  if command -v pnpm >/dev/null 2>&1; then
    pnpm "$@"
  elif command -v corepack >/dev/null 2>&1; then
    corepack pnpm "$@"
  else
    npx --yes "pnpm@${PNPM_VERSION}" "$@"
  fi
}

bootstrap_workspace() {
  uv sync --frozen
  run_pnpm install --frozen-lockfile
}

run_compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
    podman compose "$@"
  else
    echo "Docker Compose or Podman Compose is required." >&2
    return 1
  fi
}

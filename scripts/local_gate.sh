#!/usr/bin/env bash

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
cd "$REPOSITORY_ROOT"

bootstrap_workspace
uv run python scripts/run_local_gate.py "$@"

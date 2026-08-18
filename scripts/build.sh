#!/usr/bin/env bash

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
cd "$REPOSITORY_ROOT"

bootstrap_workspace
uv build --all-packages
run_pnpm build

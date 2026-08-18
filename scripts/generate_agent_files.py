#!/usr/bin/env python3
"""Generate or verify agent-specific adapters from agent_contract/."""

from __future__ import annotations

import argparse
from pathlib import Path

from ontology_core import AgentContractError, AgentContractService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    try:
        status = AgentContractService(repository_root).sync(check=arguments.check)
    except AgentContractError as error:
        parser.error(str(error))
    action = "verified" if arguments.check else "generated"
    print(f"agent adapters {action}: {len(status.generated)} files ({status.digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

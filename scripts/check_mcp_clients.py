#!/usr/bin/env python3
"""Resolve project client configs exactly and negotiate both stdio servers."""

from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_NAME = "enterprise-ontology-workbench"


async def _probe(parameters: StdioServerParameters) -> dict[str, object]:
    async with stdio_client(parameters) as (read, write):  # noqa: SIM117
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            prompts = await session.list_prompts()
            if initialized.server_info.name != SERVER_NAME:
                raise RuntimeError("project MCP configuration launched an unexpected server")
            if len(tools.tools) != 9 or len(prompts.prompts) != 3:
                raise RuntimeError("project MCP configuration exposed an incomplete contract")
            return {
                "server": initialized.server_info.name,
                "status": "passed",
                "tools": len(tools.tools),
                "prompts": len(prompts.prompts),
            }


def _codex_parameters(repository: Path) -> StdioServerParameters:
    config_path = repository / ".codex/config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    server = config["mcp_servers"]["enterprise_ontology_workbench"]
    # Codex resolves an MCP process cwd from the project/session root. Other
    # relative config file paths use the declaring .codex/ directory.
    cwd = (repository / server["cwd"]).resolve(strict=True)
    if cwd != repository:
        raise RuntimeError("Codex project MCP cwd does not resolve to the repository root")
    if not (repository / ".agents/skills").is_dir():
        raise RuntimeError("Codex project skills are unavailable")
    return StdioServerParameters(
        command=server["command"],
        args=list(server["args"]),
        cwd=cwd,
    )


def _claude_parameters(repository: Path) -> StdioServerParameters:
    config = json.loads((repository / ".mcp.json").read_text(encoding="utf-8"))
    server = config["mcpServers"][SERVER_NAME]
    marker = "${CLAUDE_PROJECT_DIR:-.}"
    arguments = [value.replace(marker, repository.as_posix()) for value in server["args"]]
    if any(marker in value for value in arguments):
        raise RuntimeError("Claude project directory variable was not resolved")
    settings = json.loads((repository / ".claude/settings.json").read_text(encoding="utf-8"))
    if SERVER_NAME not in settings["enabledMcpjsonServers"]:
        raise RuntimeError("Claude project MCP server is not enabled")
    if not (repository / ".claude/skills").is_dir():
        raise RuntimeError("Claude project skills are unavailable")
    return StdioServerParameters(
        command=server["command"],
        args=arguments,
        cwd=repository,
    )


async def _main() -> None:
    repository = Path(__file__).resolve().parents[1]
    claude = _claude_parameters(repository)
    codex = _codex_parameters(repository)
    if not (repository / ".git").exists():
        result = {
            "claude_code": {"reason": "git_worktree_required", "status": "not_executable"},
            "codex": {"reason": "git_worktree_required", "status": "not_executable"},
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return
    results = {
        "claude_code": await _probe(claude),
        "codex": await _probe(codex),
    }
    print(json.dumps(results, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(_main())

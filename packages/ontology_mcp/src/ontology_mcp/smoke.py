"""Official-client smoke probe for the installed MCP package."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextResourceContents


async def probe(repository: Path) -> dict[str, object]:
    root = repository.resolve(strict=True)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "ontology_mcp.server",
            "--repository",
            root.as_posix(),
            "--audit-log",
            ".eow-mcp-smoke-audit.jsonl",
        ],
        cwd=root,
        env=dict(os.environ),
    )
    async with stdio_client(parameters) as (read, write):  # noqa: SIM117
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            prompts = await session.list_prompts()
            modules = await session.call_tool("ontology_list_modules", {"request": {}})
            validation = await session.call_tool("ontology_validate", {"request": {}})
            manifest = await session.read_resource("ontology://manifest/modules")

    if initialized.server_info.name != "enterprise-ontology-workbench":
        raise RuntimeError("unexpected MCP server identity")
    if modules.is_error or validation.is_error:
        raise RuntimeError("MCP read tools failed")
    validation_payload = validation.structured_content
    if not isinstance(validation_payload, dict) or validation_payload.get("conforms") is not True:
        raise RuntimeError("MCP validation did not conform")
    if not manifest.contents or not isinstance(manifest.contents[0], TextResourceContents):
        raise RuntimeError("MCP module resource was unavailable")
    module_payload = json.loads(manifest.contents[0].text)
    if len(module_payload.get("items", [])) < 1:
        raise RuntimeError("MCP module resource was empty")
    return {
        "status": "passed",
        "server": initialized.server_info.name,
        "tools": len(tools.tools),
        "resources": len(resources.resources),
        "resource_templates": len(templates.resource_templates),
        "prompts": len(prompts.prompts),
        "modules": len(module_payload["items"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="ontology-mcp-smoke")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    payload = asyncio.run(probe(arguments.repository))
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

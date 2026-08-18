from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import quote

import ontology_mcp
import ontology_mcp.audit as audit_module
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextResourceContents
from ontology_core import AgentContractService
from ontology_mcp import McpSettings, create_server
from ontology_mcp.audit import AuditWriteError, WriteAuditLog
from ontology_mcp.models import DeprecateInput, RelationInput, SearchInput, TermInput
from ontology_mcp.runtime import McpRuntimeError, OntologyMcpRuntime
from ontology_mcp.smoke import probe
from rdflib import Dataset, Literal, URIRef

ROOT = Path(__file__).parents[3]
BASE = "https://knowledge.example.com/"


def _audit_process(
    repository_text: str,
    audit_text: str,
    prefix: str,
    count: int,
    fail_first: bool,
) -> None:
    repository = Path(repository_text)
    runtime = OntologyMcpRuntime(
        McpSettings.from_repository(
            repository,
            audit_log=Path(audit_text),
        )
    )
    audit = runtime.audit
    real_fsync = audit_module.os.fsync
    failed = False

    if fail_first:

        def fail_once(descriptor: int) -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise OSError("synthetic child fsync failure")
            real_fsync(descriptor)

        audit_module.os.fsync = fail_once
        try:
            audit.record(
                agent=prefix,
                tool="ontology_deprecate_term",
                files=(),
                result="success",
                invocation_id=f"{prefix}-failed",
            )
        except AuditWriteError:
            pass
        finally:
            audit_module.os.fsync = real_fsync

    for index in range(count):
        audit.record(
            agent=prefix,
            tool="ontology_deprecate_term",
            files=(f"knowledge/{prefix}-{index}.ttl",),
            result="success",
            invocation_id=f"{prefix}-{index}",
        )


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> Path:
    for directory in ("knowledge", "config", "agent_contract"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copy2(ROOT / ".gitignore", tmp_path / ".gitignore")
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "MCP Integration")
    _git(tmp_path, "config", "user.email", "mcp@example.test")
    _git(tmp_path, "add", "knowledge", "config", "agent_contract", ".gitignore")
    _git(tmp_path, "commit", "--quiet", "-m", "chore: seed MCP fixture")
    _git(tmp_path, "switch", "--quiet", "--create", "proposal/mcp-integration")
    return tmp_path


def _knowledge_file_states(repository: Path) -> dict[str, tuple[bytes, int, int]]:
    root = repository / "knowledge"
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mode & 0o7777,
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _structured(result: CallToolResult) -> dict[str, object]:
    value = result.structured_content
    assert isinstance(value, dict)
    return value


def test_package_exposes_version() -> None:
    assert ontology_mcp.__version__ == "0.1.0"


def test_installed_package_smoke_uses_the_official_client(tmp_path: Path) -> None:
    result = asyncio.run(probe(_repository(tmp_path)))

    assert result == {
        "status": "passed",
        "server": "enterprise-ontology-workbench",
        "tools": 9,
        "resources": 4,
        "resource_templates": 1,
        "prompts": 3,
        "modules": 5,
    }


def test_project_configs_discover_the_local_stdio_server() -> None:
    codex = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))
    codex_server = codex["mcp_servers"]["enterprise_ontology_workbench"]
    assert codex_server["command"] == "uv"
    assert codex_server["args"] == [
        "run",
        "ontology-mcp",
        "--repository",
        ".",
        "--write-enabled",
    ]
    assert codex_server["cwd"] == "."
    effective_cwd = (ROOT / codex_server["cwd"]).resolve(strict=True)
    assert effective_cwd == ROOT
    assert (effective_cwd / codex_server["args"][3]).resolve(strict=True) == ROOT
    assert codex_server["default_tools_approval_mode"] == "writes"

    claude = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    claude_server = claude["mcpServers"]["enterprise-ontology-workbench"]
    assert claude_server["type"] == "stdio"
    assert claude_server["command"] == "uv"
    assert "${CLAUDE_PROJECT_DIR:-.}" in claude_server["args"]
    settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["enabledMcpjsonServers"] == ["enterprise-ontology-workbench"]

    completed = subprocess.run(
        (sys.executable, "scripts/check_mcp_clients.py"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    actual = json.loads(completed.stdout)
    if (ROOT / ".git").exists():
        assert actual == {
            "claude_code": {
                "prompts": 3,
                "server": "enterprise-ontology-workbench",
                "status": "passed",
                "tools": 9,
            },
            "codex": {
                "prompts": 3,
                "server": "enterprise-ontology-workbench",
                "status": "passed",
                "tools": 9,
            },
        }
    else:
        assert actual == {
            "claude_code": {
                "reason": "git_worktree_required",
                "status": "not_executable",
            },
            "codex": {
                "reason": "git_worktree_required",
                "status": "not_executable",
            },
        }


def test_settings_reject_audit_escape_and_symlink(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository")
    with pytest.raises(ValueError, match="inside the repository"):
        McpSettings.from_repository(repository, audit_log=tmp_path / "outside.jsonl")
    with pytest.raises(ValueError, match="inside the repository"):
        McpSettings.from_repository(repository, audit_log=Path("../outside.jsonl"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (repository / "unsafe").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        McpSettings.from_repository(repository, audit_log=Path("unsafe/audit.jsonl"))


def test_tool_schemas_are_strict_and_no_destructive_tools_exist(tmp_path: Path) -> None:
    server = create_server(McpSettings.from_repository(_repository(tmp_path)))

    async def inspect() -> None:
        tools = await server.list_tools()
        names = {tool.name for tool in tools}
        assert names == {
            "ontology_list_modules",
            "ontology_search",
            "ontology_describe",
            "ontology_get_context",
            "ontology_validate",
            "ontology_diff",
            "ontology_propose_term",
            "ontology_propose_relation",
            "ontology_deprecate_term",
        }
        assert all(tool.input_schema["additionalProperties"] is False for tool in tools)
        for tool in tools:
            request_ref = tool.input_schema["properties"]["request"]["$ref"]
            definition = request_ref.rsplit("/", 1)[-1]
            assert tool.input_schema["$defs"][definition]["additionalProperties"] is False
        assert all("delete" not in name and "merge" not in name for name in names)

    asyncio.run(inspect())


def test_real_stdio_client_executes_every_tool_resource_and_prompt(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    audit = repository / ".eow/audit/mcp-test.jsonl"
    contract = AgentContractService(repository)
    canonical_prompts = {
        document.identifier: document.content.strip() for document in contract.prompts
    }

    async def exercise() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "ontology_mcp.server",
                "--repository",
                repository.as_posix(),
                "--audit-log",
                audit.relative_to(repository).as_posix(),
                "--write-enabled",
            ],
            cwd=repository,
        )
        async with stdio_client(parameters) as (read, write):  # noqa: SIM117
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.server_info.name == "enterprise-ontology-workbench"
                assert initialized.instructions == contract.mcp_instructions.content.strip()

                tools = await session.list_tools()
                assert len(tools.tools) == 9
                resources = await session.list_resources()
                assert len(resources.resources) == 4
                templates = await session.list_resource_templates()
                assert len(templates.resource_templates) == 1
                prompts = await session.list_prompts()
                assert len(prompts.prompts) == 3

                modules = await session.call_tool("ontology_list_modules", {"request": {}})
                assert not modules.is_error
                assert len(_structured(modules)["items"]) == 5  # type: ignore[arg-type]

                invalid = await session.call_tool(
                    "ontology_search",
                    {"request": {"text": "aplicación", "unknown": True}},
                )
                assert invalid.is_error

                search = await session.call_tool(
                    "ontology_search",
                    {"request": {"text": "aplicación", "limit": 50, "offset": 0}},
                )
                assert not search.is_error
                assert _structured(search)["search_id"]

                description = await session.call_tool(
                    "ontology_describe",
                    {"request": {"iri": f"{BASE}ontology/software#Application"}},
                )
                assert not description.is_error
                assert _structured(description)["neighborhood"]

                context = await session.call_tool(
                    "ontology_get_context",
                    {"request": {"task": "Revisar la aplicación y su ownership"}},
                )
                assert not context.is_error
                assert _structured(context)["markdown"]

                validation = await session.call_tool("ontology_validate", {"request": {}})
                assert not validation.is_error
                assert _structured(validation)["conforms"] is True

                diff = await session.call_tool("ontology_diff", {"request": {"base": "main"}})
                assert not diff.is_error

                for uri in (
                    "ontology://governance/rules",
                    "ontology://manifest/modules",
                    "ontology://validation/current",
                    "ontology://competency/questions",
                ):
                    response = await session.read_resource(uri)
                    assert isinstance(response.contents[0], TextResourceContents)
                    assert json.loads(response.contents[0].text)
                encoded = quote(f"{BASE}ontology/software#Application", safe="")
                relevant = await session.read_resource(f"ontology://resource/{encoded}")
                assert isinstance(relevant.contents[0], TextResourceContents)
                assert json.loads(relevant.contents[0].text)["description"]

                prompt_arguments = {
                    "model_domain_concept": {
                        "task": "Modelar una capacidad",
                        "evidence": "Catálogo de arquitectura revisado",
                    },
                    "review_ontology_change": {"base": "main"},
                    "connect_repository_to_enterprise_knowledge": {
                        "repository": "inventario-software",
                        "business_question": "¿Qué unidad soporta la aplicación?",
                    },
                }
                for name, arguments in prompt_arguments.items():
                    rendered = await session.get_prompt(name, arguments=arguments)
                    assert rendered.messages
                    content = rendered.messages[0].content
                    assert hasattr(content, "text")
                    assert content.text == canonical_prompts[name].format(**arguments)

                individual_search = await session.call_tool(
                    "ontology_search",
                    {
                        "request": {
                            "text": "aplicación mcp temporal",
                            "limit": 50,
                            "offset": 0,
                        }
                    },
                )
                receipt = str(_structured(individual_search)["search_id"])
                proposed = await session.call_tool(
                    "ontology_propose_term",
                    {
                        "request": {
                            "agent": "integration-agent",
                            "iri": f"{BASE}id/software/application/mcp_fixture",
                            "module_id": "software",
                            "kind": "individual",
                            "preferred_label_es": "Aplicación MCP temporal",
                            "evidence": "Fixture local verificable para P09",
                            "author": "integration-agent",
                            "search_query": "aplicación mcp temporal",
                            "search_id": receipt,
                            "search_confirmed": True,
                            "class_iri": f"{BASE}ontology/software#Application",
                            "source_id": "mcp_fixture",
                        }
                    },
                )
                assert not proposed.is_error
                assert str(_structured(proposed)["path"]).startswith("knowledge/")

                relation = await session.call_tool(
                    "ontology_propose_relation",
                    {
                        "request": {
                            "agent": "integration-agent",
                            "subject": f"{BASE}id/software/application/mcp_fixture",
                            "predicate": f"{BASE}ontology/software#supportsOrganizationUnit",
                            "object_iri": f"{BASE}id/organization/unit/architecture",
                            "evidence": "Relación sintética revisada para P09",
                        }
                    },
                )
                assert not relation.is_error

                deprecated = await session.call_tool(
                    "ontology_deprecate_term",
                    {
                        "request": {
                            "agent": "integration-agent",
                            "iri": f"{BASE}ontology/software#Application",
                            "reason": "Deprecación sintética confinada al repositorio temporal",
                        }
                    },
                )
                assert not deprecated.is_error

    asyncio.run(exercise())
    entries = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [entry["tool"] for entry in entries] == [
        "ontology_propose_term",
        "ontology_propose_relation",
        "ontology_deprecate_term",
    ]
    assert all(entry["agent"] == "integration-agent" for entry in entries)
    assert all(entry["result"] == "success" for entry in entries)
    assert all(entry["files"] and entry["files"][0].startswith("knowledge/") for entry in entries)


def test_stdio_session_rejects_tampered_search_receipt_and_accepts_original(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    audit = repository / ".eow/audit/receipt-adversarial.jsonl"

    async def exercise() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "ontology_mcp.server",
                "--repository",
                repository.as_posix(),
                "--audit-log",
                audit.relative_to(repository).as_posix(),
                "--write-enabled",
            ],
            cwd=repository,
        )
        async with stdio_client(parameters) as (read, write):  # noqa: SIM117
            async with ClientSession(read, write) as session:
                await session.initialize()
                query = "capacidad MCP con receipt verificable"
                search = await session.call_tool(
                    "ontology_search",
                    {"request": {"text": query, "limit": 50, "offset": 0}},
                )
                authentic = str(_structured(search)["search_id"])
                tampered = authentic[:-1] + ("0" if authentic[-1] != "0" else "1")
                request = {
                    "agent": "receipt-adversarial",
                    "iri": f"{BASE}ontology/software#ReceiptVerifiedCapability",
                    "module_id": "software",
                    "kind": "class",
                    "preferred_label_es": "Capacidad MCP con receipt verificable",
                    "definition_es": "Clase temporal para verificar la firma del receipt en MCP.",
                    "evidence": "Prueba adversarial confinada a un repositorio temporal",
                    "author": "receipt-adversarial",
                    "search_query": query,
                    "search_confirmed": True,
                }
                rejected = await session.call_tool(
                    "ontology_propose_term",
                    {"request": {**request, "search_id": tampered}},
                )
                accepted = await session.call_tool(
                    "ontology_propose_term",
                    {"request": {**request, "search_id": authentic}},
                )

                assert rejected.is_error
                assert not accepted.is_error
                assert str(_structured(accepted)["path"]).endswith(
                    "knowledge/ontology/software/terms/ReceiptVerifiedCapability.ttl"
                )

    asyncio.run(exercise())
    entries = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert entries[0]["result"] == "rejected"
    assert entries[0]["code"] == "authoring.invalid_search_id"
    assert entries[-1]["result"] == "success"
    assert "code" not in entries[-1]
    assert all(entry["tool"] == "ontology_propose_term" for entry in entries)


def test_mcp_published_subject_relation_is_confined_to_a_proposal_graph(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    server = create_server(McpSettings.from_repository(repository, write_enabled=True))
    component = f"{BASE}id/software/component/mcp_graph_fixture"

    async def propose() -> dict[str, object]:
        search = await server.call_tool(
            "ontology_search",
            {"request": {"text": "componente mcp para graph de propuesta", "limit": 50}},
        )
        receipt = str(_structured(search)["search_id"])
        created = await server.call_tool(
            "ontology_propose_term",
            {
                "request": {
                    "agent": "mcp-graph-test",
                    "iri": component,
                    "module_id": "software",
                    "kind": "individual",
                    "preferred_label_es": "Componente MCP para graph de propuesta",
                    "evidence": "Fixture adversarial MCP de separación de estados",
                    "author": "mcp-graph-test",
                    "search_query": "componente mcp para graph de propuesta",
                    "search_id": receipt,
                    "search_confirmed": True,
                    "class_iri": f"{BASE}ontology/software#SoftwareComponent",
                    "source_id": "mcp_graph_fixture",
                }
            },
        )
        assert not created.is_error
        relation = await server.call_tool(
            "ontology_propose_relation",
            {
                "request": {
                    "agent": "mcp-graph-test",
                    "subject": f"{BASE}id/software/application/workbench",
                    "predicate": f"{BASE}ontology/software#isComposedOf",
                    "object_iri": component,
                    "evidence": "Fixture adversarial MCP de named graph propuesto",
                }
            },
        )
        assert not relation.is_error
        return _structured(relation)

    result = asyncio.run(propose())
    document = Dataset().parse(repository / str(result["path"]), format="trig")
    triple = (
        URIRef(f"{BASE}id/software/application/workbench"),
        URIRef(f"{BASE}ontology/software#isComposedOf"),
        URIRef(component),
    )
    published = URIRef(f"{BASE}graph/source/fixture_inventory")
    proposal = next(
        graph.identifier
        for graph in document.graphs()
        if str(graph.identifier).startswith(f"{BASE}graph/proposal/") and triple in graph
    )
    assert proposal == URIRef(f"{BASE}graph/proposal/mcp-integration/fixture_inventory")
    metadata = next(
        graph.identifier
        for graph in document.graphs()
        if (
            proposal,
            URIRef(f"{BASE}ontology/core#status"),
            Literal("proposed"),
        )
        in graph
    )
    assert triple not in document.graph(published)
    assert triple in document.graph(proposal)
    assert (
        proposal,
        URIRef(f"{BASE}ontology/core#status"),
        Literal("proposed"),
    ) in document.graph(metadata)


def test_write_tools_reject_main_without_touching_knowledge_or_git_state(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _git(repository, "switch", "--quiet", "main")
    settings = McpSettings.from_repository(repository, write_enabled=True)
    server = create_server(settings)
    before = _knowledge_file_states(repository)
    before_status = _git(repository, "status", "--porcelain=v1")

    async def reject_all() -> None:
        search = await server.call_tool(
            "ontology_search",
            {"request": {"text": "unidad bloqueada en main", "limit": 50, "offset": 0}},
        )
        receipt = str(_structured(search)["search_id"])
        requests = (
            (
                "ontology_propose_term",
                {
                    "agent": "main-adversary",
                    "iri": f"{BASE}id/organization/unit/main_blocked",
                    "module_id": "organization",
                    "kind": "individual",
                    "preferred_label_es": "Unidad bloqueada en main",
                    "evidence": "Fixture que no puede modificar main",
                    "author": "main-adversary",
                    "search_query": "unidad bloqueada en main",
                    "search_id": receipt,
                    "search_confirmed": True,
                    "class_iri": f"{BASE}ontology/organization#OrganizationUnit",
                    "source_id": "main_blocked",
                },
            ),
            (
                "ontology_propose_relation",
                {
                    "agent": "main-adversary",
                    "subject": f"{BASE}id/software/application/workbench",
                    "predicate": "http://purl.org/dc/terms/identifier",
                    "literal": "main-blocked",
                    "evidence": "Fixture que no puede modificar main",
                },
            ),
            (
                "ontology_deprecate_term",
                {
                    "agent": "main-adversary",
                    "iri": f"{BASE}ontology/software#Application",
                    "reason": "Fixture que no puede modificar main",
                },
            ),
        )
        for tool, request in requests:
            with pytest.raises(ToolError, match="prohibited on protected branch main"):
                await server.call_tool(tool, {"request": request})

    asyncio.run(reject_all())

    assert _knowledge_file_states(repository) == before
    assert _git(repository, "status", "--porcelain=v1") == before_status == ""
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["tool"] for entry in entries] == [
        "ontology_propose_term",
        "ontology_propose_relation",
        "ontology_deprecate_term",
    ]
    assert [entry["result"] for entry in entries] == ["rejected"] * 3
    assert [entry["code"] for entry in entries] == ["git.protected_branch"] * 3
    assert len({entry["invocation_id"] for entry in entries}) == 3


@pytest.mark.parametrize("mutation", ["branch", "head"])
def test_workspace_revision_change_during_staging_rejects_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/Application.ttl"
    before = _knowledge_file_states(repository)
    real_guard = runtime._require_workspace_revision
    calls = 0

    def mutate_before_second_guard(branch: str, head: str | None) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            if mutation == "branch":
                _git(repository, "switch", "--quiet", "main")
            else:
                _git(repository, "commit", "--allow-empty", "--quiet", "-m", "concurrent head")
        real_guard(branch, head)

    monkeypatch.setattr(runtime, "_require_workspace_revision", mutate_before_second_guard)
    with pytest.raises(McpRuntimeError, match="proposal branch or HEAD changed"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="workspace-race-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="La revisión Git real debe permanecer estable",
            )
        )

    assert target.read_bytes() == before["ontology/software/terms/Application.ttl"][0]
    assert _knowledge_file_states(repository) == before
    assert _git(repository, "status", "--porcelain=v1") == ""
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]
    assert entries[0]["code"] == "mcp.concurrent_workspace"


def test_real_proposal_branch_defines_distinct_named_graph_identity(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _git(repository, "switch", "--quiet", "main")
    graphs: list[URIRef] = []
    for branch in ("proposal/branch-alpha", "proposal/branch-beta"):
        _git(repository, "switch", "--quiet", "--create", branch)
        runtime = OntologyMcpRuntime(McpSettings.from_repository(repository, write_enabled=True))
        result = runtime.propose_relation(
            RelationInput(
                agent="branch-identity-adversary",
                subject=f"{BASE}id/software/application/workbench",
                predicate="http://purl.org/dc/terms/identifier",
                literal="branch-specific-proposal",
                evidence="La identidad del graph debe corresponder a la rama real",
            )
        )
        document = Dataset().parse(repository / str(result["path"]), format="trig")
        triple = (
            URIRef(f"{BASE}id/software/application/workbench"),
            URIRef("http://purl.org/dc/terms/identifier"),
            Literal("branch-specific-proposal"),
        )
        graphs.append(next(graph.identifier for graph in document.graphs() if triple in graph))
        _git(repository, "restore", "knowledge/data/sources/fixture_inventory.trig")
        _git(repository, "switch", "--quiet", "main")

    assert graphs == [
        URIRef(f"{BASE}graph/proposal/branch-alpha/fixture_inventory"),
        URIRef(f"{BASE}graph/proposal/branch-beta/fixture_inventory"),
    ]
    assert len(set(graphs)) == 2
    assert all("mcp-stage" not in str(graph) for graph in graphs)


def test_write_disabled_is_rejected_and_audited(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository)
    server = create_server(settings)

    async def reject() -> None:
        with pytest.raises(ToolError, match="controlled write tools are disabled"):
            await server.call_tool(
                "ontology_deprecate_term",
                {
                    "request": {
                        "agent": "read-only-agent",
                        "iri": f"{BASE}ontology/software#Application",
                        "reason": "No debe escribirse",
                    }
                },
            )

    asyncio.run(reject())
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert entries == [
        {
            "agent": "read-only-agent",
            "code": "mcp.write_disabled",
            "files": [],
            "invocation_id": entries[0]["invocation_id"],
            "result": "rejected",
            "timestamp": entries[0]["timestamp"],
            "tool": "ontology_deprecate_term",
        }
    ]


@pytest.mark.parametrize(
    "tool",
    [
        "ontology_propose_term",
        "ontology_propose_relation",
        "ontology_deprecate_term",
    ],
)
def test_invalid_write_schema_is_rejected_and_audited_before_handler(
    tmp_path: Path,
    tool: str,
) -> None:
    repository = _repository(tmp_path)
    audit = repository / ".eow/audit/schema-invalid.jsonl"

    async def reject() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "ontology_mcp.server",
                "--repository",
                repository.as_posix(),
                "--audit-log",
                audit.relative_to(repository).as_posix(),
                "--write-enabled",
            ],
            cwd=repository,
        )
        async with stdio_client(parameters) as (read, write):  # noqa: SIM117
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    tool,
                    {
                        "request": {
                            "agent": "schema-reviewer",
                            "iri": f"{BASE}ontology/software#Application",
                            "reason": "Schema adversarial",
                            "unknown": True,
                        }
                    },
                )
                assert result.is_error

    asyncio.run(reject())
    entries = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert entries == [
        {
            "agent": "schema-reviewer",
            "code": "mcp.schema_invalid",
            "files": [],
            "invocation_id": entries[0]["invocation_id"],
            "result": "rejected",
            "timestamp": entries[0]["timestamp"],
            "tool": tool,
        }
    ]


def test_audit_failure_aborts_and_rolls_back_a_controlled_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    term = repository / "knowledge/ontology/software/terms/Application.ttl"
    before = term.read_bytes()

    def unavailable(**_: object) -> None:
        raise OSError("audit sink unavailable")

    monkeypatch.setattr(runtime.audit, "record", unavailable)
    with pytest.raises(McpRuntimeError, match="audit record was unavailable"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="audit-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="La mutación debe revertirse si falla la auditoría",
            )
        )

    assert term.read_bytes() == before
    assert _git(repository, "status", "--short", "knowledge") == ""


def test_replaced_audit_parent_rejects_before_mutating_knowledge(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    term = repository / "knowledge/ontology/software/terms/Application.ttl"
    before = term.read_bytes()
    shutil.rmtree(settings.audit_log.parent)
    settings.audit_log.parent.write_text("not a directory", encoding="utf-8")

    with pytest.raises(McpRuntimeError, match="audit record was unavailable"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="audit-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="El preflight debe fallar antes de editar",
            )
        )

    assert term.read_bytes() == before
    assert _git(repository, "status", "--short", "knowledge") == ""


def test_failed_audit_fsync_removes_uncommitted_success_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    audit = WriteAuditLog(repository, repository / ".eow/audit/fsync.jsonl")
    real_fsync = audit_module.os.fsync
    calls = 0

    def fail_first_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("synthetic fsync failure after append")
        real_fsync(descriptor)

    monkeypatch.setattr(audit_module.os, "fsync", fail_first_fsync)
    with pytest.raises(AuditWriteError, match="not published atomically"):
        audit.record(
            agent="fsync-adversary",
            tool="ontology_deprecate_term",
            files=("knowledge/example.ttl",),
            result="success",
            invocation_id="invocation-fsync",
        )

    assert not audit.path.exists()


def test_failed_audit_fsync_and_ftruncate_cannot_leave_false_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    audit = WriteAuditLog(repository, repository / ".eow/audit/no-truncate.jsonl")
    truncate_calls = 0

    def fail_fsync(_: int) -> None:
        raise OSError("synthetic fsync failure")

    def fail_ftruncate(_: int, __: int) -> None:
        nonlocal truncate_calls
        truncate_calls += 1
        raise OSError("synthetic ftruncate failure")

    monkeypatch.setattr(audit_module.os, "fsync", fail_fsync)
    monkeypatch.setattr(audit_module.os, "ftruncate", fail_ftruncate)
    with pytest.raises(AuditWriteError, match="not published atomically"):
        audit.record(
            agent="terminal-adversary",
            tool="ontology_deprecate_term",
            files=(),
            result="success",
            invocation_id="fsync-and-truncate",
        )

    assert truncate_calls == 0
    assert not audit.path.exists()


def test_visible_atomic_audit_record_is_terminal_if_directory_fsync_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    audit = WriteAuditLog(repository, repository / ".eow/audit/directory-fsync.jsonl")
    real_fsync = audit_module.os.fsync
    calls = 0

    def fail_directory_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic directory fsync failure after atomic replace")
        real_fsync(descriptor)

    monkeypatch.setattr(audit_module.os, "fsync", fail_directory_fsync)
    audit.record(
        agent="directory-adversary",
        tool="ontology_deprecate_term",
        files=(),
        result="success",
        invocation_id="directory-fsync",
    )

    entries = [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]
    assert [entry["result"] for entry in entries] == ["success"]


def test_audit_log_serializes_independent_processes_without_lost_records(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    audit = repository / ".eow/audit/processes.jsonl"
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(
            target=_audit_process,
            args=(repository.as_posix(), audit.as_posix(), "alpha", 12, False),
        ),
        context.Process(
            target=_audit_process,
            args=(repository.as_posix(), audit.as_posix(), "beta", 12, True),
        ),
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    entries = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    invocation_ids = {str(entry["invocation_id"]) for entry in entries}
    assert len(entries) == 24
    assert len(invocation_ids) == 24
    assert "beta-failed" not in invocation_ids
    assert all(entry["result"] == "success" for entry in entries)


def test_success_audit_failure_restores_only_target_and_records_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/Application.ttl"
    before = target.read_bytes()
    target.chmod(0o640)
    timestamp = 1_700_000_000_123_456_789
    target.touch()
    target_stat = target.stat()
    target_mtime = timestamp
    target_atime = target_stat.st_atime_ns
    target.chmod(0o640)
    audit_module.os.utime(target, ns=(target_atime, target_mtime))
    real_record = runtime.audit.record
    failed = False

    def fail_success_once(**arguments: object) -> None:
        nonlocal failed
        if arguments["result"] == "success" and not failed:
            failed = True
            raise AuditWriteError("synthetic success audit failure")
        real_record(**arguments)  # type: ignore[arg-type]

    monkeypatch.setattr(runtime.audit, "record", fail_success_once)
    with pytest.raises(McpRuntimeError, match="success audit was unavailable"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="audit-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="La auditoría debe ser terminal e inequívoca",
            )
        )

    current = target.stat()
    assert target.read_bytes() == before
    assert current.st_mode & 0o777 == 0o640
    assert current.st_mtime_ns == target_mtime
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]
    assert entries[0]["code"] == "mcp.write_failed"


def test_runtime_fsync_failure_never_leaves_a_false_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/Application.ttl"
    before = target.read_bytes()
    real_record = runtime.audit.record

    def fail_success_fsync(**arguments: object) -> None:
        if arguments["result"] != "success":
            real_record(**arguments)  # type: ignore[arg-type]
            return
        real_fsync = audit_module.os.fsync
        calls = 0

        def fail_first(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("synthetic post-append fsync failure")
            real_fsync(descriptor)

        with monkeypatch.context() as context:
            context.setattr(audit_module.os, "fsync", fail_first)
            real_record(**arguments)  # type: ignore[arg-type]

    monkeypatch.setattr(runtime.audit, "record", fail_success_fsync)
    with pytest.raises(McpRuntimeError, match="success audit was unavailable"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="fsync-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="Un success no durable nunca debe quedar como resultado final",
            )
        )

    assert target.read_bytes() == before
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]
    assert len({entry["invocation_id"] for entry in entries}) == 1


def test_rejected_staging_does_not_touch_unrelated_metadata(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    unrelated = repository / "knowledge/ontology/software/terms/Application.ttl"
    unrelated.chmod(0o644)
    before = unrelated.stat()

    with pytest.raises(Exception, match="published ontology term"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="metadata-adversary",
                iri=f"{BASE}ontology/software#MissingTerm",
                reason="El staging rechazado no debe tocar archivos reales",
            )
        )

    after = unrelated.stat()
    assert after.st_mode == before.st_mode
    assert after.st_mtime_ns == before.st_mtime_ns


def test_concurrent_unrelated_file_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    concurrent = repository / "knowledge/concurrent-note.txt"
    publish = runtime._publish_staged_file

    def create_concurrent_file(*arguments: object, **keywords: object):  # type: ignore[no-untyped-def]
        concurrent.write_text("preserve me", encoding="utf-8")
        return publish(*arguments, **keywords)  # type: ignore[arg-type]

    monkeypatch.setattr(runtime, "_publish_staged_file", create_concurrent_file)
    runtime.deprecate_term(
        DeprecateInput(
            agent="concurrency-adversary",
            iri=f"{BASE}ontology/software#Application",
            reason="Un archivo ajeno concurrente debe sobrevivir",
        )
    )

    assert concurrent.read_text(encoding="utf-8") == "preserve me"


def test_concurrent_target_edit_is_preserved_and_proposal_aborts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/Application.ttl"
    external = target.read_bytes() + b"\n# concurrent external edit\n"
    publish = runtime._publish_staged_file

    def edit_target(*arguments: object, **keywords: object):  # type: ignore[no-untyped-def]
        target.write_bytes(external)
        return publish(*arguments, **keywords)  # type: ignore[arg-type]

    monkeypatch.setattr(runtime, "_publish_staged_file", edit_target)
    with pytest.raises(McpRuntimeError, match="changed outside"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="concurrency-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="La edición externa debe ganar el compare-and-swap",
            )
        )

    assert target.read_bytes() == external


def test_target_edit_immediately_before_exchange_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/Application.ttl"
    external = target.read_bytes() + b"\n# edit in the former TOCTOU window\n"
    external_mode = 0o640
    external_mtime = 1_700_000_000_234_567_890
    real_exchange = runtime._exchange_paths
    injected = False

    def inject_before_exchange(left: Path, right: Path) -> None:
        nonlocal injected
        if not injected and right == target:
            injected = True
            target.write_bytes(external)
            target.chmod(external_mode)
            os.utime(target, ns=(external_mtime, external_mtime))
        real_exchange(left, right)

    monkeypatch.setattr(runtime, "_exchange_paths", inject_before_exchange)
    with pytest.raises(McpRuntimeError, match="changed outside"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="exchange-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="La edición entre check y publicación debe sobrevivir",
            )
        )

    metadata = target.stat()
    assert target.read_bytes() == external
    assert metadata.st_mode & 0o777 == external_mode
    assert metadata.st_mtime_ns == external_mtime


def test_target_edit_immediately_after_exchange_is_rejected_and_audited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/Application.ttl"
    external = target.read_bytes() + b"\n# edit immediately after exchange\n"
    external_mode = 0o640
    external_mtime = 1_700_000_000_456_789_012
    real_exchange = runtime._exchange_paths
    injected = False

    def inject_after_exchange(left: Path, right: Path) -> None:
        nonlocal injected
        real_exchange(left, right)
        if not injected and right == target:
            injected = True
            target.write_bytes(external)
            target.chmod(external_mode)
            os.utime(target, ns=(external_mtime, external_mtime))

    monkeypatch.setattr(runtime, "_exchange_paths", inject_after_exchange)
    with pytest.raises(McpRuntimeError, match="immediately after atomic publication"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="post-exchange-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="La propuesta no puede informar success si deja de ser el target",
            )
        )

    metadata = target.stat()
    assert target.read_bytes() == external
    assert b"owl:deprecated true" not in external
    assert metadata.st_mode & 0o777 == external_mode
    assert metadata.st_mtime_ns == external_mtime
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]
    assert entries[0]["code"] == "mcp.concurrent_target"


def test_new_target_created_immediately_before_link_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/ConcurrentNew.ttl"
    staged = repository / "staged-new.ttl"
    staged.write_text("staged", encoding="utf-8")
    external = b"external creation wins\n"
    external_mtime = 1_700_000_000_345_678_901
    real_link = os.link

    def create_before_link(source: Path, destination: Path, **kwargs: object) -> None:
        target.write_bytes(external)
        target.chmod(0o640)
        os.utime(target, ns=(external_mtime, external_mtime))
        real_link(source, destination, **kwargs)

    monkeypatch.setattr(os, "link", create_before_link)
    with pytest.raises(McpRuntimeError, match="created outside"):
        runtime._publish_staged_file(target, staged, None)

    metadata = target.stat()
    assert target.read_bytes() == external
    assert metadata.st_mode & 0o777 == 0o640
    assert metadata.st_mtime_ns == external_mtime


def test_new_target_edit_immediately_after_link_is_rejected_and_audited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    search = runtime.search(SearchInput(text="unidad post link", limit=50, offset=0))
    target = repository / "knowledge/data/sources/proposals/post_link.ttl"
    external = b"# external file created immediately after link\n"
    external_mode = 0o640
    external_mtime = 1_700_000_000_567_890_123
    real_link = os.link

    def edit_after_link(source: Path, destination: Path, **kwargs: object) -> None:
        real_link(source, destination, **kwargs)
        if Path(destination) == target:
            target.write_bytes(external)
            target.chmod(external_mode)
            os.utime(target, ns=(external_mtime, external_mtime))

    monkeypatch.setattr(os, "link", edit_after_link)
    with pytest.raises(McpRuntimeError, match="immediately after atomic publication"):
        runtime.propose_term(
            TermInput(
                agent="post-link-adversary",
                iri=f"{BASE}id/organization/unit/post_link",
                module_id="organization",
                kind="individual",
                preferred_label_es="Unidad post link",
                evidence="Fixture de carrera posterior a link",
                author="post-link-adversary",
                search_query="unidad post link",
                search_id=str(search["search_id"]),
                search_confirmed=True,
                class_iri=f"{BASE}ontology/organization#OrganizationUnit",
                source_id="post_link",
            )
        )

    metadata = target.stat()
    assert target.read_bytes() == external
    assert metadata.st_mode & 0o777 == external_mode
    assert metadata.st_mtime_ns == external_mtime
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]
    assert entries[0]["code"] == "mcp.concurrent_target"


def test_second_edit_during_compensating_exchange_is_recovered_without_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/Application.ttl"
    first_external = target.read_bytes() + b"\n# first concurrent edit\n"
    second_external = target.read_bytes() + b"\n# second concurrent edit\n"
    second_mode = 0o600
    second_mtime = 1_700_000_000_678_901_234
    real_exchange = runtime._exchange_paths
    calls = 0

    def edit_around_compensation(left: Path, right: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            target.write_bytes(first_external)
        elif calls == 2:
            target.write_bytes(second_external)
            target.chmod(second_mode)
            os.utime(target, ns=(second_mtime, second_mtime))
        real_exchange(left, right)

    monkeypatch.setattr(runtime, "_exchange_paths", edit_around_compensation)
    with pytest.raises(McpRuntimeError, match="displaced state was preserved"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="compensation-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="La segunda edición debe ganar la compensación",
            )
        )

    assert target.read_bytes() == first_external
    recoveries = tuple((repository / ".eow/recovery").glob("*.recovery"))
    assert len(recoveries) == 1
    metadata = recoveries[0].stat()
    assert recoveries[0].read_bytes() == second_external
    assert metadata.st_mode & 0o777 == second_mode
    assert metadata.st_mtime_ns == second_mtime
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]


def test_third_edit_after_compensation_is_target_and_second_is_recovered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    target = repository / "knowledge/ontology/software/terms/Application.ttl"
    baseline = target.read_bytes()
    first_external = baseline + b"\n# first concurrent edit\n"
    second_external = baseline + b"\n# second concurrent edit\n"
    third_external = baseline + b"\n# third concurrent edit\n"
    second_mode = 0o600
    second_mtime = 1_700_000_000_678_901_235
    third_mode = 0o640
    third_mtime = 1_700_000_000_678_901_236
    real_exchange = runtime._exchange_paths
    calls = 0

    def edit_during_every_exchange(left: Path, right: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            target.write_bytes(first_external)
        elif calls == 2:
            target.write_bytes(second_external)
            target.chmod(second_mode)
            os.utime(target, ns=(second_mtime, second_mtime))
        real_exchange(left, right)
        if calls == 2:
            target.write_bytes(third_external)
            target.chmod(third_mode)
            os.utime(target, ns=(third_mtime, third_mtime))

    monkeypatch.setattr(runtime, "_exchange_paths", edit_during_every_exchange)
    with pytest.raises(McpRuntimeError, match="displaced state was preserved"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="third-edit-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="Ninguna edición concurrente desplazada puede eliminarse",
            )
        )

    target_metadata = target.stat()
    assert target.read_bytes() == third_external
    assert target_metadata.st_mode & 0o777 == third_mode
    assert target_metadata.st_mtime_ns == third_mtime
    recoveries = tuple((repository / ".eow/recovery").glob("*.recovery"))
    assert len(recoveries) == 1
    recovery_metadata = recoveries[0].stat()
    assert recoveries[0].read_bytes() == second_external
    assert recovery_metadata.st_mode & 0o777 == second_mode
    assert recovery_metadata.st_mtime_ns == second_mtime
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]
    assert entries[0]["code"] == "mcp.concurrent_target"


def test_new_target_edit_after_atomic_detach_survives_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    search = runtime.search(SearchInput(text="unidad rollback detach", limit=50, offset=0))
    target = repository / "knowledge/data/sources/proposals/rollback_detach.ttl"
    external = b"# external replacement after rollback detach\n"
    external_mode = 0o640
    external_mtime = 1_700_000_000_678_901_237
    real_replace = os.replace
    real_record = runtime.audit.record

    def fail_success(**arguments: object) -> None:
        if arguments["result"] == "success":
            raise AuditWriteError("synthetic success audit failure")
        real_record(**arguments)  # type: ignore[arg-type]

    def edit_after_detach(source: Path, destination: Path) -> None:
        real_replace(source, destination)
        if Path(source) == target and ".rollback-" in Path(destination).name:
            target.write_bytes(external)
            target.chmod(external_mode)
            os.utime(target, ns=(external_mtime, external_mtime))

    monkeypatch.setattr(runtime.audit, "record", fail_success)
    monkeypatch.setattr(os, "replace", edit_after_detach)
    with pytest.raises(McpRuntimeError, match="success audit was unavailable"):
        runtime.propose_term(
            TermInput(
                agent="rollback-detach-adversary",
                iri=f"{BASE}id/organization/unit/rollback_detach",
                module_id="organization",
                kind="individual",
                preferred_label_es="Unidad rollback detach",
                evidence="Fixture de carrera posterior al detach atómico",
                author="rollback-detach-adversary",
                search_query="unidad rollback detach",
                search_id=str(search["search_id"]),
                search_confirmed=True,
                class_iri=f"{BASE}ontology/organization#OrganizationUnit",
                source_id="rollback_detach",
            )
        )

    metadata = target.stat()
    assert target.read_bytes() == external
    assert metadata.st_mode & 0o777 == external_mode
    assert metadata.st_mtime_ns == external_mtime
    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]
    assert entries[0]["code"] == "mcp.write_failed"


@pytest.mark.parametrize(
    ("system", "backend"),
    [
        ("Linux", "_linux_exchange_paths"),
        ("Darwin", "_macos_exchange_paths"),
        ("Windows", "_windows_exchange_paths"),
    ],
)
def test_atomic_exchange_dispatches_to_each_supported_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    backend: str,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    selected: list[tuple[Path, Path]] = []
    monkeypatch.setattr("ontology_mcp.runtime.platform.system", lambda: system)
    monkeypatch.setattr(
        OntologyMcpRuntime,
        backend,
        staticmethod(lambda first, second: selected.append((first, second))),
    )

    OntologyMcpRuntime._exchange_paths(left, right)

    assert selected == [(left, right)]


def test_macos_exchange_backend_preserves_swap_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.write_text("candidate", encoding="utf-8")
    right.write_text("baseline", encoding="utf-8")

    class FakeRename:
        argtypes: object = None
        restype: object = None

        def __call__(self, first: bytes, second: bytes, flags: int) -> int:
            assert flags == 2
            first_path = Path(os.fsdecode(first))
            second_path = Path(os.fsdecode(second))
            scratch = tmp_path / "macos-scratch"
            os.rename(first_path, scratch)
            os.rename(second_path, first_path)
            os.rename(scratch, second_path)
            return 0

    class FakeLibrary:
        renamex_np = FakeRename()

    monkeypatch.setattr("ontology_mcp.runtime.ctypes.CDLL", lambda *args, **kwargs: FakeLibrary())

    OntologyMcpRuntime._macos_exchange_paths(left, right)

    assert left.read_text(encoding="utf-8") == "baseline"
    assert right.read_text(encoding="utf-8") == "candidate"


def test_windows_exchange_backend_preserves_swap_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.write_text("candidate", encoding="utf-8")
    right.write_text("baseline", encoding="utf-8")

    class FakeReplace:
        argtypes: object = None
        restype: object = None

        def __call__(
            self,
            target: str,
            replacement: str,
            backup: str,
            flags: int,
            _exclude: object,
            _reserved: object,
        ) -> int:
            assert flags == 1
            os.replace(target, backup)
            os.replace(replacement, target)
            return 1

    class FakeKernel:
        ReplaceFileW = FakeReplace()

    monkeypatch.setattr(
        "ontology_mcp.runtime.ctypes.WinDLL",
        lambda *args, **kwargs: FakeKernel(),
        raising=False,
    )

    OntologyMcpRuntime._windows_exchange_paths(left, right)

    assert left.read_text(encoding="utf-8") == "baseline"
    assert right.read_text(encoding="utf-8") == "candidate"


def test_unknown_platform_fails_closed_without_touching_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.write_text("candidate", encoding="utf-8")
    right.write_text("baseline", encoding="utf-8")
    monkeypatch.setattr("ontology_mcp.runtime.platform.system", lambda: "UnsupportedOS")

    with pytest.raises(McpRuntimeError, match="no atomic exchange backend"):
        OntologyMcpRuntime._exchange_paths(left, right)

    assert left.read_text(encoding="utf-8") == "candidate"
    assert right.read_text(encoding="utf-8") == "baseline"


def test_rollback_failure_is_explicitly_audited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    settings = McpSettings.from_repository(repository, write_enabled=True)
    runtime = OntologyMcpRuntime(settings)
    real_record = runtime.audit.record

    def fail_success(**arguments: object) -> None:
        if arguments["result"] == "success":
            raise AuditWriteError("synthetic success audit failure")
        real_record(**arguments)  # type: ignore[arg-type]

    def fail_restore(_: object) -> None:
        raise OSError("synthetic rollback failure")

    monkeypatch.setattr(runtime.audit, "record", fail_success)
    monkeypatch.setattr(runtime, "_restore_published_file", fail_restore)
    with pytest.raises(McpRuntimeError, match="could not be restored safely"):
        runtime.deprecate_term(
            DeprecateInput(
                agent="rollback-adversary",
                iri=f"{BASE}ontology/software#Application",
                reason="La falla de rollback debe quedar explícita",
            )
        )

    entries = [
        json.loads(line) for line in settings.audit_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["result"] for entry in entries] == ["rejected"]
    assert entries[0]["code"] == "mcp.rollback_failed"

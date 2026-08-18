"""Local stdio MCP server for governed ontology operations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote

from mcp.server import MCPServer
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.types import ToolAnnotations
from ontology_core import AgentContractService
from pydantic import ConfigDict

from ontology_mcp.config import McpSettings, parse_settings
from ontology_mcp.models import (
    ContextInput,
    DeprecateInput,
    DescribeInput,
    DiffInput,
    EmptyInput,
    RelationInput,
    SearchInput,
    TermInput,
)
from ontology_mcp.runtime import OntologyMcpRuntime

WRITE_TOOLS = frozenset(
    {
        "ontology_propose_term",
        "ontology_propose_relation",
        "ontology_deprecate_term",
    }
)


class _WriteAuditMiddleware:
    """Audit protocol-level write rejections that occur before a tool handler."""

    def __init__(self, runtime: OntologyMcpRuntime) -> None:
        self.runtime = runtime

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        params = ctx.params if isinstance(ctx.params, Mapping) else {}
        tool = params.get("name")
        if ctx.method != "tools/call" or tool not in WRITE_TOOLS:
            return await call_next(ctx)
        token = self.runtime.begin_protocol_write()
        try:
            result = await call_next(ctx)
            is_error = bool(getattr(result, "is_error", False))
            if isinstance(result, Mapping):
                is_error = is_error or bool(result.get("isError") or result.get("is_error"))
            if is_error and not self.runtime.protocol_write_audited:
                self.runtime.audit_protocol_rejection(
                    agent=self._agent(params),
                    tool=str(tool),
                    code="mcp.schema_invalid",
                )
            return result
        except Exception:
            if not self.runtime.protocol_write_audited:
                self.runtime.audit_protocol_rejection(
                    agent=self._agent(params),
                    tool=str(tool),
                    code="mcp.schema_invalid",
                )
            raise
        finally:
            self.runtime.end_protocol_write(token)

    @staticmethod
    def _agent(params: Mapping[str, object]) -> str:
        arguments = params.get("arguments")
        if isinstance(arguments, Mapping):
            request = arguments.get("request")
            if isinstance(request, Mapping):
                agent = request.get("agent")
                if isinstance(agent, str) and agent.strip():
                    return agent.strip()
        return "unknown"


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _harden_tool_schema(server: MCPServer[Any], name: str) -> None:
    """Make the SDK's generated outer argument object strict as required by the spec."""

    manager: Any = server._tool_manager
    tool: Any = manager._tools[name]
    model: Any = tool.fn_metadata.arg_model
    model.model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        strict=True,
    )
    model.model_rebuild(force=True)
    tool.parameters = model.model_json_schema(by_alias=True)


def create_server(settings: McpSettings) -> MCPServer[Any]:
    runtime = OntologyMcpRuntime(settings)
    contract = AgentContractService(settings.repository_root)
    prompt_templates = {
        document.identifier: document.content.strip() for document in contract.prompts
    }
    server: MCPServer[Any] = MCPServer(
        "enterprise-ontology-workbench",
        version="0.1.0",
        description="Local governed RDF/Git workbench",
        instructions=contract.mcp_instructions.content.strip(),
        middleware=[_WriteAuditMiddleware(runtime)],
    )

    read_only = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
    controlled_write = ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )

    @server.tool(name="ontology_list_modules", structured_output=True, annotations=read_only)
    def ontology_list_modules(request: EmptyInput) -> dict[str, object]:
        """List deterministic modules, ownership state and imports."""

        del request
        return runtime.list_modules()

    @server.tool(name="ontology_search", structured_output=True, annotations=read_only)
    def ontology_search(request: SearchInput) -> dict[str, object]:
        """Search IRI/local name/labels and issue an auditable search receipt."""

        return runtime.search(request)

    @server.tool(name="ontology_describe", structured_output=True, annotations=read_only)
    def ontology_describe(request: DescribeInput) -> dict[str, object]:
        """Describe one RDF resource with bounded neighborhood and impact."""

        return runtime.describe(request)

    @server.tool(name="ontology_get_context", structured_output=True, annotations=read_only)
    def ontology_get_context(request: ContextInput) -> dict[str, object]:
        """Build deterministic bounded JSON and Markdown context without embeddings."""

        return runtime.get_context(request)

    @server.tool(name="ontology_validate", structured_output=True, annotations=read_only)
    def ontology_validate(request: EmptyInput) -> dict[str, object]:
        """Run parser, SHACL and deterministic governance rules."""

        del request
        return runtime.validate()

    @server.tool(name="ontology_diff", structured_output=True, annotations=read_only)
    def ontology_diff(request: DiffInput) -> dict[str, object]:
        """Review the semantic diff of the current proposal against a Git base."""

        return runtime.diff(request)

    @server.tool(
        name="ontology_propose_term",
        structured_output=True,
        annotations=controlled_write,
    )
    def ontology_propose_term(request: TermInput) -> dict[str, object]:
        """Create or update one controlled RDF term after confirmed global search."""

        return runtime.propose_term(request)

    @server.tool(
        name="ontology_propose_relation",
        structured_output=True,
        annotations=controlled_write,
    )
    def ontology_propose_relation(request: RelationInput) -> dict[str, object]:
        """Add one validated proposed relation with evidence."""

        return runtime.propose_relation(request)

    @server.tool(
        name="ontology_deprecate_term",
        structured_output=True,
        annotations=controlled_write,
    )
    def ontology_deprecate_term(request: DeprecateInput) -> dict[str, object]:
        """Deprecate a published term without deleting its RDF file."""

        return runtime.deprecate_term(request)

    for tool_name in (
        "ontology_list_modules",
        "ontology_search",
        "ontology_describe",
        "ontology_get_context",
        "ontology_validate",
        "ontology_diff",
        "ontology_propose_term",
        "ontology_propose_relation",
        "ontology_deprecate_term",
    ):
        _harden_tool_schema(server, tool_name)

    @server.resource(
        "ontology://governance/rules",
        name="governance_rules",
        description="Canonical governed agent rules",
        mime_type="application/json",
    )
    def governance_rules() -> str:
        return _json(runtime.governance_rules())

    @server.resource(
        "ontology://manifest/modules",
        name="module_manifest",
        description="Loaded RDF module manifest",
        mime_type="application/json",
    )
    def module_manifest() -> str:
        return _json(runtime.list_modules())

    @server.resource(
        "ontology://validation/current",
        name="validation_report",
        description="Current deterministic validation report",
        mime_type="application/json",
    )
    def validation_report() -> str:
        return _json(runtime.validate())

    @server.resource(
        "ontology://competency/questions",
        name="competency_questions",
        description="RDF-backed competency questions",
        mime_type="application/json",
    )
    def competency_questions() -> str:
        return _json(runtime.competency_questions())

    @server.resource(
        "ontology://resource/{iri}",
        name="relevant_ontology",
        description="Description, neighborhood and impact relevant to an encoded IRI",
        mime_type="application/json",
    )
    def relevant_ontology(iri: str) -> str:
        return _json(runtime.relevant_ontology(unquote(iri)))

    @server.prompt(name="model_domain_concept")
    def model_domain_concept(task: str, evidence: str) -> str:
        """Guide a governed decision between reuse, concept, class or individual."""

        return prompt_templates["model_domain_concept"].format(task=task, evidence=evidence)

    @server.prompt(name="review_ontology_change")
    def review_ontology_change(base: str = "main") -> str:
        """Guide a complete governed review of an ontology proposal."""

        return prompt_templates["review_ontology_change"].format(base=base)

    @server.prompt(name="connect_repository_to_enterprise_knowledge")
    def connect_repository_to_enterprise_knowledge(repository: str, business_question: str) -> str:
        """Guide a minimal evidence-backed connection to enterprise knowledge."""

        return prompt_templates["connect_repository_to_enterprise_knowledge"].format(
            repository=repository,
            business_question=business_question,
        )

    return server


def main(argv: list[str] | None = None) -> None:
    create_server(parse_settings(argv)).run(transport="stdio")


if __name__ == "__main__":
    main()

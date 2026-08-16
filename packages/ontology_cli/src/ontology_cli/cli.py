"""Deterministic command-line adapter over ontology_core."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from ontology_core import (
    AgentContextService,
    AgentContractError,
    AgentContractService,
    ContextBudget,
    ContextRequest,
    FilesystemRdfStore,
    GitWorkspaceError,
    GitWorkspaceService,
    ImpactService,
    OntologyQueryService,
    ProposalReviewService,
    ReadOnlySparqlService,
    SparqlLimits,
    SparqlQueryError,
    ValidationService,
)


class CliError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ontology")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        child = subparsers.add_parser(name, help=help_text)
        child.add_argument("--json", action="store_true", dest="as_json")
        return child

    command("status", "Estado Git, RDF y contrato de agentes")
    command("modules", "Lista módulos e imports")
    search = command("search", "Busca recursos y emite search_id")
    search.add_argument("text")
    search.add_argument("--limit", type=int, default=50)
    search.add_argument("--offset", type=int, default=0)
    describe = command("describe", "Describe un recurso")
    describe.add_argument("iri")
    context = command("context", "Genera contexto estructurado")
    context.add_argument("--task", required=True)
    context.add_argument("--term", action="append", default=[])
    context.add_argument("--module", action="append", default=[])
    context.add_argument("--max-terms", type=int, default=80)
    context.add_argument("--depth", type=int, default=2)
    context.add_argument("--max-bytes", type=int, default=64 * 1024)
    command("validate", "Ejecuta parser, SHACL y lint")
    diff = command("diff", "Compara la propuesta con una revisión base")
    diff.add_argument("--base", default="main")
    impact = command("impact", "Calcula impacto semántico")
    impact.add_argument("iri")
    query = command("query", "Ejecuta un archivo SPARQL de solo lectura")
    query.add_argument("file", type=Path)
    query.add_argument("--timeout", type=float, default=5.0)
    query.add_argument("--max-results", type=int, default=1000)
    command("agent_sync", "Regenera AGENTS, CLAUDE y skills")
    return parser


def _services(repository: Path) -> tuple[Path, FilesystemRdfStore, OntologyQueryService]:
    try:
        root = repository.resolve(strict=True)
    except OSError as error:
        raise CliError("repository.unavailable", "repository path is unavailable") from error
    knowledge = root / "knowledge"
    namespace = root / "config/namespace.yaml"
    try:
        store = FilesystemRdfStore(knowledge, namespace)
        dataset = store.load()
    except Exception as error:  # noqa: BLE001 - normalized at the CLI boundary
        raise CliError("rdf.load_failed", str(error)) from error
    return root, store, OntologyQueryService(dataset, store.prefixes)


def _query_text(root: Path, requested: Path) -> str:
    candidate = requested if requested.is_absolute() else root / requested
    if candidate.is_symlink():
        raise CliError("query.unsafe_path", "query files cannot be symbolic links")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CliError("query.unavailable", "query file is unavailable") from error
    allowed = (root / "knowledge/competency_questions/queries").resolve(strict=True)
    if not resolved.is_relative_to(allowed) or not resolved.is_file():
        raise CliError(
            "query.unsafe_path",
            "query files must be regular local files under knowledge/competency_questions/queries",
        )
    try:
        return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CliError("query.decode", "query file must be valid UTF-8") from error


def _execute(arguments: argparse.Namespace) -> object:
    root, store, query = _services(arguments.repository)
    command = arguments.command
    if command == "status":
        try:
            git: object = GitWorkspaceService(root, store.knowledge_root).status().to_dict()
        except GitWorkspaceError as error:
            git = {"available": False, "code": error.code}
        validation = ValidationService(store).validate_dataset(store.dataset)
        return {
            "repository": root.as_posix(),
            "git": git,
            "dataset": query.stats(store.discover_modules()).to_dict(),
            "validation": validation.to_dict(),
            "agent_contract": AgentContractService(root).status().to_dict(),
        }
    if command == "modules":
        return {"items": [item.to_dict() for item in query.modules(store.discover_modules())]}
    if command == "search":
        return query.search_page(
            arguments.text, limit=arguments.limit, offset=arguments.offset
        ).to_dict()
    if command == "describe":
        description = query.describe(arguments.iri)
        if description is None:
            raise CliError("resource.not_found", "requested RDF resource does not exist")
        return description.to_dict()
    if command == "context":
        pack = AgentContextService(store).generate(
            ContextRequest(
                task=arguments.task,
                terms=tuple(arguments.term),
                modules=tuple(arguments.module),
                budget=ContextBudget(
                    max_terms=arguments.max_terms,
                    depth=arguments.depth,
                    max_bytes=arguments.max_bytes,
                ),
            )
        )
        return pack.to_dict()
    if command == "validate":
        return ValidationService(store).validate_repository().to_dict()
    if command == "diff":
        workspace = GitWorkspaceService(root, store.knowledge_root)
        return (
            ProposalReviewService(store, workspace).review(base_ref=arguments.base).diff.to_dict()
        )
    if command == "impact":
        return (
            ImpactService(store.dataset, store.prefixes, store=store)
            .analyze(arguments.iri)
            .to_dict()
        )
    if command == "query":
        service = ReadOnlySparqlService(
            store.dataset,
            store.prefixes,
            limits=SparqlLimits(
                timeout_seconds=arguments.timeout,
                max_results=arguments.max_results,
            ),
        )
        return service.execute(_query_text(root, arguments.file)).to_dict()
    if command == "agent_sync":
        return AgentContractService(root).sync().to_dict()
    raise CliError("cli.command", "unsupported command")


def _emit(payload: object, *, as_json: bool, stream: Any | None = None) -> None:
    destination = sys.stdout if stream is None else stream
    if as_json:
        print(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            file=destination,
        )
    else:
        print(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).rstrip(),
            file=destination,
        )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        payload = _execute(arguments)
    except (AgentContractError, GitWorkspaceError, SparqlQueryError, CliError, ValueError) as error:
        code = getattr(error, "code", "cli.invalid_request")
        _emit(
            {"error": {"code": code, "message": str(error)}},
            as_json=arguments.as_json,
            stream=sys.stderr,
        )
        return 2
    _emit(payload, as_json=arguments.as_json)
    return 0

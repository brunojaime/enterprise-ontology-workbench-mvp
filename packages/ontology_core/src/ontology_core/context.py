"""Deterministic context packs assembled from RDF without vector retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass

from rdflib import URIRef
from rdflib.namespace import OWL

from ontology_core.agent_contract import AgentContractService
from ontology_core.competency import CompetencyQuestionRepository
from ontology_core.impact import ImpactService
from ontology_core.query import NeighborhoodLimits, OntologyQueryService, SearchResult
from ontology_core.search_receipts import SearchReceiptAuthority
from ontology_core.store import FilesystemRdfStore, ModuleDefinition


class ContextBudgetError(ValueError):
    """The requested context budget is invalid or cannot hold the fixed contract."""


@dataclass(frozen=True)
class ContextBudget:
    max_terms: int = 80
    depth: int = 2
    max_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if not 1 <= self.max_terms <= 500:
            raise ContextBudgetError("max_terms must be between 1 and 500")
        if not 0 <= self.depth <= 5:
            raise ContextBudgetError("depth must be between 0 and 5")
        if not 4096 <= self.max_bytes <= 1024 * 1024:
            raise ContextBudgetError("max_bytes must be between 4096 and 1048576")


@dataclass(frozen=True)
class ContextRequest:
    task: str
    terms: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    budget: ContextBudget = ContextBudget()

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("task must be non-empty")


@dataclass(frozen=True)
class AgentContextPack:
    payload: dict[str, object]
    json: str
    markdown: str
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return self.payload


class AgentContextService:
    """Build a bounded explainable context pack from canonical RDF services."""

    def __init__(
        self,
        store: FilesystemRdfStore,
        *,
        receipt_authority: SearchReceiptAuthority | None = None,
        snapshot_id: str | None = None,
    ) -> None:
        self.store = store
        self.dataset = store.load()
        self.prefixes = store.prefixes
        self.modules = tuple(sorted(store.discover_modules(), key=lambda module: module.identifier))
        self.knowledge_root = store.knowledge_root
        self.query = OntologyQueryService(
            self.dataset,
            self.prefixes,
            receipt_authority=receipt_authority,
            snapshot_id=snapshot_id,
        )
        self.impact = ImpactService(self.dataset, self.prefixes, store=store)
        self.questions = CompetencyQuestionRepository(
            self.dataset, self.prefixes.configuration.base
        )

    def generate(self, request: ContextRequest) -> AgentContextPack:
        candidates = self._candidates(request)
        selected = list(candidates[: request.budget.max_terms])
        initially_truncated = len(candidates) > len(selected)
        while True:
            payload = self._payload(request, tuple(selected), initially_truncated)
            json_text = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            markdown = self._markdown(payload)
            if (
                len(json_text.encode("utf-8")) <= request.budget.max_bytes
                and len(markdown.encode("utf-8")) <= request.budget.max_bytes
            ):
                truncated = bool(payload["limits"]["truncated"])  # type: ignore[index]
                return AgentContextPack(payload, json_text, markdown, truncated)
            if selected:
                selected.pop()
                initially_truncated = True
                continue
            raise ContextBudgetError("max_bytes is too small for the fixed context contract")

    def _candidates(self, request: ContextRequest) -> tuple[SearchResult, ...]:
        search_terms = tuple(dict.fromkeys((*request.terms, *self._task_tokens(request.task))))
        by_iri: dict[str, SearchResult] = {}
        for term in search_terms:
            for result in self.query.search(term, limit=request.budget.max_terms):
                existing = by_iri.get(result.iri)
                if existing is None or (result.score, result.iri) < (existing.score, existing.iri):
                    by_iri[result.iri] = result
        selected_modules = self._selected_module_ids(request.modules, request.budget.depth)
        allowed_modules = {
            f"{self.prefixes.configuration.base}id/module/{module}" for module in selected_modules
        }
        results = tuple(by_iri.values())
        if request.modules:
            results = tuple(
                result for result in results if allowed_modules.intersection(result.modules)
            )
        return tuple(sorted(results, key=lambda result: (result.score, result.iri)))

    def _payload(
        self,
        request: ContextRequest,
        terms: tuple[SearchResult, ...],
        truncated: bool,
    ) -> dict[str, object]:
        term_entries: list[dict[str, object]] = []
        neighborhoods: list[dict[str, object]] = []
        shapes: set[str] = set()
        for term in terms:
            description = self.query.describe(term.iri)
            entry = term.to_dict()
            entry["definitions"] = (
                [value.to_dict() for value in description.definitions] if description else []
            )
            term_entries.append(entry)
            neighborhood = self.query.neighborhood(
                term.iri,
                depth=request.budget.depth,
                limits=NeighborhoodLimits(
                    max_depth=request.budget.depth,
                    max_nodes=max(1, request.budget.max_terms),
                    max_edges=request.budget.max_terms * 3,
                ),
            )
            neighborhoods.append(neighborhood.to_dict())
            shapes.update(value.value for value in self.impact.analyze(term.iri).shapes)
        selected_modules = self._selected_module_ids(request.modules, request.budget.depth)
        module_entries = [
            self._module_entry(module)
            for module in self.modules
            if not request.modules or module.identifier in selected_modules
        ]
        question_entries = [
            question.to_dict()
            for question in self.questions.list()
            if not request.modules or question.module.rsplit("/", 1)[-1] in selected_modules
        ]
        limits = {
            "max_terms": request.budget.max_terms,
            "depth": request.budget.depth,
            "max_bytes": request.budget.max_bytes,
            "included_terms": len(term_entries),
            "truncated": truncated,
        }
        contract_manifest = self.knowledge_root.parent / "agent_contract/manifest.yaml"
        if contract_manifest.is_file():
            contract = AgentContractService(self.knowledge_root.parent)
            rules = [
                {"id": rule.identifier, "source": f"agent_contract/{rule.path}"}
                for rule in contract.rules
            ]
        else:
            rules = [
                {
                    "id": "search_before_create",
                    "source": "enterprise_ontology_workbench_mvp_spec.md#62-buscar-antes-de-crear",
                },
                {
                    "id": "rdf_and_git_are_canonical",
                    "source": "enterprise_ontology_workbench_mvp_spec.md#31-fuente-canónica",
                },
                {
                    "id": "validate_before_publish",
                    "source": (
                        "enterprise_ontology_workbench_mvp_spec.md#610-validación-determinista"
                    ),
                },
            ]
        return {
            "task": request.task.strip(),
            "retrieval": "structured_rdf",
            "rules": rules,
            "prefixes": dict(sorted(self.prefixes.configuration.prefixes.items())),
            "modules": module_entries,
            "terms": term_entries,
            "similar_terms": [term.to_dict() for term in terms],
            "neighborhoods": neighborhoods,
            "shapes": sorted(shapes),
            "competency_questions": question_entries,
            "examples": self._example_paths("valid"),
            "counterexamples": self._example_paths("invalid"),
            "validation_commands": [
                "./scripts/validate.sh",
                "./scripts/test.sh",
            ],
            "limits": limits,
        }

    def _module_entry(self, module: ModuleDefinition) -> dict[str, object]:
        ontology = URIRef(f"{self.prefixes.configuration.base}ontology/{module.identifier}")
        imports = sorted(
            str(obj)
            for _, _, obj, _ in self.dataset.quads((ontology, OWL.imports, None, None))
            if isinstance(obj, URIRef)
        )
        return {
            "id": module.identifier,
            "graph": str(module.graph_iri),
            "source_path": module.source_path.as_posix(),
            "imports": imports,
        }

    def _selected_module_ids(
        self,
        requested_modules: tuple[str, ...],
        max_depth: int,
    ) -> frozenset[str]:
        if not requested_modules:
            return frozenset(module.identifier for module in self.modules)
        ontology_to_module = {
            f"{self.prefixes.configuration.base}ontology/{module.identifier}": module.identifier
            for module in self.modules
        }
        known = frozenset(ontology_to_module.values())
        selected = {module for module in requested_modules if module in known}
        queue = sorted((module, 0) for module in selected)
        cursor = 0
        while cursor < len(queue):
            module_id, depth = queue[cursor]
            cursor += 1
            if depth >= max_depth:
                continue
            ontology = URIRef(f"{self.prefixes.configuration.base}ontology/{module_id}")
            imported_ids = sorted(
                ontology_to_module[str(imported)]
                for _, _, imported, _ in self.dataset.quads((ontology, OWL.imports, None, None))
                if isinstance(imported, URIRef) and str(imported) in ontology_to_module
            )
            for imported_id in imported_ids:
                if imported_id in selected:
                    continue
                selected.add(imported_id)
                queue.append((imported_id, depth + 1))
        return frozenset(selected)

    def _example_paths(self, category: str) -> list[str]:
        root = self.knowledge_root / "examples" / category
        return [
            path.relative_to(self.knowledge_root).as_posix()
            for path in sorted(root.glob("*.ttl"))
            if path.is_file()
        ]

    @staticmethod
    def _task_tokens(task: str) -> tuple[str, ...]:
        return tuple(
            token.strip(".,:;!?()[]{}\"'")
            for token in task.split()
            if len(token.strip(".,:;!?()[]{}\"'")) >= 4
        )

    @staticmethod
    def _markdown(payload: dict[str, object]) -> str:
        sections = (
            ("Tarea", "task"),
            ("Recuperación", "retrieval"),
            ("Reglas", "rules"),
            ("Prefijos", "prefixes"),
            ("Módulos e imports", "modules"),
            ("Términos", "terms"),
            ("Términos similares", "similar_terms"),
            ("Vecindarios", "neighborhoods"),
            ("Shapes", "shapes"),
            ("Preguntas de competencia", "competency_questions"),
            ("Ejemplos", "examples"),
            ("Contraejemplos", "counterexamples"),
            ("Comandos de validación", "validation_commands"),
            ("Límites", "limits"),
        )
        lines = ["# Contexto de agente"]
        for title, key in sections:
            value = json.dumps(
                payload[key], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            lines.extend((f"\n## {title}", "```json", value, "```"))
        return "\n".join(lines) + "\n"

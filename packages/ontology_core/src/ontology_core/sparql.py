"""Strictly read-only SPARQL execution with bounded resources and no federation."""

from __future__ import annotations

import multiprocessing
from collections.abc import Mapping
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Any, cast
from typing import Literal as TypingLiteral

from rdflib import Dataset, Graph
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.term import Node

from ontology_core.prefixes import PrefixResolver
from ontology_core.query import RdfValue, _node_key

QueryKind = TypingLiteral["select", "ask", "construct", "describe"]
ALLOWED_OPERATIONS = {
    "SelectQuery": "select",
    "AskQuery": "ask",
    "ConstructQuery": "construct",
    "DescribeQuery": "describe",
}


class SparqlQueryError(ValueError):
    """A query is invalid, unsafe, timed out or exceeded its configured boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SparqlLimits:
    timeout_seconds: float = 5.0
    max_results: int = 1000
    max_query_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if not 0 < self.timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be greater than 0 and at most 60")
        if not 1 <= self.max_results <= 100_000:
            raise ValueError("max_results must be between 1 and 100000")
        if not 1 <= self.max_query_bytes <= 1024 * 1024:
            raise ValueError("max_query_bytes must be between 1 and 1048576")


@dataclass(frozen=True)
class SparqlResult:
    kind: QueryKind
    variables: tuple[str, ...] = ()
    rows: tuple[tuple[RdfValue | None, ...], ...] = ()
    boolean: bool | None = None
    triples: tuple[tuple[RdfValue, RdfValue, RdfValue], ...] = ()
    truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "variables": list(self.variables),
            "rows": [
                [value.to_dict() if value is not None else None for value in row]
                for row in self.rows
            ],
            "boolean": self.boolean,
            "triples": [
                [subject.to_dict(), predicate.to_dict(), obj.to_dict()]
                for subject, predicate, obj in self.triples
            ],
            "truncated": self.truncated,
        }


WorkerPayload = tuple[
    str,
    tuple[str, ...],
    tuple[tuple[Node | None, ...], ...],
    bool | None,
    tuple[tuple[Node, Node, Node], ...],
    bool,
]


def _contains_component(value: object, component_name: str) -> bool:
    if getattr(value, "name", None) == component_name:
        return True
    if type(value).__name__ == "ParseResults":
        sequence = cast(Any, value)
        return any(_contains_component(item, component_name) for item in sequence)
    if isinstance(value, Mapping):
        return any(_contains_component(item, component_name) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_component(item, component_name) for item in value)
    return False


def validate_read_only_query(query: str, limits: SparqlLimits) -> QueryKind:
    """Parse a query and enforce the exact read-only/federation-free allowlist."""

    if len(query.encode("utf-8")) > limits.max_query_bytes:
        raise SparqlQueryError("sparql.query_size", "query exceeds the configured byte limit")
    try:
        parsed: Any = parseQuery(query)
    except Exception as error:  # noqa: BLE001 - RDFLib exposes several parser exception types
        raise SparqlQueryError("sparql.syntax", f"invalid SPARQL query: {error}") from error
    if len(parsed) < 2:
        raise SparqlQueryError("sparql.operation", "SPARQL query has no operation")
    operation = getattr(parsed[1], "name", "")
    kind = ALLOWED_OPERATIONS.get(operation)
    if kind is None:
        raise SparqlQueryError(
            "sparql.operation",
            "only SELECT, ASK, CONSTRUCT and DESCRIBE queries are allowed",
        )
    if _contains_component(parsed, "ServiceGraphPattern"):
        raise SparqlQueryError("sparql.service", "SERVICE is not allowed")
    if _contains_component(parsed, "DatasetClause"):
        raise SparqlQueryError("sparql.dataset_clause", "FROM clauses are not allowed")
    return kind  # type: ignore[return-value]


def _query_worker(
    connection: Connection,
    serialized_dataset: str,
    query: str,
    kind: QueryKind,
    max_results: int,
) -> None:
    try:
        dataset = Dataset(default_union=True)
        dataset.parse(data=serialized_dataset, format="trig")
        result: Any = dataset.query(query)
        variables: tuple[str, ...] = ()
        rows: list[tuple[Node | None, ...]] = []
        boolean: bool | None = None
        triples: list[tuple[Node, Node, Node]] = []
        truncated = False
        if kind == "select":
            result_variables = tuple(result.vars or ())
            variables = tuple(str(variable) for variable in result_variables)
            for index, row in enumerate(result):
                if index >= max_results:
                    truncated = True
                    break
                rows.append(tuple(row.get(variable) for variable in result_variables))
        elif kind == "ask":
            boolean = bool(result.askAnswer)
        else:
            graph = result.graph
            if not isinstance(graph, Graph):
                raise ValueError("graph query returned no graph")
            ordered = sorted(graph, key=lambda triple: tuple(_node_key(node) for node in triple))
            triples.extend(ordered[:max_results])
            truncated = len(ordered) > max_results
        payload: WorkerPayload = (
            kind,
            variables,
            tuple(rows),
            boolean,
            tuple(triples),
            truncated,
        )
        connection.send(("ok", payload))
    except Exception as error:  # noqa: BLE001 - normalized at the process boundary
        connection.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


class ReadOnlySparqlService:
    """Execute bounded SPARQL queries over a disposable copy of the Dataset."""

    def __init__(
        self,
        dataset: Dataset,
        prefixes: PrefixResolver,
        *,
        limits: SparqlLimits | None = None,
    ) -> None:
        self.dataset = dataset
        self.prefixes = prefixes
        self.limits = limits or SparqlLimits()

    def execute(self, query: str) -> SparqlResult:
        kind = validate_read_only_query(query, self.limits)
        serialized = self.dataset.serialize(format="trig")
        start_method = "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
        process_context = multiprocessing.get_context(start_method)
        parent, child = process_context.Pipe(duplex=False)
        process = process_context.Process(  # type: ignore[attr-defined]
            target=_query_worker,
            args=(child, serialized, query, kind, self.limits.max_results),
            daemon=True,
        )
        process.start()
        child.close()
        try:
            if not parent.poll(self.limits.timeout_seconds):
                process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join()
                raise SparqlQueryError("sparql.timeout", "query exceeded the configured timeout")
            try:
                status, payload = parent.recv()
            except EOFError as error:
                raise SparqlQueryError(
                    "sparql.execution", "query process returned no result"
                ) from error
        finally:
            parent.close()
            process.join(timeout=0.05)
            if process.is_alive():
                process.terminate()
                process.join()
        if status != "ok":
            raise SparqlQueryError("sparql.execution", str(payload))
        if not isinstance(payload, tuple) or len(payload) != 6:
            raise SparqlQueryError("sparql.execution", "query process returned an invalid result")
        payload_kind, variables, raw_rows, boolean, raw_triples, truncated = payload
        if payload_kind != kind:
            raise SparqlQueryError("sparql.execution", "query result kind does not match request")
        return SparqlResult(
            kind=kind,
            variables=variables,
            rows=tuple(
                tuple(
                    RdfValue.from_node(value, self.prefixes) if value is not None else None
                    for value in row
                )
                for row in raw_rows
            ),
            boolean=boolean,
            triples=tuple(
                tuple(RdfValue.from_node(value, self.prefixes) for value in triple)  # type: ignore[misc]
                for triple in raw_triples
            ),
            truncated=bool(truncated),
        )

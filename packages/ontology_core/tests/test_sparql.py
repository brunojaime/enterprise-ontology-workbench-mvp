from __future__ import annotations

from pathlib import Path

import pytest
from ontology_core import (
    FilesystemRdfStore,
    ReadOnlySparqlService,
    SparqlLimits,
    SparqlQueryError,
)

ROOT = Path(__file__).parents[3]
BASE = "https://knowledge.example.com/"


def service(*, limits: SparqlLimits | None = None) -> ReadOnlySparqlService:
    store = FilesystemRdfStore(ROOT / "knowledge", ROOT / "config" / "namespace.yaml")
    return ReadOnlySparqlService(store.load(), store.prefixes, limits=limits)


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ("SELECT ?s WHERE { ?s a <http://www.w3.org/2002/07/owl#Class> }", "select"),
        ("ASK { ?s a <http://www.w3.org/2002/07/owl#Class> }", "ask"),
        (
            "CONSTRUCT { ?s a <http://www.w3.org/2002/07/owl#Class> } "
            "WHERE { ?s a <http://www.w3.org/2002/07/owl#Class> }",
            "construct",
        ),
        (
            f"DESCRIBE <{BASE}ontology/software#Application>",
            "describe",
        ),
    ],
)
def test_read_only_sparql_supports_only_the_four_query_forms(query: str, kind: str) -> None:
    result = service().execute(query)

    assert result.kind == kind
    assert result.rows or result.boolean is not None or result.triples


@pytest.mark.parametrize(
    "query",
    [
        "INSERT DATA { <urn:s> <urn:p> <urn:o> }",
        "DELETE WHERE { ?s ?p ?o }",
        "LOAD <https://remote.example/data>",
        "CLEAR ALL",
        "CREATE GRAPH <urn:g>",
    ],
)
def test_sparql_update_and_non_query_operations_are_blocked(query: str) -> None:
    with pytest.raises(SparqlQueryError) as error:
        service().execute(query)

    assert error.value.code in {"sparql.syntax", "sparql.operation"}


def test_service_and_remote_dataset_clauses_are_blocked_without_network_access() -> None:
    remote_service = "SELECT * WHERE { SERVICE <https://remote.example/sparql> { ?s ?p ?o } }"
    remote_from = "SELECT * FROM <https://remote.example/graph> WHERE { ?s ?p ?o }"

    with pytest.raises(SparqlQueryError) as service_error:
        service().execute(remote_service)
    with pytest.raises(SparqlQueryError) as dataset_error:
        service().execute(remote_from)

    assert service_error.value.code == "sparql.service"
    assert dataset_error.value.code == "sparql.dataset_clause"


def test_service_text_inside_a_literal_or_comment_is_not_a_false_positive() -> None:
    query = """
        # SERVICE <https://remote.example/sparql>
        SELECT ?message WHERE { VALUES ?message { "SERVICE is text" } }
    """

    result = service().execute(query)

    assert result.rows[0][0] is not None
    assert result.rows[0][0].value == "SERVICE is text"


def test_sparql_applies_deterministic_result_limit_and_reports_truncation() -> None:
    query = "SELECT ?s ?p ?o WHERE { GRAPH ?g { ?s ?p ?o } } ORDER BY ?s ?p ?o"
    bounded = service(limits=SparqlLimits(max_results=2)).execute(query)
    repeated = service(limits=SparqlLimits(max_results=2)).execute(query)

    assert len(bounded.rows) == 2
    assert bounded.truncated
    assert bounded.to_dict() == repeated.to_dict()


def test_sparql_ask_sees_the_union_without_collapsing_named_graphs() -> None:
    sparql = service()
    before = sparql.dataset.serialize(format="trig")

    result = sparql.execute(
        f"ASK {{ <{BASE}ontology/software#Application> a <http://www.w3.org/2002/07/owl#Class> }}"
    )

    assert result.boolean is True
    assert sparql.dataset.serialize(format="trig") == before
    assert len(sparql.dataset.default_graph) == 0


def test_sparql_enforces_query_size_timeout_and_configuration_bounds() -> None:
    with pytest.raises(SparqlQueryError) as size_error:
        service(limits=SparqlLimits(max_query_bytes=5)).execute("ASK { ?s ?p ?o }")
    with pytest.raises(SparqlQueryError) as timeout_error:
        service(limits=SparqlLimits(timeout_seconds=0.000001)).execute("ASK { ?s ?p ?o }")

    assert size_error.value.code == "sparql.query_size"
    assert timeout_error.value.code == "sparql.timeout"
    with pytest.raises(ValueError):
        SparqlLimits(max_results=0)
    with pytest.raises(ValueError):
        SparqlLimits(timeout_seconds=61)

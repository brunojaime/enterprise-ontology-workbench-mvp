from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from ontology_core import (
    CompetencyQuestionError,
    CompetencyQuestionRepository,
    CompetencyQuestionService,
    FilesystemRdfStore,
    ReadOnlySparqlService,
    SparqlLimits,
)
from rdflib import Literal, URIRef
from rdflib.namespace import RDF

ROOT = Path(__file__).parents[3]
BASE = "https://knowledge.example.com/"


def components(
    knowledge_root: Path = ROOT / "knowledge",
) -> tuple[FilesystemRdfStore, CompetencyQuestionRepository, CompetencyQuestionService]:
    store = FilesystemRdfStore(knowledge_root, ROOT / "config" / "namespace.yaml")
    dataset = store.load()
    repository = CompetencyQuestionRepository(dataset, BASE)
    service = CompetencyQuestionService(
        repository,
        ReadOnlySparqlService(dataset, store.prefixes),
        knowledge_root,
    )
    return store, repository, service


def test_questions_load_from_rdf_with_modules_states_and_optional_query_files() -> None:
    _, repository, _ = components()

    questions = repository.list()

    assert [question.iri.rsplit("/", 1)[-1] for question in questions] == [
        "applications_exist",
        "documented_only",
        "governed_knowledge_traceability",
        "missing_domain_fixture",
    ]
    assert all(question.text and question.module and question.state for question in questions)
    documented = next(question for question in questions if question.query_file is None)
    assert documented.acceptance_criterion
    assert repository.get(questions[0].iri) == questions[0]
    assert repository.get(f"{BASE}id/competency-question/missing") is None


def test_question_execution_produces_passed_failed_and_not_executable() -> None:
    _, _, service = components()

    results = service.execute_all()

    assert {result.question.iri.rsplit("/", 1)[-1]: result.status for result in results} == {
        "applications_exist": "passed",
        "documented_only": "not_executable",
        "governed_knowledge_traceability": "passed",
        "missing_domain_fixture": "failed",
    }
    assert all(result.reason for result in results)


def test_question_results_are_deterministic_and_do_not_mutate_named_graphs() -> None:
    store, _, service = components()
    before = set(store.dataset.quads((None, None, None, None)))

    first = [result.to_dict() for result in service.execute_all()]
    second = [result.to_dict() for result in service.execute_all()]

    assert first == second
    assert set(store.dataset.quads((None, None, None, None))) == before
    assert len(store.dataset.default_graph) == 0


def test_question_query_path_is_confined_and_service_is_never_executed(tmp_path: Path) -> None:
    copied = tmp_path / "knowledge"
    shutil.copytree(ROOT / "knowledge", copied)
    external = tmp_path / "external.rq"
    external.write_text("ASK { ?s ?p ?o }", encoding="utf-8")
    linked = copied / "competency_questions" / "queries" / "external.rq"
    linked.symlink_to(external)
    _, repository, service = components(copied)
    question = repository.list()[0]

    escaped = service.execute(replace(question, query_file="external.rq"))
    traversal = service.execute(replace(question, query_file="../questions.ttl"))

    assert escaped.status == "not_executable"
    assert traversal.status == "not_executable"
    assert "local .rq" in escaped.reason


def test_entire_query_directory_symlink_cannot_escape_knowledge(tmp_path: Path) -> None:
    copied = tmp_path / "knowledge"
    shutil.copytree(ROOT / "knowledge", copied)
    external_queries = tmp_path / "external-queries"
    external_queries.mkdir()
    (external_queries / "applications_exist.rq").write_text("ASK { ?s ?p ?o }", encoding="utf-8")
    query_root = copied / "competency_questions" / "queries"
    shutil.rmtree(query_root)
    query_root.symlink_to(external_queries, target_is_directory=True)
    _, repository, service = components(copied)

    result = service.execute(repository.list()[0])

    assert result.status == "not_executable"
    assert "directory" in result.reason and "knowledge" in result.reason


def test_unsafe_or_missing_query_is_not_executable(tmp_path: Path) -> None:
    copied = tmp_path / "knowledge"
    shutil.copytree(ROOT / "knowledge", copied)
    unsafe = copied / "competency_questions" / "queries" / "unsafe.rq"
    unsafe.write_text(
        "SELECT * WHERE { SERVICE <https://remote.example/sparql> { ?s ?p ?o } }",
        encoding="utf-8",
    )
    _, repository, service = components(copied)
    question = repository.list()[0]

    blocked = service.execute(replace(question, query_file="unsafe.rq"))
    missing = service.execute(replace(question, query_file="missing.rq"))

    assert blocked.status == "not_executable" and "SERVICE" in blocked.reason
    assert missing.status == "not_executable" and "not available" in missing.reason


def test_invalid_utf8_nul_path_and_non_regular_query_are_not_executable(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "knowledge"
    shutil.copytree(ROOT / "knowledge", copied)
    queries = copied / "competency_questions" / "queries"
    (queries / "invalid_utf8.rq").write_bytes(b"ASK { \xff }")
    (queries / "directory.rq").mkdir()
    _, repository, service = components(copied)
    question = repository.list()[0]

    invalid_utf8 = service.execute(replace(question, query_file="invalid_utf8.rq"))
    nul_path = service.execute(replace(question, query_file="invalid\x00path.rq"))
    directory = service.execute(replace(question, query_file="directory.rq"))

    assert invalid_utf8.status == "not_executable"
    assert "UTF-8" in invalid_utf8.reason
    assert nul_path.status == "not_executable"
    assert "not available" in nul_path.reason
    assert directory.status == "not_executable"
    assert "regular file" in directory.reason


def test_malformed_question_rdf_is_rejected_deterministically() -> None:
    store, repository, _ = components()
    question = URIRef(f"{BASE}id/competency-question/applications_exist")
    graph = store.dataset.graph(URIRef(f"{BASE}graph/competency-questions/questions"))
    graph.add((question, URIRef(f"{BASE}ontology/competency#questionText"), Literal("Duplicate")))
    malformed = CompetencyQuestionRepository(store.dataset, BASE)

    with pytest.raises(CompetencyQuestionError, match="exactly one"):
        malformed.list()


def test_non_boolean_expectation_is_rejected() -> None:
    store, _, _ = components()
    question = URIRef(f"{BASE}id/competency-question/applications_exist")
    graph = store.dataset.graph(URIRef(f"{BASE}graph/competency-questions/questions"))
    predicate = URIRef(f"{BASE}ontology/competency#expectedBoolean")
    graph.remove((question, predicate, None))
    graph.add((question, predicate, Literal("yes")))

    with pytest.raises(CompetencyQuestionError, match="boolean"):
        CompetencyQuestionRepository(store.dataset, BASE).list()


def test_question_requires_an_expected_result_or_acceptance_criterion() -> None:
    store, _, _ = components()
    question = URIRef(f"{BASE}id/competency-question/applications_exist")
    graph = store.dataset.graph(URIRef(f"{BASE}graph/competency-questions/questions"))
    graph.remove((question, URIRef(f"{BASE}ontology/competency#expectedBoolean"), None))

    with pytest.raises(CompetencyQuestionError, match="expected result or acceptanceCriterion"):
        CompetencyQuestionRepository(store.dataset, BASE).list()


def test_acceptance_criterion_must_be_a_non_empty_literal() -> None:
    store, _, _ = components()
    question = URIRef(f"{BASE}id/competency-question/documented_only")
    graph = store.dataset.graph(URIRef(f"{BASE}graph/competency-questions/questions"))
    predicate = URIRef(f"{BASE}ontology/competency#acceptanceCriterion")
    graph.remove((question, predicate, None))
    graph.add((question, predicate, Literal("   ")))

    with pytest.raises(CompetencyQuestionError, match="non-empty"):
        CompetencyQuestionRepository(store.dataset, BASE).list()


@pytest.mark.parametrize(
    ("query_file", "query"),
    [
        (
            "truncated_select.rq",
            "SELECT ?s WHERE { GRAPH ?g { ?s ?p ?o } }",
        ),
        (
            "truncated_construct.rq",
            "CONSTRUCT { ?s ?p ?o } WHERE { GRAPH ?g { ?s ?p ?o } }",
        ),
        (
            "truncated_describe.rq",
            "DESCRIBE ?s WHERE { GRAPH ?g { ?s ?p ?o } }",
        ),
    ],
)
def test_truncated_graph_or_row_results_are_inconclusive_below_the_threshold(
    tmp_path: Path, query_file: str, query: str
) -> None:
    copied = tmp_path / "knowledge"
    shutil.copytree(ROOT / "knowledge", copied)
    (copied / "competency_questions" / "queries" / query_file).write_text(query, encoding="utf-8")
    store = FilesystemRdfStore(copied, ROOT / "config" / "namespace.yaml")
    dataset = store.load()
    repository = CompetencyQuestionRepository(dataset, BASE)
    service = CompetencyQuestionService(
        repository,
        ReadOnlySparqlService(
            dataset,
            store.prefixes,
            limits=SparqlLimits(max_results=1),
        ),
        copied,
    )
    question = replace(
        repository.list()[0],
        query_file=query_file,
        expected_boolean=None,
        minimum_result_count=2,
        acceptance_criterion=None,
    )

    result = service.execute(question)

    assert result.status == "not_executable"
    assert result.result is not None and result.result.truncated
    assert "truncated" in result.reason


def test_truncated_result_can_pass_when_the_returned_prefix_meets_the_threshold(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "knowledge"
    shutil.copytree(ROOT / "knowledge", copied)
    query_file = "truncated_but_sufficient.rq"
    (copied / "competency_questions" / "queries" / query_file).write_text(
        "SELECT ?s WHERE { GRAPH ?g { ?s ?p ?o } }", encoding="utf-8"
    )
    store = FilesystemRdfStore(copied, ROOT / "config" / "namespace.yaml")
    dataset = store.load()
    repository = CompetencyQuestionRepository(dataset, BASE)
    service = CompetencyQuestionService(
        repository,
        ReadOnlySparqlService(dataset, store.prefixes, limits=SparqlLimits(max_results=1)),
        copied,
    )
    question = replace(
        repository.list()[0],
        query_file=query_file,
        expected_boolean=None,
        minimum_result_count=1,
        acceptance_criterion=None,
    )

    result = service.execute(question)

    assert result.status == "passed"
    assert result.result is not None and result.result.truncated


def test_question_type_is_present_in_the_loaded_dataset() -> None:
    store, _, _ = components()
    question_type = URIRef(f"{BASE}ontology/competency#CompetencyQuestion")

    assert any(store.dataset.quads((None, RDF.type, question_type, None)))

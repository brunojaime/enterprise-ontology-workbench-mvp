"""RDF-backed competency questions and deterministic execution outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal as TypingLiteral

from rdflib import Dataset, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF
from rdflib.term import Node

from ontology_core.sparql import ReadOnlySparqlService, SparqlQueryError, SparqlResult

QuestionStatus = TypingLiteral["passed", "failed", "not_executable"]


class CompetencyQuestionError(ValueError):
    """The RDF definition of a competency question is ambiguous or invalid."""


@dataclass(frozen=True)
class CompetencyQuestion:
    iri: str
    text: str
    module: str
    state: str
    query_file: str | None
    expected_boolean: bool | None
    minimum_result_count: int | None
    acceptance_criterion: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "iri": self.iri,
            "text": self.text,
            "module": self.module,
            "state": self.state,
            "query_file": self.query_file,
            "expected_boolean": self.expected_boolean,
            "minimum_result_count": self.minimum_result_count,
            "acceptance_criterion": self.acceptance_criterion,
        }


@dataclass(frozen=True)
class CompetencyQuestionResult:
    question: CompetencyQuestion
    status: QuestionStatus
    reason: str
    result: SparqlResult | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question.to_dict(),
            "status": self.status,
            "reason": self.reason,
            "result": self.result.to_dict() if self.result else None,
        }


class CompetencyQuestionRepository:
    """Read competency-question resources from the canonical Dataset."""

    def __init__(self, dataset: Dataset, base: str) -> None:
        self.dataset = dataset
        self.vocabulary = Namespace(f"{base}ontology/competency#")
        self.core = Namespace(f"{base}ontology/core#")

    def list(self) -> tuple[CompetencyQuestion, ...]:
        questions = {
            subject
            for subject, _, _, _ in self.dataset.quads(
                (None, RDF.type, self.vocabulary.CompetencyQuestion, None)
            )
            if isinstance(subject, URIRef)
        }
        return tuple(self._read(question) for question in sorted(questions, key=str))

    def get(self, iri: str) -> CompetencyQuestion | None:
        resource = URIRef(iri)
        if not any(
            True
            for _ in self.dataset.quads(
                (resource, RDF.type, self.vocabulary.CompetencyQuestion, None)
            )
        ):
            return None
        return self._read(resource)

    def _read(self, resource: URIRef) -> CompetencyQuestion:
        text = self._single(resource, self.vocabulary.questionText, required=True)
        module = self._single(resource, DCTERMS.isPartOf, required=True)
        state = self._single(resource, self.core.status, required=True)
        query_file = self._single(resource, self.vocabulary.queryFile)
        expected = self._single(resource, self.vocabulary.expectedBoolean)
        minimum = self._single(resource, self.vocabulary.minimumResultCount)
        criterion = self._single(resource, self.vocabulary.acceptanceCriterion)
        if not isinstance(text, Literal) or not str(text).strip():
            raise CompetencyQuestionError(f"{resource}: questionText must be non-empty")
        if not isinstance(module, URIRef):
            raise CompetencyQuestionError(f"{resource}: module must be an IRI")
        if not isinstance(state, Literal) or str(state) not in {"proposed", "active", "deprecated"}:
            raise CompetencyQuestionError(f"{resource}: invalid state")
        if query_file is not None and not isinstance(query_file, Literal):
            raise CompetencyQuestionError(f"{resource}: queryFile must be a literal")
        expected_boolean: bool | None = None
        if expected is not None:
            if not isinstance(expected, Literal) or not isinstance(expected.toPython(), bool):
                raise CompetencyQuestionError(f"{resource}: expectedBoolean must be boolean")
            expected_boolean = bool(expected.toPython())
        minimum_count: int | None = None
        if minimum is not None:
            parsed_minimum = minimum.toPython() if isinstance(minimum, Literal) else None
            if (
                not isinstance(parsed_minimum, int)
                or isinstance(parsed_minimum, bool)
                or parsed_minimum < 0
            ):
                raise CompetencyQuestionError(
                    f"{resource}: minimumResultCount must be a non-negative integer"
                )
            minimum_count = parsed_minimum
        acceptance_criterion: str | None = None
        if criterion is not None:
            if not isinstance(criterion, Literal) or not str(criterion).strip():
                raise CompetencyQuestionError(
                    f"{resource}: acceptanceCriterion must be a non-empty literal"
                )
            acceptance_criterion = str(criterion)
        if expected_boolean is None and minimum_count is None and acceptance_criterion is None:
            raise CompetencyQuestionError(
                f"{resource}: an expected result or acceptanceCriterion is required"
            )
        return CompetencyQuestion(
            iri=str(resource),
            text=str(text),
            module=str(module),
            state=str(state),
            query_file=str(query_file) if query_file is not None else None,
            expected_boolean=expected_boolean,
            minimum_result_count=minimum_count,
            acceptance_criterion=acceptance_criterion,
        )

    def _single(self, subject: Node, predicate: Node, *, required: bool = False) -> Node | None:
        values = {obj for _, _, obj, _ in self.dataset.quads((subject, predicate, None, None))}
        if len(values) > 1 or (required and not values):
            qualifier = "exactly one" if required else "at most one"
            raise CompetencyQuestionError(f"{subject}: {predicate} must have {qualifier} value")
        return next(iter(values), None)


class CompetencyQuestionService:
    """Execute local `.rq` associations through the shared read-only SPARQL service."""

    def __init__(
        self,
        repository: CompetencyQuestionRepository,
        sparql: ReadOnlySparqlService,
        knowledge_root: Path,
    ) -> None:
        self.repository = repository
        self.sparql = sparql
        self.knowledge_root = knowledge_root.resolve()
        self.query_root = self.knowledge_root / "competency_questions" / "queries"

    def execute(self, question: CompetencyQuestion) -> CompetencyQuestionResult:
        if question.query_file is None:
            return CompetencyQuestionResult(
                question=question,
                status="not_executable",
                reason="question has no associated query file",
            )
        try:
            query = self._read_query(question.query_file)
            result = self.sparql.execute(query)
        except (OSError, CompetencyQuestionError, SparqlQueryError) as error:
            return CompetencyQuestionResult(
                question=question,
                status="not_executable",
                reason=str(error),
            )
        accepted = self._accepted(question, result)
        if accepted is None:
            if result.truncated and question.minimum_result_count is not None:
                reason = "truncated result cannot determine the minimum-result expectation"
            else:
                reason = "question has no expectation compatible with its query form"
            return CompetencyQuestionResult(
                question=question,
                status="not_executable",
                reason=reason,
                result=result,
            )
        return CompetencyQuestionResult(
            question=question,
            status="passed" if accepted else "failed",
            reason="expectation satisfied" if accepted else "expectation not satisfied",
            result=result,
        )

    def execute_all(self) -> tuple[CompetencyQuestionResult, ...]:
        return tuple(self.execute(question) for question in self.repository.list())

    def _read_query(self, relative_path: str) -> str:
        try:
            resolved_root = self.query_root.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise CompetencyQuestionError(
                f"query file is not available: {relative_path}"
            ) from error
        if not resolved_root.is_relative_to(self.knowledge_root):
            raise CompetencyQuestionError(
                "query directory must remain inside the knowledge repository"
            )
        try:
            candidate = resolved_root / relative_path
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as error:
            raise CompetencyQuestionError(
                f"query file is not available: {relative_path}"
            ) from error
        if not resolved.is_relative_to(resolved_root) or resolved.suffix.lower() != ".rq":
            raise CompetencyQuestionError("query file must be a local .rq file inside queries/")
        try:
            if not resolved.is_file():
                raise CompetencyQuestionError("query target must be a regular file")
            if resolved.stat().st_size > self.sparql.limits.max_query_bytes:
                raise CompetencyQuestionError("query file exceeds the configured byte limit")
            return resolved.read_bytes().decode("utf-8")
        except UnicodeDecodeError as error:
            raise CompetencyQuestionError("query file must contain valid UTF-8") from error
        except OSError as error:
            raise CompetencyQuestionError(
                f"query file is not available: {relative_path}"
            ) from error

    @staticmethod
    def _accepted(question: CompetencyQuestion, result: SparqlResult) -> bool | None:
        if result.kind == "ask":
            if question.expected_boolean is None or result.boolean is None:
                return None
            return result.boolean is question.expected_boolean
        if question.minimum_result_count is None:
            return None
        count = len(result.rows) if result.kind == "select" else len(result.triples)
        if result.truncated and count < question.minimum_result_count:
            return None
        return count >= question.minimum_result_count

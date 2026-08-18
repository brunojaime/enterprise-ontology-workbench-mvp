"""Complete resource detail assembled from framework-independent query services."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib.term import IdentifiedNode

from ontology_core.impact import ImpactService
from ontology_core.query import OntologyQueryService, RdfValue, ResourceDescription


@dataclass(frozen=True)
class ResourceUsage:
    incoming_references: int
    outgoing_statements: int
    predicate_uses: int

    def to_dict(self) -> dict[str, int]:
        return {
            "incoming_references": self.incoming_references,
            "outgoing_statements": self.outgoing_statements,
            "predicate_uses": self.predicate_uses,
        }


@dataclass(frozen=True)
class ResourceDetail:
    description: ResourceDescription
    shapes: tuple[RdfValue, ...]
    usage: ResourceUsage

    def to_dict(self) -> dict[str, object]:
        payload = self.description.to_dict()
        payload["shapes"] = [value.to_dict() for value in self.shapes]
        payload["usage"] = self.usage.to_dict()
        return payload


class ResourceDetailService:
    """Combine description and impact without moving semantics into an adapter."""

    def __init__(self, query: OntologyQueryService, impact: ImpactService) -> None:
        if query.dataset is not impact.dataset or query.prefixes is not impact.prefixes:
            raise ValueError("resource detail requires query and impact from one snapshot")
        self.query = query
        self.impact = impact

    def describe(self, resource: str | IdentifiedNode) -> ResourceDetail | None:
        description = self.query.describe(resource)
        if description is None:
            return None
        impact = self.impact.analyze(resource)
        return ResourceDetail(
            description=description,
            shapes=impact.shapes,
            usage=ResourceUsage(
                incoming_references=len(impact.incoming),
                outgoing_statements=len(impact.outgoing),
                predicate_uses=len(impact.predicate_uses),
            ),
        )

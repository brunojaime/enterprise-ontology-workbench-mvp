"""Pure serialization helpers for the HTTP adapter."""

from ontology_core import RdfValue
from ontology_core.store import ModuleDefinition
from rdflib.term import Node

from enterprise_ontology_api.errors import ApiProblem
from enterprise_ontology_api.runtime import RuntimeSnapshot


def rdf_value(node: Node, snapshot: RuntimeSnapshot) -> dict[str, str]:
    return RdfValue.from_node(node, snapshot.store.prefixes).to_dict()


def module_definition(snapshot: RuntimeSnapshot, module_id: str) -> ModuleDefinition:
    module = next(
        (item for item in snapshot.context.modules if item.identifier == module_id),
        None,
    )
    if module is None:
        raise ApiProblem(
            404,
            "module.not_found",
            "The requested module does not exist.",
            details={"module_id": module_id},
        )
    return module


def module_payload(
    snapshot: RuntimeSnapshot,
    module: ModuleDefinition,
    *,
    term_offset: int = 0,
    term_limit: int = 20,
) -> dict[str, object]:
    description = next(
        item
        for item in snapshot.query.modules(snapshot.context.modules)
        if item.identifier == module.identifier
    )
    terms = sorted(
        (("class", value) for value in description.classes),
        key=lambda item: item[1].value,
    ) + sorted(
        (("property", value) for value in description.properties),
        key=lambda item: item[1].value,
    )
    selected = terms[term_offset : term_offset + term_limit]
    payload = description.to_dict()
    payload["classes"] = [value.to_dict() for category, value in selected if category == "class"]
    payload["properties"] = [
        value.to_dict() for category, value in selected if category == "property"
    ]
    payload["term_total"] = len(terms)
    payload["term_offset"] = term_offset
    payload["term_limit"] = term_limit
    payload["terms_has_next"] = term_offset + len(selected) < len(terms)
    return payload

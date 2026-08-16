from pathlib import Path

from ontology_core.forms import FormSchemaService
from ontology_core.store import FilesystemRdfStore
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, SH, XSD


def service() -> FormSchemaService:
    root = Path(__file__).resolve().parents[3]
    return FormSchemaService(FilesystemRdfStore(root / "knowledge", root / "config/namespace.yaml"))


def test_form_catalog_covers_every_editable_adr_type() -> None:
    schemas = service().schemas()
    assert [schema.kind for schema in schemas] == [
        "ontology",
        "class",
        "object_property",
        "datatype_property",
        "annotation_property",
        "individual",
        "concept",
        "node_shape",
        "competency_question",
    ]
    property_schema = next(schema for schema in schemas if schema.kind == "object_property")
    fields = {field.key: field for field in property_schema.fields}
    assert fields["label"].required is True
    assert fields["status"].allowed_values == ("proposed", "active", "deprecated")
    assert fields["direction"].required is True


def test_supported_shacl_subset_is_translated_to_typed_fields() -> None:
    graph = Graph()
    shape = URIRef("https://example.test/Shape")
    property_shape = BNode()
    allowed = BNode()
    graph.add((shape, RDF.type, SH.NodeShape))
    graph.add((shape, SH.targetClass, OWL.Class))
    graph.add((shape, SH.property, property_shape))
    graph.add((property_shape, SH.path, URIRef("https://example.test/riskLevel")))
    graph.add((property_shape, SH.minCount, Literal(2)))
    graph.add((property_shape, SH.maxCount, Literal(3)))
    graph.add((property_shape, SH.datatype, XSD.string))
    graph.add((property_shape, SH["in"], allowed))
    graph.add((property_shape, SH.name, Literal("Nivel de riesgo", lang="es")))
    graph.add((property_shape, SH.description, Literal("Clasificación controlada", lang="es")))
    graph.add((property_shape, SH.message, Literal("Seleccione un nivel", lang="es")))
    graph.add((property_shape, SH.severity, SH.Warning))
    graph.add((property_shape, SH.pattern, Literal("^(low|high)$")))
    Collection(graph, allowed, [Literal("low"), Literal("high")])

    schema = service().schema("class", shapes=graph)
    field = next(item for item in schema.fields if item.key == "riskLevel")
    assert field.input == "select"
    assert field.required is True
    assert field.multiple is True
    assert field.min_count == 2
    assert field.max_count == 3
    assert field.datatype == str(XSD.string)
    assert field.allowed_values == ("low", "high")
    assert field.pattern == "^(low|high)$"
    assert field.name == "Nivel de riesgo"
    assert field.description == "Clasificación controlada"
    assert field.message == "Seleccione un nivel"
    assert field.severity == str(SH.Warning)


def test_multiple_property_shapes_merge_to_the_strongest_exact_cardinality() -> None:
    graph = Graph()
    shape = URIRef("https://example.test/Shape")
    path = URIRef("https://example.test/reviewer")
    graph.add((shape, SH.targetClass, OWL.Class))
    for minimum, maximum in ((1, 5), (2, 3)):
        property_shape = BNode()
        graph.add((shape, SH.property, property_shape))
        graph.add((property_shape, SH.path, path))
        graph.add((property_shape, SH.minCount, Literal(minimum)))
        graph.add((property_shape, SH.maxCount, Literal(maximum)))

    field = next(
        item for item in service().schema("class", shapes=graph).fields if item.path == str(path)
    )

    assert field.min_count == 2
    assert field.max_count == 3
    assert field.required is True
    assert field.multiple is True

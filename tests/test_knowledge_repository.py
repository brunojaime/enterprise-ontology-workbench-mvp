from pathlib import Path

import pytest
from ontology_core import FilesystemRdfStore
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.exceptions import ParserError
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SH, SKOS, XSD

REPOSITORY_ROOT = Path(__file__).parents[1]
KNOWLEDGE_ROOT = REPOSITORY_ROOT / "knowledge"
EOW = Namespace("https://knowledge.example.com/ontology/core#")
MODULE = Namespace("https://knowledge.example.com/id/module/")


def assert_minimum_term_metadata(graph: Graph, subject: URIRef, module: URIRef) -> None:
    spanish_labels = {
        label for label in graph.objects(subject, SKOS.prefLabel) if label.language == "es"
    }
    spanish_definitions = {
        definition
        for definition in graph.objects(subject, SKOS.definition)
        if definition.language == "es"
    }

    assert spanish_labels
    assert spanish_definitions
    assert (subject, DCTERMS.isPartOf, module) in graph
    assert graph.value(subject, EOW.status) in {
        Literal("proposed"),
        Literal("active"),
        Literal("deprecated"),
    }
    assert graph.value(subject, DCTERMS.source) is not None
    assert graph.value(subject, DCTERMS.creator) is not None
    created = graph.value(subject, DCTERMS.created)
    assert isinstance(created, Literal)
    assert created.datatype == XSD.date


def assert_property_metadata(graph: Graph, subject: URIRef) -> None:
    assert graph.value(subject, SKOS.scopeNote) is not None
    assert graph.value(subject, SKOS.example) is not None
    assert graph.value(subject, RDFS.domain) is not None
    assert graph.value(subject, RDFS.range) is not None


def term_contract_defects(graph: Graph, subject: URIRef, *, property_term: bool) -> set[str]:
    defects: set[str] = set()
    if not any(label.language == "es" for label in graph.objects(subject, SKOS.prefLabel)):
        defects.add("spanish_label")
    if not any(
        definition.language == "es" for definition in graph.objects(subject, SKOS.definition)
    ):
        defects.add("definition")
    module = graph.value(subject, DCTERMS.isPartOf)
    if not isinstance(module, URIRef) or (module, RDF.type, EOW.OntologyModule) not in graph:
        defects.add("ownership")
    if graph.value(subject, EOW.status) not in {
        Literal("proposed"),
        Literal("active"),
        Literal("deprecated"),
    }:
        defects.add("status")
    if graph.value(subject, DCTERMS.source) is None:
        defects.add("evidence")
    if graph.value(subject, DCTERMS.creator) is None:
        defects.add("author")
    created = graph.value(subject, DCTERMS.created)
    if not isinstance(created, Literal) or created.datatype != XSD.date:
        defects.add("date")
    if property_term:
        if graph.value(subject, SKOS.scopeNote) is None:
            defects.add("direction")
        if graph.value(subject, SKOS.example) is None:
            defects.add("example")
        if graph.value(subject, RDFS.domain) is None:
            defects.add("domain")
        if graph.value(subject, RDFS.range) is None:
            defects.add("range")
    return defects


def aggregated_fixture_graph(extra_fixture: str | None = None) -> Graph:
    graph = Graph()
    canonical = FilesystemRdfStore(
        KNOWLEDGE_ROOT, REPOSITORY_ROOT / "config" / "namespace.yaml"
    ).load()
    for subject, predicate, obj, _ in canonical.quads((None, None, None, None)):
        graph.add((subject, predicate, obj))
    for path in sorted((KNOWLEDGE_ROOT / "examples" / "valid").glob("*.ttl")):
        graph.parse(path, format="turtle")
    if extra_fixture is not None:
        graph.parse(KNOWLEDGE_ROOT / "examples" / "invalid" / extra_fixture, format="turtle")
    return graph


def test_knowledge_directory_matches_plan_02_layout() -> None:
    expected_directories = {
        "ontology/core/terms",
        "ontology/organization/terms",
        "ontology/software/terms",
        "ontology/domains/example/terms",
        "shapes/modules",
        "data/sources",
        "competency_questions/queries",
        "examples/valid",
        "examples/invalid",
    }

    assert all((KNOWLEDGE_ROOT / relative).is_dir() for relative in expected_directories)
    assert (KNOWLEDGE_ROOT / "manifest.ttl").is_file()
    assert (KNOWLEDGE_ROOT / "ontology" / "core" / "terms" / ".gitkeep").is_file()


def test_core_module_contains_only_manifest_governance_terms() -> None:
    core_root = KNOWLEDGE_ROOT / "ontology" / "core"
    module_graph = Graph().parse(core_root / "module.ttl")
    term_files = tuple(sorted((core_root / "terms").glob("*.ttl")))
    graph = Graph()
    for term_file in term_files:
        graph.parse(term_file)
    namespace = "https://knowledge.example.com/ontology/core#"
    expected_terms = {
        "KnowledgeManifest",
        "OntologyModule",
        "manifestVersion",
        "namespaceBase",
        "module",
        "moduleId",
        "sourcePath",
        "graph",
        "status",
    }

    declared_terms = {
        str(subject).removeprefix(namespace)
        for subject in graph.subjects()
        if str(subject).startswith(namespace)
    }
    assert {path.stem for path in term_files} == expected_terms
    assert not {
        subject for subject in module_graph.subjects() if str(subject).startswith(namespace)
    }
    assert declared_terms == expected_terms

    term_types = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)
    for term_type in term_types:
        for subject in graph.subjects(RDF.type, term_type):
            assert isinstance(subject, URIRef)
            assert_minimum_term_metadata(graph, subject, MODULE.core)
            if term_type != OWL.Class:
                assert_property_metadata(graph, subject)


def test_core_module_has_ownership_metadata_and_is_the_import_root() -> None:
    graph = Graph().parse(KNOWLEDGE_ROOT / "ontology" / "core" / "module.ttl")
    ontology = URIRef("https://knowledge.example.com/ontology/core")

    assert (ontology, RDF.type, OWL.Ontology) in graph
    assert graph.value(ontology, DCTERMS.isPartOf) == MODULE.core
    assert graph.value(ontology, DCTERMS.rightsHolder) is not None
    assert graph.value(ontology, DCTERMS.creator) is not None
    assert graph.value(ontology, DCTERMS.source) is not None
    assert graph.value(ontology, EOW.status) == Literal("active")
    assert set(graph.objects(ontology, OWL.imports)) == set()
    assert "sin imports" in str(graph.value(ontology, DCTERMS.requires)).lower()


@pytest.mark.parametrize(
    ("module", "expected_imports"),
    [
        ("organization", {URIRef("https://knowledge.example.com/ontology/core")}),
        (
            "software",
            {
                URIRef("https://knowledge.example.com/ontology/core"),
                URIRef("https://knowledge.example.com/ontology/organization"),
            },
        ),
    ],
)
def test_domain_modules_have_ownership_metadata_and_explicit_imports(
    module: str, expected_imports: set[URIRef]
) -> None:
    graph = Graph().parse(KNOWLEDGE_ROOT / "ontology" / module / "module.ttl")
    ontology = URIRef(f"https://knowledge.example.com/ontology/{module}")

    assert (ontology, RDF.type, OWL.Ontology) in graph
    assert graph.value(ontology, DCTERMS.rightsHolder) is not None
    assert graph.value(ontology, DCTERMS.creator) is not None
    assert graph.value(ontology, DCTERMS.source) is not None
    assert graph.value(ontology, EOW.status) == Literal("active")
    assert graph.value(ontology, DCTERMS.isPartOf) == MODULE[module]
    created = graph.value(ontology, DCTERMS.created)
    assert isinstance(created, Literal) and created.datatype == XSD.date
    assert any(label.language == "es" for label in graph.objects(ontology, SKOS.prefLabel))
    definitions = tuple(graph.objects(ontology, SKOS.definition))
    assert any(definition.language == "es" for definition in definitions)
    assert any("Fixture mínimo" in str(definition) for definition in definitions)
    assert set(graph.objects(ontology, OWL.imports)) == expected_imports


def test_competency_vocabulary_has_governed_terms_for_question_contract() -> None:
    root = KNOWLEDGE_ROOT / "ontology" / "competency"
    graph = Graph().parse(root / "module.ttl")
    term_files = tuple(sorted((root / "terms").glob("*.ttl")))
    for term_file in term_files:
        graph.parse(term_file)
    expected_terms = {
        "CompetencyQuestion",
        "acceptanceCriterion",
        "expectedBoolean",
        "minimumResultCount",
        "queryFile",
        "questionText",
    }

    assert {path.stem for path in term_files} == expected_terms
    assert set(
        graph.objects(URIRef("https://knowledge.example.com/ontology/competency"), OWL.imports)
    ) == {URIRef("https://knowledge.example.com/ontology/core")}
    for name in expected_terms:
        term = URIRef(f"https://knowledge.example.com/ontology/competency#{name}")
        assert_minimum_term_metadata(graph, term, MODULE.competency)
        if name != "CompetencyQuestion":
            assert_property_metadata(graph, term)


@pytest.mark.parametrize(
    ("relative_path", "subject", "module", "is_property"),
    [
        (
            "ontology/organization/terms/OrganizationUnit.ttl",
            URIRef("https://knowledge.example.com/ontology/organization#OrganizationUnit"),
            MODULE.organization,
            False,
        ),
        (
            "ontology/software/terms/Application.ttl",
            URIRef("https://knowledge.example.com/ontology/software#Application"),
            MODULE.software,
            False,
        ),
        (
            "ontology/software/terms/supportsOrganizationUnit.ttl",
            URIRef("https://knowledge.example.com/ontology/software#supportsOrganizationUnit"),
            MODULE.software,
            True,
        ),
    ],
)
def test_module_fixture_terms_have_required_metadata(
    relative_path: str, subject: URIRef, module: URIRef, is_property: bool
) -> None:
    graph = Graph().parse(KNOWLEDGE_ROOT / relative_path)

    assert_minimum_term_metadata(graph, subject, module)
    if is_property:
        assert_property_metadata(graph, subject)


def parse_valid_fixture(name: str) -> Graph:
    return Graph().parse(KNOWLEDGE_ROOT / "examples" / "valid" / name, format="turtle")


@pytest.mark.parametrize(
    ("fixture", "subject", "rdf_type"),
    [
        ("class.ttl", "ExampleClass", OWL.Class),
        ("property.ttl", "exampleProperty", OWL.ObjectProperty),
        (
            "individual.ttl",
            "example_individual",
            URIRef("https://knowledge.example.com/example/valid/ExampleClass"),
        ),
        ("concept.ttl", "ExampleConcept", SKOS.Concept),
        ("shape.ttl", "ExampleShape", SH.NodeShape),
    ],
)
def test_valid_fixture_covers_required_resource_kind(
    fixture: str, subject: str, rdf_type: URIRef
) -> None:
    namespace = "https://knowledge.example.com/example/valid/"
    subject_iri = URIRef(f"{namespace}{subject}")
    graph = parse_valid_fixture(fixture)

    assert (subject_iri, RDF.type, rdf_type) in graph
    if rdf_type in {OWL.Class, OWL.ObjectProperty, SKOS.Concept}:
        assert_minimum_term_metadata(graph, subject_iri, MODULE.fixture)
    if rdf_type == OWL.ObjectProperty:
        assert_property_metadata(graph, subject_iri)


def test_valid_individual_and_shape_include_their_required_context() -> None:
    namespace = "https://knowledge.example.com/example/valid/"
    individual = URIRef(f"{namespace}example_individual")
    individual_graph = parse_valid_fixture("individual.ttl")
    shape = URIRef(f"{namespace}ExampleShape")
    shape_graph = parse_valid_fixture("shape.ttl")

    assert (individual, RDF.type, OWL.NamedIndividual) in individual_graph
    assert individual_graph.value(individual, DCTERMS.source) is not None
    assert shape_graph.value(shape, SH.name).language == "es"
    assert shape_graph.value(shape, SH.description).language == "es"


def test_valid_fixtures_form_one_complete_aggregate_with_a_defined_owner() -> None:
    graph = aggregated_fixture_graph()
    namespace = "https://knowledge.example.com/example/valid/"

    assert (MODULE.fixture, RDF.type, EOW.OntologyModule) in graph
    assert (
        term_contract_defects(graph, URIRef(f"{namespace}ExampleClass"), property_term=False)
        == set()
    )
    assert (
        term_contract_defects(graph, URIRef(f"{namespace}exampleProperty"), property_term=True)
        == set()
    )
    assert (
        term_contract_defects(graph, URIRef(f"{namespace}ExampleConcept"), property_term=False)
        == set()
    )


def test_semantically_invalid_fixture_is_parseable_and_covers_all_resource_kinds() -> None:
    graph = Graph().parse(
        KNOWLEDGE_ROOT / "examples" / "invalid" / "missing_governance_metadata.ttl",
        format="turtle",
    )
    namespace = "https://knowledge.example.com/example/invalid/"

    assert (URIRef(f"{namespace}ClassWithoutMetadata"), RDF.type, OWL.Class) in graph
    assert (URIRef(f"{namespace}propertyWithoutMetadata"), RDF.type, OWL.ObjectProperty) in graph
    assert (
        URIRef(f"{namespace}individualWithoutMetadata"),
        RDF.type,
        URIRef(f"{namespace}ClassWithoutMetadata"),
    ) in graph
    assert (URIRef(f"{namespace}conceptWithoutMetadata"), RDF.type, SKOS.Concept) in graph
    assert (URIRef(f"{namespace}shapeWithoutMetadata"), RDF.type, SH.NodeShape) in graph


def test_directed_invalid_fixtures_each_expose_the_intended_single_defect() -> None:
    namespace = "https://knowledge.example.com/example/invalid/"
    class_iri = URIRef(f"{namespace}ClassMissingDefinition")
    missing_definition = aggregated_fixture_graph("class_missing_definition.ttl")
    assert term_contract_defects(missing_definition, class_iri, property_term=False) == {
        "definition"
    }

    property_iri = URIRef(f"{namespace}propertyMissingDirection")
    missing_direction = aggregated_fixture_graph("property_missing_direction.ttl")
    assert term_contract_defects(missing_direction, property_iri, property_term=True) == {
        "direction"
    }

    concept_iri = URIRef(f"{namespace}ConceptInvalidStatus")
    invalid_status = aggregated_fixture_graph("concept_invalid_status.ttl")
    assert term_contract_defects(invalid_status, concept_iri, property_term=False) == {"status"}


def test_syntax_invalid_fixture_exercises_parser_failure() -> None:
    with pytest.raises((ParserError, SyntaxError)):
        Graph().parse(
            KNOWLEDGE_ROOT / "examples" / "invalid" / "syntax_error.ttl",
            format="turtle",
        )

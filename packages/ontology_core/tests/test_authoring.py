from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from ontology_core import FilesystemRdfStore, OntologyQueryService
from ontology_core.authoring import (
    AuthoringError,
    DeprecationDraft,
    IndividualDraft,
    RelationDraft,
    RelationIdentity,
    SearchConfirmation,
    TermDraft,
    TermWriter,
)
from ontology_core.diff import SemanticDiffService
from ontology_core.validation import ValidationService
from ontology_core.workspace import GitWorkspaceError, GitWorkspaceService
from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SH, SKOS, XSD

BASE = "https://knowledge.example.com/"


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def proposal_repository(tmp_path: Path) -> Path:
    source_root = Path(__file__).resolve().parents[3]
    root = tmp_path / "repository"
    root.mkdir()
    shutil.copytree(source_root / "knowledge", root / "knowledge")
    shutil.copytree(source_root / "config", root / "config")
    application_path = root / "knowledge/ontology/software/terms/Application.ttl"
    application_path.write_text(
        application_path.read_text(encoding="utf-8")
        + f'\n<{BASE}ontology/software#Application> <https://external.example/unknown> "keep" .\n',
        encoding="utf-8",
    )
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Test Author")
    git(root, "config", "user.email", "test@example.com")
    git(root, "add", "knowledge", "config")
    git(root, "commit", "-m", "chore: seed knowledge")
    git(root, "switch", "--create", "proposal/authoring")
    return root


def writer(repository: Path) -> TermWriter:
    store = FilesystemRdfStore(
        repository / "knowledge",
        repository / "config/namespace.yaml",
    )
    workspace = GitWorkspaceService(repository, repository / "knowledge")
    query = OntologyQueryService(store.load(), store.prefixes)
    return TermWriter(store, workspace, query)


def confirmed(service: TermWriter, query: str = "application") -> SearchConfirmation:
    assert service.search is not None
    receipt = service.search.search_page(query).search_id
    return SearchConfirmation(query=query, confirmed=True, search_id=receipt)


def add_plain_dynamic_shape(repository: Path, target_class: URIRef, suffix: str) -> URIRef:
    predicate = URIRef("https://external.example/note")
    shape = URIRef(f"https://external.example/shape/{suffix}")
    property_shape = BNode()
    graph = Graph()
    graph.add((shape, RDF.type, SH.NodeShape))
    graph.add((shape, SH.targetClass, target_class))
    graph.add((shape, SH.property, property_shape))
    graph.add((property_shape, SH.path, predicate))
    graph.add((property_shape, SH.name, Literal("Nota editable", lang="es")))
    path = repository / f"knowledge/shapes/modules/{suffix}.ttl"
    path.write_text(graph.serialize(format="turtle"), encoding="utf-8")
    return predicate


def add_opaque_dynamic_values(graph: Graph, subject: URIRef, predicate: URIRef) -> BNode:
    technical = BNode()
    graph.add((subject, predicate, Literal("editable note")))
    graph.add((subject, predicate, Literal("English note", lang="EN")))
    graph.add((subject, predicate, Literal("typed note", datatype=XSD.token)))
    graph.add((subject, predicate, URIRef("https://external.example/note/resource")))
    graph.add((subject, predicate, technical))
    graph.add(
        (
            technical,
            URIRef("https://external.example/detail"),
            Literal("technical child", datatype=XSD.string),
        )
    )
    return technical


def opaque_dynamic_subgraph(graph: Graph, subject: URIRef, predicate: URIRef) -> Graph:
    result = Graph()
    pending: list[BNode] = []
    for node in graph.objects(subject, predicate):
        if isinstance(node, Literal) and node.language is None and node.datatype is None:
            continue
        result.add((subject, predicate, node))
        if isinstance(node, BNode):
            pending.append(node)
    seen: set[BNode] = set()
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        for triple in graph.triples((node, None, None)):
            result.add(triple)
            if isinstance(triple[2], BNode):
                pending.append(triple[2])
    return result


def assert_dataset_semantics_equal(
    repository: Path,
    expected: Dataset,
    actual: Dataset,
) -> None:
    store = FilesystemRdfStore(repository / "knowledge", repository / "config/namespace.yaml")
    report = SemanticDiffService(store.prefixes).compare(
        expected,
        actual,
        base_ref="expected",
        head_ref="actual",
    )
    assert report.added_quads == ()
    assert report.removed_quads == ()


def graph_dataset(graph: Graph, graph_iri: URIRef) -> Dataset:
    dataset = Dataset()
    target = dataset.graph(graph_iri)
    for triple in graph:
        target.add(triple)
    return dataset


def test_term_writer_creates_one_file_and_preserves_unknown_triples(
    proposal_repository: Path,
) -> None:
    service = writer(proposal_repository)
    result = service.save_term(
        TermDraft(
            iri=f"{BASE}ontology/software#BusinessCapability",
            module_id="software",
            kind="class",
            preferred_label_es="Capacidad empresarial",
            alternative_labels_es=("Competencia empresarial",),
            definition_es="Capacidad mínima creada por una propuesta controlada.",
            evidence="Catálogo aprobado de capacidades",
            author="Test Author",
            search=confirmed(service, "capacidad empresarial"),
        )
    )
    assert result.path == "knowledge/ontology/software/terms/BusinessCapability.ttl"
    assert git(proposal_repository, "status", "--porcelain").split()[-1] == result.path
    created_graph = Graph().parse(proposal_repository / result.path, format="turtle")
    created_subject = URIRef(f"{BASE}ontology/software#BusinessCapability")
    assert (
        created_subject,
        SKOS.altLabel,
        Literal("Competencia empresarial", lang="es"),
    ) in created_graph

    application_path = proposal_repository / "knowledge/ontology/software/terms/Application.ttl"
    service.save_term(
        TermDraft(
            iri=f"{BASE}ontology/software#Application",
            module_id="software",
            kind="class",
            preferred_label_es="Aplicación empresarial",
            definition_es="Sistema identificable actualizado sin perder extensiones RDF.",
            evidence="Revisión del catálogo de aplicaciones",
            author="Test Author",
            search=confirmed(service),
        )
    )
    graph = Graph().parse(application_path, format="turtle")
    subject = URIRef(f"{BASE}ontology/software#Application")
    assert (subject, URIRef("https://external.example/unknown"), Literal("keep")) in graph
    assert (subject, SKOS.prefLabel, Literal("Aplicación empresarial", lang="es")) in graph


def test_term_writer_requires_search_definition_evidence_and_proposal_branch(
    proposal_repository: Path,
) -> None:
    git(proposal_repository, "switch", "main")
    service = writer(proposal_repository)
    draft = TermDraft(
        iri=f"{BASE}ontology/software#UnsafeClass",
        module_id="software",
        kind="class",
        preferred_label_es="Clase insegura",
        definition_es="No debe escribirse directamente sobre la rama publicada.",
        evidence="Fixture",
        author="Test Author",
        search=confirmed(service),
    )
    with pytest.raises(GitWorkspaceError) as protected:
        service.save_term(draft)
    assert protected.value.code == "git.protected_branch"
    assert not (proposal_repository / "knowledge/ontology/software/terms/UnsafeClass.ttl").exists()

    git(proposal_repository, "switch", "proposal/authoring")
    with pytest.raises(AuthoringError) as missing_search:
        service.save_term(replace(draft, search=SearchConfirmation("", False)))
    assert missing_search.value.code == "authoring.search_required"

    with pytest.raises(AuthoringError) as mismatched_search:
        service.save_term(
            replace(
                draft,
                search=SearchConfirmation(
                    "otra consulta",
                    True,
                    service.search.search_page("consulta original").search_id,
                ),
            )
        )
    assert mismatched_search.value.code == "authoring.invalid_search_id"

    assert service.search is not None
    filtered_receipt = service.search.search_page(
        "clase insegura",
        modules=frozenset(("missing-module",)),
    ).search_id
    with pytest.raises(AuthoringError) as filtered_search:
        service.save_term(
            replace(
                draft,
                search=SearchConfirmation("clase insegura", True, filtered_receipt),
            )
        )
    assert filtered_search.value.code == "authoring.invalid_search_id"

    displaced_receipt = service.search.search_page(
        "clase insegura",
        offset=999,
    ).search_id
    with pytest.raises(AuthoringError) as displaced_search:
        service.save_term(
            replace(
                draft,
                search=SearchConfirmation("clase insegura", True, displaced_receipt),
            )
        )
    assert displaced_search.value.code == "authoring.invalid_search_id"
    assert not (proposal_repository / "knowledge/ontology/software/terms/UnsafeClass.ttl").exists()


def test_property_individual_relation_and_deprecation_flows(
    proposal_repository: Path,
) -> None:
    (proposal_repository / "knowledge/shapes/modules/individual_reviewer_fixture.ttl").write_text(
        """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix fixture: <https://fixtures.example/reviewer#> .
<https://knowledge.example.com/shape/software/IndividualReviewerFixtureShape>
  a sh:NodeShape ;
  sh:targetClass owl:NamedIndividual ;
  sh:property [ sh:path fixture:reviewer ; sh:maxCount 2 ; sh:datatype xsd:string ] .
""",
        encoding="utf-8",
    )
    service = writer(proposal_repository)
    property_result = service.save_term(
        TermDraft(
            iri=f"{BASE}ontology/software#hasBusinessOwner",
            module_id="software",
            kind="object_property",
            preferred_label_es="tiene responsable empresarial",
            alternative_labels_es=("asigna responsable",),
            definition_es="Relaciona una aplicación con la unidad que asume su responsabilidad.",
            evidence="Matriz de responsabilidades del fixture",
            author="Test Author",
            search=confirmed(service, "responsable empresarial"),
            reading_direction_es="Se lee desde la aplicación hacia la unidad responsable.",
            valid_example="app:workbench software:hasBusinessOwner orgid:architecture .",
            domain=f"{BASE}ontology/software#Application",
            range=f"{BASE}ontology/organization#OrganizationUnit",
        )
    )
    assert property_result.operation == "created"
    property_graph = Graph().parse(proposal_repository / property_result.path, format="turtle")
    assert (
        URIRef(f"{BASE}ontology/software#hasBusinessOwner"),
        SKOS.altLabel,
        Literal("asigna responsable", lang="es"),
    ) in property_graph

    individual_result = service.save_individual(
        IndividualDraft(
            iri=f"{BASE}id/software/application/catalog",
            class_iri=f"{BASE}ontology/software#Application",
            source_id="catalog_fixture",
            preferred_label_es="Catálogo (fixture)",
            alternative_labels_es=("Catálogo aplicativo",),
            evidence="Inventario sintético controlado",
            author="Test Author",
            search=confirmed(service, "catálogo"),
            form_values=(("reviewer", ("Ada", "Grace")),),
        )
    )
    assert individual_result.path.endswith("data/sources/proposals/catalog_fixture.ttl")
    individual_graph = Graph().parse(proposal_repository / individual_result.path, format="turtle")
    individual = URIRef(f"{BASE}id/software/application/catalog")
    assert (individual, RDF.type, OWL.NamedIndividual) in individual_graph
    assert (individual, DCTERMS.source, None) in individual_graph
    assert (
        individual,
        SKOS.altLabel,
        Literal("Catálogo aplicativo", lang="es"),
    ) in individual_graph
    assert service.editable_resource(str(individual)).alternative_labels_es == (
        "Catálogo aplicativo",
    )
    assert set(
        individual_graph.objects(individual, URIRef("https://fixtures.example/reviewer#reviewer"))
    ) == {
        Literal("Ada", datatype=XSD.string),
        Literal("Grace", datatype=XSD.string),
    }
    assert dict(service.editable_resource(str(individual)).form_values)["reviewer"] == (
        "Ada",
        "Grace",
    )

    relation_result = service.save_relation(
        RelationDraft(
            subject=f"{BASE}id/software/application/catalog",
            predicate=f"{BASE}ontology/software#hasBusinessOwner",
            object_iri=f"{BASE}id/organization/unit/architecture",
            literal=None,
            datatype=None,
            language=None,
            evidence="Inventario sintético confirmado",
        )
    )
    assert relation_result.path.endswith("catalog_fixture.ttl")
    assert ValidationService(service.store).validate_repository().conforms is True

    deprecated = service.deprecate(
        DeprecationDraft(
            iri=f"{BASE}ontology/software#Application",
            reason="Reemplazada por una taxonomía más precisa.",
            replacement_iri=f"{BASE}ontology/organization#OrganizationUnit",
        )
    )
    application_path = proposal_repository / deprecated.path
    assert application_path.exists()
    graph = Graph().parse(application_path, format="turtle")
    application = URIRef(f"{BASE}ontology/software#Application")
    assert (application, OWL.deprecated, Literal(True)) in graph
    assert (
        application,
        URIRef(str(DCTERMS.isReplacedBy)),
        URIRef(f"{BASE}ontology/organization#OrganizationUnit"),
    ) in graph


def test_relation_rejects_incompatible_object_and_writer_rejects_symlink_escape(
    proposal_repository: Path,
    tmp_path: Path,
) -> None:
    service = writer(proposal_repository)
    with pytest.raises(AuthoringError) as mismatch:
        service.save_relation(
            RelationDraft(
                subject=f"{BASE}id/software/application/workbench",
                predicate=f"{BASE}ontology/software#supportsOrganizationUnit",
                object_iri=None,
                literal="Arquitectura",
                datatype=str(XSD.string),
                language=None,
                evidence="Fixture",
            )
        )
    assert mismatch.value.code == "authoring.object_type_mismatch"

    external = tmp_path / "external"
    external.mkdir()
    terms = proposal_repository / "knowledge/ontology/software/terms"
    escaped = terms / "EscapedClass.ttl"
    escaped.symlink_to(external / "escaped.ttl")
    with pytest.raises(AuthoringError) as unsafe:
        service.save_term(
            TermDraft(
                iri=f"{BASE}ontology/software#EscapedClass",
                module_id="software",
                kind="class",
                preferred_label_es="Clase escapada",
                definition_es="Caso adversarial de confinamiento de rutas.",
                evidence="Fixture",
                author="Test Author",
                search=confirmed(service, "escapada"),
            )
        )
    assert unsafe.value.code == "authoring.unsafe_path"


def test_relation_validates_the_exact_reified_post_write_dataset_without_mutation(
    proposal_repository: Path,
) -> None:
    service = writer(proposal_repository)
    service.save_individual(
        IndividualDraft(
            iri=f"{BASE}id/software/application/reified_validation",
            class_iri=f"{BASE}ontology/software#Application",
            source_id="reified_validation",
            preferred_label_es="Validación reificada",
            evidence="Fixture de relación exacta",
            author="Test Author",
            search=confirmed(service, "validación reificada"),
        )
    )
    subject = URIRef(f"{BASE}id/software/application/reified_validation")
    predicate = URIRef(f"{BASE}ontology/software#supportsOrganizationUnit")
    obj = URIRef(f"{BASE}id/organization/unit/architecture")
    assertion = service._statement_iri(subject, predicate, obj)
    shape_path = proposal_repository / "knowledge/shapes/modules/relation_evidence_fixture.ttl"
    shape_path.write_text(
        f"""@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
<https://knowledge.example.com/shape/relation/EvidenceShape> a sh:NodeShape ;
  sh:targetNode <{assertion}> ;
  sh:property [ sh:path dcterms:source ; sh:minLength 100 ] .
""",
        encoding="utf-8",
    )
    path = proposal_repository / "knowledge/data/sources/proposals/reified_validation.ttl"
    before = path.read_bytes()

    with pytest.raises(AuthoringError) as invalid:
        service.save_relation(
            RelationDraft(
                subject=f"{BASE}id/software/application/reified_validation",
                predicate=f"{BASE}ontology/software#supportsOrganizationUnit",
                object_iri=f"{BASE}id/organization/unit/architecture",
                literal=None,
                datatype=None,
                language=None,
                evidence="corta",
            )
        )

    assert invalid.value.code == "authoring.relation_validation_failed"
    assert path.read_bytes() == before
    assert ValidationService(service.store).validate_repository().conforms is True


@pytest.mark.parametrize(
    ("kind", "local_name"),
    [
        ("concept", "ArchitectureConcept"),
        ("datatype_property", "applicationCode"),
        ("annotation_property", "reviewNote"),
    ],
)
def test_supported_term_forms_are_written_with_their_exact_rdf_type(
    proposal_repository: Path,
    kind: str,
    local_name: str,
) -> None:
    service = writer(proposal_repository)
    property_fields = kind.endswith("property")
    result = service.save_term(
        TermDraft(
            iri=f"{BASE}ontology/software#{local_name}",
            module_id="software",
            kind=kind,  # type: ignore[arg-type]
            preferred_label_es=f"{kind} de fixture",
            alternative_labels_es=(f"alias {kind}",),
            definition_es="Definición dirigida para probar el formulario soportado.",
            evidence="Fixture dirigido de formularios P07",
            author="Test Author",
            search=confirmed(service, local_name),
            reading_direction_es="Se lee desde el recurso hacia su valor."
            if property_fields
            else None,
            valid_example=f'software:Application software:{local_name} "x" .'
            if property_fields
            else None,
        )
    )
    graph = Graph().parse(proposal_repository / result.path, format="turtle")
    expected = {
        "concept": SKOS.Concept,
        "datatype_property": OWL.DatatypeProperty,
        "annotation_property": OWL.AnnotationProperty,
    }[kind]
    subject = URIRef(f"{BASE}ontology/software#{local_name}")
    assert (subject, RDF.type, expected) in graph
    assert (subject, SKOS.altLabel, Literal(f"alias {kind}", lang="es")) in graph
    assert service.editable_resource(str(subject)).alternative_labels_es == (f"alias {kind}",)


def test_only_a_relation_marked_as_draft_can_be_deleted(proposal_repository: Path) -> None:
    service = writer(proposal_repository)
    published_identity = RelationIdentity(
        subject=f"{BASE}id/software/application/workbench",
        predicate=f"{BASE}ontology/software#supportsOrganizationUnit",
        object_iri=f"{BASE}id/organization/unit/architecture",
        literal=None,
    )
    with pytest.raises(AuthoringError) as published:
        service.delete_draft_relation(published_identity)
    assert published.value.code == "authoring.published_relation"
    with pytest.raises(AuthoringError) as duplicate:
        service.save_relation(
            RelationDraft(
                **published_identity.__dict__,
                evidence="No puede convertir conocimiento publicado en draft",
                status="proposed",
            )
        )
    assert duplicate.value.code == "authoring.relation_exists"

    service.save_individual(
        IndividualDraft(
            iri=f"{BASE}id/software/application/draft_catalog",
            class_iri=f"{BASE}ontology/software#Application",
            source_id="draft_relations",
            preferred_label_es="Catálogo de propuesta",
            evidence="Fixture dirigido",
            author="Test Author",
            search=confirmed(service, "catálogo de propuesta"),
        )
    )
    identity = RelationIdentity(
        subject=f"{BASE}id/software/application/draft_catalog",
        predicate=f"{BASE}ontology/software#supportsOrganizationUnit",
        object_iri=f"{BASE}id/organization/unit/architecture",
        literal=None,
    )

    service.save_relation(
        RelationDraft(
            **identity.__dict__,
            evidence="Fixture dirigido de relación",
            status="proposed",
        )
    )
    deleted = service.delete_draft_relation(identity)
    assert deleted.operation == "draft_relation_deleted"
    document = Graph().parse(proposal_repository / deleted.path, format="turtle")
    assert (
        URIRef(identity.subject),
        URIRef(identity.predicate),
        URIRef(identity.object_iri or ""),
    ) not in document


def test_proposed_relation_from_published_subject_uses_a_proposal_named_graph(
    proposal_repository: Path,
) -> None:
    service = writer(proposal_repository)
    component = f"{BASE}id/software/component/proposal_graph_fixture"
    service.save_individual(
        IndividualDraft(
            iri=component,
            class_iri=f"{BASE}ontology/software#SoftwareComponent",
            source_id="proposal_graph_fixture",
            preferred_label_es="Componente para graph de propuesta",
            evidence="Fixture adversarial de separación de estados",
            author="Test Author",
            search=confirmed(service, "componente para graph de propuesta"),
        )
    )
    subject = URIRef(f"{BASE}id/software/application/workbench")
    predicate = URIRef(f"{BASE}ontology/software#isComposedOf")
    obj = URIRef(component)

    result = service.save_relation(
        RelationDraft(
            subject=str(subject),
            predicate=str(predicate),
            object_iri=str(obj),
            literal=None,
            datatype=None,
            language=None,
            evidence="Fixture adversarial de separación de named graphs",
        )
    )

    document = Dataset().parse(proposal_repository / result.path, format="trig")
    published_graph = URIRef(f"{BASE}graph/source/fixture_inventory")
    proposal_graph = URIRef(f"{BASE}graph/proposal/authoring/fixture_inventory")
    metadata_graph = URIRef(f"{BASE}graph/metadata/proposal/authoring/fixture_inventory")
    assert (subject, predicate, obj) not in document.graph(published_graph)
    assert (subject, predicate, obj) in document.graph(proposal_graph)
    assert (proposal_graph, RDF.type, URIRef("http://www.w3.org/ns/prov#Entity")) in document.graph(
        metadata_graph
    )
    assert (
        proposal_graph,
        URIRef(f"{BASE}ontology/core#status"),
        Literal("proposed"),
    ) in document.graph(metadata_graph)
    assert ValidationService(service.store).validate_repository().conforms is True


def test_individual_iri_cannot_be_duplicated_across_sources(
    proposal_repository: Path,
) -> None:
    service = writer(proposal_repository)
    draft = IndividualDraft(
        iri=f"{BASE}id/software/application/unique_fixture",
        class_iri=f"{BASE}ontology/software#Application",
        source_id="source_one",
        preferred_label_es="Individuo único",
        evidence="Fixture dirigido",
        author="Test Author",
        search=confirmed(service, "individuo único"),
    )
    service.save_individual(draft)
    with pytest.raises(AuthoringError) as duplicate:
        service.save_individual(replace(draft, source_id="source_two"))
    assert duplicate.value.code == "authoring.duplicate_individual_iri"
    assert not (proposal_repository / "knowledge/data/sources/proposals/source_two.ttl").exists()


def test_existing_property_cannot_be_implicitly_converted_to_class(
    proposal_repository: Path,
) -> None:
    service = writer(proposal_repository)
    iri = f"{BASE}ontology/software#supportsOrganizationUnit"
    with pytest.raises(AuthoringError) as mismatch:
        service.save_term(
            TermDraft(
                iri=iri,
                module_id="software",
                kind="class",
                preferred_label_es="Relación convertida",
                definition_es="Conversión inválida dirigida.",
                evidence="Fixture adversarial",
                author="Test Author",
                search=confirmed(service, "supports organization unit"),
            )
        )
    assert mismatch.value.code == "authoring.kind_mismatch"
    graph = Graph().parse(
        proposal_repository / "knowledge/ontology/software/terms/supportsOrganizationUnit.ttl",
        format="turtle",
    )
    subject = URIRef(iri)
    assert (subject, RDF.type, OWL.ObjectProperty) in graph
    assert (subject, SKOS.scopeNote, None) in graph


def test_editable_property_round_trip_hydrates_and_preserves_exact_semantics(
    proposal_repository: Path,
) -> None:
    service = writer(proposal_repository)
    iri = f"{BASE}ontology/software#supportsOrganizationUnit"
    state = service.editable_resource(iri)

    assert state.kind == "object_property"
    assert state.module_id == "software"
    assert state.status == "active"
    assert state.reading_direction_es
    assert state.valid_example
    assert state.domain == f"{BASE}ontology/software#Application"
    assert state.range == f"{BASE}ontology/organization#OrganizationUnit"
    assert state.path.endswith("supportsOrganizationUnit.ttl")

    service.save_term(
        TermDraft(
            iri=state.iri,
            module_id=state.module_id,
            kind="object_property",
            preferred_label_es=state.preferred_label_es,
            alternative_labels_es=state.alternative_labels_es,
            definition_es=state.definition_es,
            evidence=state.evidence,
            author=state.author,
            search=confirmed(service, "supports organization unit"),
            status="active",
            reading_direction_es=state.reading_direction_es,
            valid_example=state.valid_example,
            domain=state.domain,
            range=state.range,
        )
    )
    graph = Graph().parse(proposal_repository / state.path, format="turtle")
    subject = URIRef(iri)
    assert (subject, RDF.type, OWL.ObjectProperty) in graph
    assert (subject, RDF.type, OWL.Class) not in graph
    assert (subject, SKOS.scopeNote, Literal(state.reading_direction_es, lang="es")) in graph
    assert (subject, RDFS.domain, URIRef(state.domain)) in graph
    assert (subject, RDFS.range, URIRef(state.range)) in graph


def test_partial_term_edit_preserves_other_languages_created_and_typed_extensions(
    proposal_repository: Path,
) -> None:
    path = proposal_repository / "knowledge/ontology/software/terms/Application.ttl"
    subject = URIRef(f"{BASE}ontology/software#Application")
    extension = URIRef("https://external.example/reviewScore")
    graph = Graph().parse(path, format="turtle")
    created = tuple(graph.objects(subject, DCTERMS.created))
    graph.add((subject, SKOS.prefLabel, Literal("Application", lang="en")))
    graph.add((subject, SKOS.altLabel, Literal("Business application", lang="en")))
    graph.add(
        (
            subject,
            SKOS.definition,
            Literal("An application retained across a partial edit.", lang="en"),
        )
    )
    graph.add((subject, extension, Literal("7", datatype=XSD.integer)))
    path.write_text(graph.serialize(format="turtle"), encoding="utf-8")

    service = writer(proposal_repository)
    state = service.editable_resource(str(subject))
    service.save_term(
        TermDraft(
            iri=state.iri,
            module_id=state.module_id,
            kind="class",
            preferred_label_es="Aplicación empresarial revisada",
            alternative_labels_es=state.alternative_labels_es,
            definition_es=state.definition_es,
            evidence=state.evidence,
            author=state.author,
            search=confirmed(service, "aplicación empresarial"),
            status="active",
        )
    )

    updated = Graph().parse(path, format="turtle")
    assert (
        subject,
        SKOS.prefLabel,
        Literal("Aplicación empresarial revisada", lang="es"),
    ) in updated
    assert (subject, SKOS.prefLabel, Literal("Application", lang="en")) in updated
    assert (subject, SKOS.altLabel, Literal("Business application", lang="en")) in updated
    assert (
        subject,
        SKOS.definition,
        Literal("An application retained across a partial edit.", lang="en"),
    ) in updated
    assert tuple(updated.objects(subject, DCTERMS.created)) == created
    assert (subject, DCTERMS.modified, None) in updated
    assert (subject, extension, Literal("7", datatype=XSD.integer)) in updated


def test_term_dynamic_field_replaces_only_exactly_representable_nodes(
    proposal_repository: Path,
) -> None:
    predicate = add_plain_dynamic_shape(proposal_repository, OWL.Class, "class_opaque_note")
    path = proposal_repository / "knowledge/ontology/software/terms/Application.ttl"
    subject = URIRef(f"{BASE}ontology/software#Application")
    graph = Graph().parse(path, format="turtle")
    add_opaque_dynamic_values(graph, subject, predicate)
    graph.add((subject, SKOS.altLabel, Literal("Etiqueta histórica", lang="ES")))
    opaque_before = opaque_dynamic_subgraph(graph, subject, predicate)
    path.write_text(graph.serialize(format="turtle"), encoding="utf-8")

    expected = graph_dataset(graph, URIRef("urn:test:term-document"))
    expected_graph = expected.graph(URIRef("urn:test:term-document"))
    expected_graph.remove((subject, predicate, Literal("editable note")))
    expected_graph.add((subject, predicate, Literal("updated note")))
    for value in tuple(expected_graph.objects(subject, SKOS.altLabel)):
        if isinstance(value, Literal) and value.language and value.language.casefold() == "es":
            expected_graph.remove((subject, SKOS.altLabel, value))
    expected_graph.add((subject, SKOS.altLabel, Literal("Etiqueta actualizada", lang="es")))
    expected_graph.remove((subject, DCTERMS.modified, None))
    expected_graph.add(
        (subject, DCTERMS.modified, Literal(date.today().isoformat(), datatype=XSD.date))
    )

    service = writer(proposal_repository)
    state = service.editable_resource(str(subject))
    assert dict(state.form_values)["note"] == ("editable note",)
    service.save_term(
        TermDraft(
            iri=state.iri,
            module_id=state.module_id,
            kind="class",
            preferred_label_es=state.preferred_label_es,
            alternative_labels_es=("Etiqueta actualizada",),
            definition_es=state.definition_es,
            evidence=state.evidence,
            author=state.author,
            search=confirmed(service, "application dynamic note"),
            status="active",
            form_values=(("note", ("updated note",)),),
        )
    )

    updated = Graph().parse(path, format="turtle")
    assert (subject, predicate, Literal("editable note")) not in updated
    assert (subject, predicate, Literal("updated note")) in updated
    assert isomorphic(opaque_before, opaque_dynamic_subgraph(updated, subject, predicate))
    assert (subject, SKOS.altLabel, Literal("Etiqueta histórica", lang="ES")) not in updated
    assert (subject, SKOS.altLabel, Literal("Etiqueta actualizada", lang="es")) in updated
    assert_dataset_semantics_equal(
        proposal_repository,
        expected,
        graph_dataset(updated, URIRef("urn:test:term-document")),
    )


def test_existing_individual_updates_its_responsible_named_graph(
    proposal_repository: Path,
) -> None:
    service = writer(proposal_repository)
    iri = f"{BASE}id/organization/unit/architecture"
    state = service.editable_resource(iri)
    assert state.kind == "individual"
    assert state.class_iri == f"{BASE}ontology/organization#OrganizationUnit"
    assert state.source_id == "fixture_inventory"

    service.save_individual(
        IndividualDraft(
            iri=iri,
            class_iri=state.class_iri,
            source_id=state.source_id,
            preferred_label_es=state.preferred_label_es,
            evidence="Inventario sintético controlado",
            author="Test Author",
            search=confirmed(service, "arquitectura fixture"),
            status="active",
        )
    )
    dataset = FilesystemRdfStore(
        proposal_repository / "knowledge",
        proposal_repository / "config/namespace.yaml",
    ).load()
    subject = URIRef(iri)
    graph = URIRef(f"{BASE}graph/source/fixture_inventory")
    assert (subject, RDF.type, OWL.NamedIndividual, graph) in dataset
    assert (
        URIRef(f"{BASE}id/software/application/workbench"),
        URIRef(f"{BASE}ontology/software#supportsOrganizationUnit"),
        subject,
        graph,
    ) in dataset


def test_individual_noop_edit_preserves_multilingual_values_and_named_graph(
    proposal_repository: Path,
) -> None:
    path = proposal_repository / "knowledge/data/sources/fixture_inventory.trig"
    subject = URIRef(f"{BASE}id/organization/unit/architecture")
    graph_iri = URIRef(f"{BASE}graph/source/fixture_inventory")
    metadata_graph = URIRef(f"{BASE}graph/metadata/source/fixture_inventory")
    extension = URIRef("https://external.example/sourceRank")
    document = Dataset().parse(path, format="trig")
    graph = document.graph(graph_iri)
    graph.add((subject, SKOS.prefLabel, Literal("Architecture", lang="en")))
    graph.add((subject, SKOS.altLabel, Literal("Architecture unit", lang="en")))
    graph.add((subject, DCTERMS.created, Literal("2020-01-02", datatype=XSD.date)))
    graph.add((subject, extension, Literal("3", datatype=XSD.integer)))
    metadata_before = set(document.graph(metadata_graph))
    path.write_text(document.serialize(format="trig"), encoding="utf-8")

    service = writer(proposal_repository)
    state = service.editable_resource(str(subject))
    service.save_individual(
        IndividualDraft(
            iri=state.iri,
            class_iri=state.class_iri,
            source_id=state.source_id,
            preferred_label_es=state.preferred_label_es,
            alternative_labels_es=state.alternative_labels_es,
            evidence="Inventario sintético controlado",
            author="Test Author",
            search=confirmed(service, "arquitectura fixture"),
            status="active",
            form_values=state.form_values,
        )
    )

    updated = Dataset().parse(path, format="trig")
    updated_graph = updated.graph(graph_iri)
    assert (subject, SKOS.prefLabel, Literal("Architecture", lang="en")) in updated_graph
    assert (subject, SKOS.altLabel, Literal("Architecture unit", lang="en")) in updated_graph
    assert (
        subject,
        DCTERMS.created,
        Literal("2020-01-02", datatype=XSD.date),
    ) in updated_graph
    assert (subject, extension, Literal("3", datatype=XSD.integer)) in updated_graph
    assert (subject, DCTERMS.modified, None) in updated_graph
    assert set(updated.graph(metadata_graph)) == metadata_before


def test_individual_dynamic_field_preserves_opaque_quads_and_shared_blank_node(
    proposal_repository: Path,
) -> None:
    predicate = add_plain_dynamic_shape(
        proposal_repository, OWL.NamedIndividual, "individual_opaque_note"
    )
    path = proposal_repository / "knowledge/data/sources/fixture_inventory.trig"
    subject = URIRef(f"{BASE}id/organization/unit/architecture")
    graph_iri = URIRef(f"{BASE}graph/source/fixture_inventory")
    metadata_graph_iri = URIRef(f"{BASE}graph/metadata/source/fixture_inventory")
    document = Dataset().parse(path, format="trig")
    source_graph = document.graph(graph_iri)
    technical = add_opaque_dynamic_values(source_graph, subject, predicate)
    source_graph.add(
        (subject, DCTERMS.source, Literal("Inventario sintético controlado", lang="es"))
    )
    source_graph.add((subject, DCTERMS.creator, Literal("Test Author")))
    source_graph.add((subject, URIRef(f"{BASE}ontology/core#status"), Literal("active")))
    source_graph.add((subject, DCTERMS.created, Literal("2020-01-02", datatype=XSD.date)))
    metadata_predicate = URIRef("https://external.example/crossGraphDetail")
    document.graph(metadata_graph_iri).add(
        (technical, metadata_predicate, Literal("shared blank node", lang="en"))
    )
    opaque_before = opaque_dynamic_subgraph(source_graph, subject, predicate)
    path.write_text(document.serialize(format="trig"), encoding="utf-8")

    expected = document
    expected_source = expected.graph(graph_iri)
    expected_source.remove((subject, predicate, Literal("editable note")))
    expected_source.add((subject, predicate, Literal("updated note")))
    expected_source.remove((subject, DCTERMS.modified, None))
    expected_source.add(
        (subject, DCTERMS.modified, Literal(date.today().isoformat(), datatype=XSD.date))
    )

    service = writer(proposal_repository)
    state = service.editable_resource(str(subject))
    assert dict(state.form_values)["note"] == ("editable note",)
    service.save_individual(
        IndividualDraft(
            iri=state.iri,
            class_iri=state.class_iri,
            source_id=state.source_id,
            preferred_label_es=state.preferred_label_es,
            alternative_labels_es=state.alternative_labels_es,
            evidence="Inventario sintético controlado",
            author="Test Author",
            search=confirmed(service, "architecture dynamic note"),
            status="active",
            form_values=(("note", ("updated note",)),),
        )
    )

    updated = Dataset().parse(path, format="trig")
    updated_source = updated.graph(graph_iri)
    assert isomorphic(
        opaque_before,
        opaque_dynamic_subgraph(updated_source, subject, predicate),
    )
    updated_technical = next(
        value for value in updated_source.objects(subject, predicate) if isinstance(value, BNode)
    )
    assert (
        updated_technical,
        metadata_predicate,
        Literal("shared blank node", lang="en"),
    ) in updated.graph(metadata_graph_iri)
    assert (subject, predicate, Literal("updated note")) in updated_source
    assert {graph.identifier for graph in updated.graphs()} >= {graph_iri, metadata_graph_iri}
    assert_dataset_semantics_equal(proposal_repository, expected, updated)


@pytest.mark.parametrize(
    ("kind", "iri", "module_id", "expected_type"),
    [
        (
            "node_shape",
            f"{BASE}shape/software/ReviewFixtureShape",
            "software",
            URIRef("http://www.w3.org/ns/shacl#NodeShape"),
        ),
        (
            "competency_question",
            f"{BASE}id/competency-question/review_fixture",
            "competency",
            URIRef(f"{BASE}ontology/competency#CompetencyQuestion"),
        ),
    ],
)
def test_structured_editable_types_are_written_without_generic_type_coercion(
    proposal_repository: Path,
    kind: str,
    iri: str,
    module_id: str,
    expected_type: URIRef,
) -> None:
    service = writer(proposal_repository)
    result = service.save_term(
        TermDraft(
            iri=iri,
            module_id=module_id,
            kind=kind,  # type: ignore[arg-type]
            preferred_label_es="Recurso estructurado de revisión",
            alternative_labels_es=("Alias estructurado",),
            definition_es="Fixture mínimo del subconjunto editable de P07.",
            evidence="Contrato SHACL de autoría",
            author="Test Author",
            search=confirmed(service, "recurso estructurado de revisión"),
            question_text_es="¿El fixture estructurado puede revisarse?"
            if kind == "competency_question"
            else None,
            acceptance_criterion_es="La pregunta conserva su criterio RDF."
            if kind == "competency_question"
            else None,
        )
    )
    graph = Graph().parse(proposal_repository / result.path, format="turtle")
    subject = URIRef(iri)
    assert (subject, RDF.type, expected_type) in graph
    assert (subject, RDF.type, OWL.Class) not in graph
    assert (subject, SKOS.altLabel, Literal("Alias estructurado", lang="es")) in graph
    state = service.editable_resource(iri)
    assert state.kind == kind
    assert state.alternative_labels_es == ("Alias estructurado",)


def test_ontology_round_trip_preserves_imports_and_unmodelled_module_metadata(
    proposal_repository: Path,
) -> None:
    service = writer(proposal_repository)
    iri = f"{BASE}ontology/software"
    state = service.editable_resource(iri)
    assert state.kind == "ontology"
    assert state.module_id == "software"

    service.save_term(
        TermDraft(
            iri=iri,
            module_id="software",
            kind="ontology",
            preferred_label_es=state.preferred_label_es,
            alternative_labels_es=("Módulo aplicativo",),
            definition_es=state.definition_es,
            evidence=state.evidence,
            author=state.author,
            search=confirmed(service, "módulo software"),
            status="active",
        )
    )
    graph = Graph().parse(proposal_repository / state.path, format="turtle")
    subject = URIRef(iri)
    assert (subject, RDF.type, OWL.Ontology) in graph
    assert len(tuple(graph.objects(subject, OWL.imports))) == 2
    assert (subject, DCTERMS.rightsHolder, None) in graph
    assert (subject, SKOS.altLabel, Literal("Módulo aplicativo", lang="es")) in graph
    assert service.editable_resource(iri).alternative_labels_es == ("Módulo aplicativo",)


def test_structured_noop_edit_preserves_multilingual_metadata_and_created_date(
    proposal_repository: Path,
) -> None:
    path = proposal_repository / "knowledge/ontology/software/module.ttl"
    subject = URIRef(f"{BASE}ontology/software")
    extension = URIRef("https://external.example/maturity")
    graph = Graph().parse(path, format="turtle")
    created = tuple(graph.objects(subject, DCTERMS.created))
    graph.add((subject, SKOS.prefLabel, Literal("Software fixture module", lang="en")))
    graph.add((subject, SKOS.altLabel, Literal("Application module", lang="en")))
    graph.add(
        (
            subject,
            SKOS.definition,
            Literal("A bounded module retained during structured editing.", lang="en"),
        )
    )
    graph.add((subject, extension, Literal("0.8", datatype=XSD.decimal)))
    path.write_text(graph.serialize(format="turtle"), encoding="utf-8")

    service = writer(proposal_repository)
    state = service.editable_resource(str(subject))
    service.save_term(
        TermDraft(
            iri=state.iri,
            module_id=state.module_id,
            kind="ontology",
            preferred_label_es=state.preferred_label_es,
            alternative_labels_es=state.alternative_labels_es,
            definition_es=state.definition_es,
            evidence=state.evidence,
            author=state.author,
            search=confirmed(service, "módulo software"),
            status="active",
            form_values=state.form_values,
        )
    )

    updated = Graph().parse(path, format="turtle")
    assert (subject, SKOS.prefLabel, Literal("Software fixture module", lang="en")) in updated
    assert (subject, SKOS.altLabel, Literal("Application module", lang="en")) in updated
    assert (
        subject,
        SKOS.definition,
        Literal("A bounded module retained during structured editing.", lang="en"),
    ) in updated
    assert tuple(updated.objects(subject, DCTERMS.created)) == created
    assert (subject, DCTERMS.modified, None) in updated
    assert (subject, extension, Literal("0.8", datatype=XSD.decimal)) in updated


def test_structured_dynamic_field_preserves_opaque_rdf_subgraph(
    proposal_repository: Path,
) -> None:
    predicate = add_plain_dynamic_shape(proposal_repository, OWL.Ontology, "ontology_opaque_note")
    path = proposal_repository / "knowledge/ontology/software/module.ttl"
    subject = URIRef(f"{BASE}ontology/software")
    graph = Graph().parse(path, format="turtle")
    add_opaque_dynamic_values(graph, subject, predicate)
    opaque_before = opaque_dynamic_subgraph(graph, subject, predicate)
    path.write_text(graph.serialize(format="turtle"), encoding="utf-8")

    expected = graph_dataset(graph, URIRef("urn:test:structured-document"))
    expected_graph = expected.graph(URIRef("urn:test:structured-document"))
    expected_graph.remove((subject, predicate, Literal("editable note")))
    expected_graph.add((subject, predicate, Literal("updated note")))
    expected_graph.remove((subject, DCTERMS.modified, None))
    expected_graph.add(
        (subject, DCTERMS.modified, Literal(date.today().isoformat(), datatype=XSD.date))
    )

    service = writer(proposal_repository)
    state = service.editable_resource(str(subject))
    assert dict(state.form_values)["note"] == ("editable note",)
    service.save_term(
        TermDraft(
            iri=state.iri,
            module_id=state.module_id,
            kind="ontology",
            preferred_label_es=state.preferred_label_es,
            alternative_labels_es=state.alternative_labels_es,
            definition_es=state.definition_es,
            evidence=state.evidence,
            author=state.author,
            search=confirmed(service, "software ontology dynamic note"),
            status="active",
            form_values=(("note", ("updated note",)),),
        )
    )

    updated = Graph().parse(path, format="turtle")
    assert isomorphic(opaque_before, opaque_dynamic_subgraph(updated, subject, predicate))
    assert (subject, predicate, Literal("updated note")) in updated
    assert_dataset_semantics_equal(
        proposal_repository,
        expected,
        graph_dataset(updated, URIRef("urn:test:structured-document")),
    )


def test_shacl_derived_field_is_required_validated_and_persisted(
    proposal_repository: Path,
) -> None:
    shape_path = proposal_repository / "knowledge/shapes/modules/risk_fixture.ttl"
    shape_path.write_text(
        """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://knowledge.example.com/ontology/software#> .
<https://knowledge.example.com/shape/software/RiskFixtureShape> a sh:NodeShape ;
  sh:targetClass owl:Class ;
  sh:property [
    sh:path ex:riskLevel ;
    sh:minCount 1 ;
    sh:maxCount 1 ;
    sh:in ( "low" "high" ) ;
    sh:name "Nivel de riesgo"@es
  ] ;
  sh:property [
    sh:path ex:reviewer ;
    sh:minCount 2 ;
    sh:maxCount 3 ;
    sh:name "Revisores"@es
  ] .
""",
        encoding="utf-8",
    )
    service = writer(proposal_repository)
    draft = TermDraft(
        iri=f"{BASE}ontology/software#RiskAwareCapability",
        module_id="software",
        kind="class",
        preferred_label_es="Capacidad con riesgo",
        definition_es="Fixture para el campo tipado derivado de SHACL.",
        evidence="Shape de riesgo de fixture",
        author="Test Author",
        search=confirmed(service, "capacidad con riesgo"),
    )
    with pytest.raises(AuthoringError) as missing:
        service.save_term(draft)
    assert missing.value.code == "authoring.required_form_field"
    with pytest.raises(AuthoringError) as invalid:
        service.save_term(
            replace(
                draft,
                form_values=(("riskLevel", ("critical",)), ("reviewer", ("Ada", "Grace"))),
            )
        )
    assert invalid.value.code == "authoring.form_field_value"
    with pytest.raises(AuthoringError) as too_few:
        service.save_term(
            replace(
                draft,
                form_values=(("riskLevel", ("high",)), ("reviewer", ("Ada",))),
            )
        )
    assert too_few.value.code == "authoring.required_form_field"
    with pytest.raises(AuthoringError) as too_many:
        service.save_term(
            replace(
                draft,
                form_values=(
                    ("riskLevel", ("high",)),
                    ("reviewer", ("Ada", "Grace", "Linus", "Margaret")),
                ),
            )
        )
    assert too_many.value.code == "authoring.form_field_cardinality"

    result = service.save_term(
        replace(
            draft,
            form_values=(
                ("riskLevel", ("high",)),
                ("reviewer", ("Ada", "Grace")),
            ),
        )
    )
    graph = Graph().parse(proposal_repository / result.path, format="turtle")
    assert (
        URIRef(draft.iri),
        URIRef(f"{BASE}ontology/software#riskLevel"),
        Literal("high"),
    ) in graph
    assert set(graph.objects(URIRef(draft.iri), URIRef(f"{BASE}ontology/software#reviewer"))) == {
        Literal("Ada"),
        Literal("Grace"),
    }
    assert dict(service.editable_resource(draft.iri).form_values)["reviewer"] == (
        "Ada",
        "Grace",
    )

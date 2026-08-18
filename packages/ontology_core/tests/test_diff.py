from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ontology_core import FilesystemRdfStore, OntologyQueryService
from ontology_core.authoring import SearchConfirmation, TermDraft, TermWriter
from ontology_core.diff import ProposalReviewService, SemanticDiffService
from ontology_core.workspace import GitWorkspaceService
from rdflib import BNode, Dataset, Literal, URIRef
from rdflib.namespace import RDF, SH

BASE = "https://knowledge.example.com/"
GRAPH = URIRef(f"{BASE}graph/test")


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def dataset(turtle: str) -> Dataset:
    result = Dataset()
    result.graph(GRAPH).parse(data=turtle, format="turtle")
    return result


def test_semantic_diff_ignores_turtle_order_and_blank_node_labels(
    tmp_path: Path,
) -> None:
    config = tmp_path / "namespace.yaml"
    config.write_text(
        "config_version: '1.0'\nnamespace:\n  base: https://knowledge.example.com/\n"
        "prefixes:\n  ex: ontology/example#\n",
        encoding="utf-8",
    )
    store_root = tmp_path / "knowledge"
    store_root.mkdir()
    prefixes = FilesystemRdfStore(store_root, config).prefixes
    left = dataset(
        """
        @prefix ex: <https://knowledge.example.com/ontology/example#> .
        ex:Thing ex:technical [ ex:value "one" ; ex:other "two" ] .
        """
    )
    reordered = dataset(
        """
        @prefix ex: <https://knowledge.example.com/ontology/example#> .
        ex:Thing ex:technical [ ex:other "two" ; ex:value "one" ] .
        """
    )
    service = SemanticDiffService(prefixes)
    empty = service.compare(left, reordered, base_ref="main", head_ref="proposal/test")
    assert empty.added_quads == ()
    assert empty.removed_quads == ()

    changed = dataset(
        """
        @prefix ex: <https://knowledge.example.com/ontology/example#> .
        @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
        ex:Thing ex:technical [ ex:other "two" ; ex:value "one" ] ;
            skos:prefLabel "Cosa"@es .
        """
    )
    report = service.compare(left, changed, base_ref="main", head_ref="proposal/test")
    assert len(report.added_quads) == 1
    assert report.added_quads[0].category == "label"
    assert report.modified_resources[0].value.endswith("#Thing")


def test_proposal_review_combines_diff_impact_evidence_and_validation(
    tmp_path: Path,
) -> None:
    source_root = Path(__file__).resolve().parents[3]
    root = tmp_path / "repository"
    root.mkdir()
    shutil.copytree(source_root / "knowledge", root / "knowledge")
    shutil.copytree(source_root / "config", root / "config")
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Test Author")
    git(root, "config", "user.email", "test@example.com")
    git(root, "add", "knowledge", "config")
    git(root, "commit", "-m", "chore: seed knowledge")
    git(root, "switch", "--create", "proposal/review")
    store = FilesystemRdfStore(root / "knowledge", root / "config/namespace.yaml")
    workspace = GitWorkspaceService(root, root / "knowledge")
    query = OntologyQueryService(store.load(), store.prefixes)
    TermWriter(store, workspace, query).save_term(
        TermDraft(
            iri=f"{BASE}ontology/software#Application",
            module_id="software",
            kind="class",
            preferred_label_es="Aplicación revisada",
            definition_es="Sistema de software identificable sujeto a revisión semántica.",
            evidence="Decisión registrada en el catálogo de aplicaciones",
            author="Test Author",
            search=SearchConfirmation(
                "aplicación",
                True,
                query.search_page("aplicación").search_id,
            ),
        )
    )
    review = ProposalReviewService(store, workspace).review()
    assert review.diff.base == "main"
    assert review.diff.head == "proposal/review"
    assert any(change.resource.value.endswith("#Application") for change in review.diff.changes)
    assert any(quad.object.value.startswith("Decisión registrada") for quad in review.evidence)
    assert f"{BASE}ontology/software#Application" in review.impact
    assert review.validation.conforms is True
    assert review.ready_to_commit is True


def test_proposal_review_treats_valid_pre_rdf_git_base_as_initial_import(
    tmp_path: Path,
) -> None:
    source_root = Path(__file__).resolve().parents[3]
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Test Author")
    git(root, "config", "user.email", "test@example.com")
    (root / "README.md").write_text("initial repository\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "chore: initial repository")
    git(root, "switch", "--create", "proposal/initial-rdf")
    shutil.copytree(source_root / "knowledge", root / "knowledge")
    shutil.copytree(source_root / "config", root / "config")

    store = FilesystemRdfStore(root / "knowledge", root / "config/namespace.yaml")
    workspace = GitWorkspaceService(root, root / "knowledge")
    review = ProposalReviewService(store, workspace).review(base_ref="main")

    assert review.diff.base == "main"
    assert len(review.diff.added_quads) == len(store.load())
    assert review.diff.removed_quads == ()
    assert review.validation.conforms is True
    assert review.ready_to_commit is True


def test_proposal_review_does_not_hide_an_unknown_git_base(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[3]
    root = tmp_path / "repository"
    root.mkdir()
    shutil.copytree(source_root / "knowledge", root / "knowledge")
    shutil.copytree(source_root / "config", root / "config")
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Test Author")
    git(root, "config", "user.email", "test@example.com")
    git(root, "add", "knowledge", "config")
    git(root, "commit", "-m", "chore: seed knowledge")
    git(root, "switch", "--create", "proposal/missing-base")

    store = FilesystemRdfStore(root / "knowledge", root / "config/namespace.yaml")
    workspace = GitWorkspaceService(root, root / "knowledge")
    try:
        ProposalReviewService(store, workspace).review(base_ref="does-not-exist")
    except Exception as error:  # noqa: BLE001 - assert public error contract
        assert getattr(error, "code", None) == "git.base_unavailable"
    else:  # pragma: no cover - explicit failure is clearer than pytest.raises typing here
        raise AssertionError("an unknown Git base must not become an empty initial import")


def test_semantic_diff_groups_hierarchy_domain_range_and_deprecation(tmp_path: Path) -> None:
    config = tmp_path / "namespace.yaml"
    config.write_text(
        "config_version: '1.0'\nnamespace:\n  base: https://knowledge.example.com/\n"
        "prefixes:\n  ex: ontology/example#\n",
        encoding="utf-8",
    )
    root = tmp_path / "knowledge"
    root.mkdir()
    prefixes = FilesystemRdfStore(root, config).prefixes
    base = dataset(
        """
        @prefix ex: <https://knowledge.example.com/ontology/example#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        ex:Child a owl:Class . ex:relation a owl:ObjectProperty .
        """
    )
    head = dataset(
        """
        @prefix ex: <https://knowledge.example.com/ontology/example#> .
        @prefix eow: <https://knowledge.example.com/ontology/core#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:Child a owl:Class ; rdfs:subClassOf ex:Parent ; eow:status "deprecated" .
        ex:relation a owl:ObjectProperty ; rdfs:domain ex:Child ; rdfs:range ex:Parent .
        """
    )
    report = SemanticDiffService(prefixes).compare(
        base, head, base_ref="main", head_ref="proposal/categories"
    )
    by_resource = {change.resource.value: change.categories for change in report.changes}
    assert by_resource[f"{BASE}ontology/example#Child"] == ("hierarchy", "status")
    assert by_resource[f"{BASE}ontology/example#relation"] == ("domain_range",)
    assert [item.value for item in report.deprecated_resources] == [f"{BASE}ontology/example#Child"]


def test_blank_node_shape_change_is_grouped_under_its_named_shape(tmp_path: Path) -> None:
    config = tmp_path / "namespace.yaml"
    config.write_text(
        "config_version: '1.0'\nnamespace:\n  base: https://knowledge.example.com/\n"
        "prefixes:\n  ex: ontology/example#\n",
        encoding="utf-8",
    )
    root = tmp_path / "knowledge"
    root.mkdir()
    prefixes = FilesystemRdfStore(root, config).prefixes
    shape = URIRef(f"{BASE}shape/ExampleShape")
    path = URIRef(f"{BASE}ontology/example#value")

    def shape_dataset(min_count: int) -> Dataset:
        result = Dataset()
        property_shape = BNode()
        graph = result.graph(GRAPH)
        graph.add((shape, RDF.type, SH.NodeShape))
        graph.add((shape, SH.property, property_shape))
        graph.add((property_shape, SH.path, path))
        graph.add((property_shape, SH.minCount, Literal(min_count)))
        return result

    report = SemanticDiffService(prefixes).compare(
        shape_dataset(1),
        shape_dataset(2),
        base_ref="main",
        head_ref="proposal/shape",
    )

    assert len(report.added_quads) == len(report.removed_quads) == 1
    assert [change.resource.value for change in report.changes] == [str(shape)]
    assert len(report.changes[0].added) == len(report.changes[0].removed) == 1
    assert str(shape) in {value.value for value in report.modified_resources}


def test_dataset_canonicalization_preserves_bnodes_shared_across_named_graphs(
    tmp_path: Path,
) -> None:
    config = tmp_path / "namespace.yaml"
    config.write_text(
        "config_version: '1.0'\nnamespace:\n  base: https://knowledge.example.com/\n"
        "prefixes:\n  ex: ontology/example#\n",
        encoding="utf-8",
    )
    root = tmp_path / "knowledge"
    root.mkdir()
    prefixes = FilesystemRdfStore(root, config).prefixes
    predicate = URIRef(f"{BASE}ontology/example#technical")
    first = URIRef(f"{BASE}ontology/example#First")
    second = URIRef(f"{BASE}ontology/example#Second")
    graph_one = URIRef(f"{BASE}graph/one")
    graph_two = URIRef(f"{BASE}graph/two")
    shared = Dataset()
    shared_node = BNode()
    shared.graph(graph_one).add((first, predicate, shared_node))
    shared.graph(graph_two).add((second, predicate, shared_node))
    split = Dataset()
    split.graph(graph_one).add((first, predicate, BNode()))
    split.graph(graph_two).add((second, predicate, BNode()))

    report = SemanticDiffService(prefixes).compare(
        shared, split, base_ref="main", head_ref="proposal/split"
    )

    assert report.added_quads
    assert report.removed_quads
    assert report.changes


def test_orphan_blank_node_changes_remain_visible_in_a_deterministic_technical_group(
    tmp_path: Path,
) -> None:
    config = tmp_path / "namespace.yaml"
    config.write_text(
        "config_version: '1.0'\nnamespace:\n  base: https://knowledge.example.com/\n"
        "prefixes:\n  ex: ontology/example#\n",
        encoding="utf-8",
    )
    root = tmp_path / "knowledge"
    root.mkdir()
    prefixes = FilesystemRdfStore(root, config).prefixes
    predicate = URIRef(f"{BASE}ontology/example#technicalValue")
    before = Dataset()
    before.graph(GRAPH).add((BNode(), predicate, Literal("one")))
    after = Dataset()
    after.graph(GRAPH).add((BNode(), predicate, Literal("two")))

    report = SemanticDiffService(prefixes).compare(
        before, after, base_ref="main", head_ref="proposal/technical"
    )

    assert len(report.added_quads) == len(report.removed_quads) == 1
    assert len(report.changes) == 1
    assert report.changes[0].resource.value.startswith("urn:eow:technical-change:")
    assert report.changes[0].added == report.added_quads
    assert report.changes[0].removed == report.removed_quads

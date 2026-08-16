"""Filesystem-backed RDF Dataset loading with explicit graph boundaries."""

from __future__ import annotations

import multiprocessing
from abc import ABC, abstractmethod
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Literal as TypingLiteral

from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF
from rdflib.term import IdentifiedNode, Node

from ontology_core.prefixes import NamespaceConfiguration, PrefixResolver


class RdfLoadError(RuntimeError):
    """An RDF source could not be loaded without changing its graph semantics."""

    def __init__(self, path: Path, detail: str, *, rule_id: str = "parser.syntax") -> None:
        super().__init__(f"could not load RDF from {path}: {detail}")
        self.path = path
        self.detail = detail
        self.rule_id = rule_id


class ManifestError(RdfLoadError):
    """The repository manifest does not satisfy the loader contract."""


class KnowledgeStore(ABC):
    """Storage boundary consumed by future API, CLI and MCP adapters."""

    @abstractmethod
    def load(self) -> Dataset:
        """Load and return the canonical RDF dataset."""

    @abstractmethod
    def serialize(self) -> str:
        """Serialize the loaded dataset as TriG without collapsing named graphs."""

    @abstractmethod
    def export(self, destination: Path) -> None:
        """Write a round-trippable TriG representation to ``destination``."""


@dataclass(frozen=True)
class ModuleDefinition:
    """A module declared by the RDF manifest."""

    identifier: str
    source_path: Path
    graph_iri: URIRef


@dataclass(frozen=True)
class LocalShapeCatalog:
    """Complete set of local SHACL sources loaded from ``knowledge/shapes``."""

    graph: Graph
    source_paths: tuple[Path, ...]


@dataclass(frozen=True)
class RdfLoadLimits:
    """Configurable resource limits applied to every repository RDF source."""

    max_file_bytes: int = 8 * 1024 * 1024
    parse_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        if self.parse_timeout_seconds <= 0:
            raise ValueError("parse_timeout_seconds must be positive")


ParsedTriple = tuple[Node, Node, Node]
ParsedQuad = tuple[Node, Node, Node, IdentifiedNode | None]


def _parse_rdf_worker(
    connection: Connection,
    path: str,
    rdf_format: TypingLiteral["turtle", "trig"],
) -> None:
    """Parse in a disposable process so a deadline can be enforced reliably."""

    try:
        if rdf_format == "trig":
            dataset = Dataset()
            dataset.parse(path, format="trig")
            payload: tuple[ParsedQuad, ...] | tuple[ParsedTriple, ...] = tuple(
                dataset.quads((None, None, None, None))
            )
        else:
            graph = Graph()
            graph.parse(path, format="turtle")
            payload = tuple(graph)
        connection.send(("ok", payload))
    except Exception as error:  # noqa: BLE001 - the parent converts worker failures to RdfLoadError
        connection.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


class FilesystemRdfStore(KnowledgeStore):
    """Load repository RDF sources into an in-memory RDFLib Dataset."""

    def __init__(
        self,
        knowledge_root: Path,
        namespace_config_path: Path,
        *,
        limits: RdfLoadLimits | None = None,
    ) -> None:
        self.knowledge_root = knowledge_root.resolve()
        self.namespace_config_path = namespace_config_path.resolve()
        self.limits = limits or RdfLoadLimits()
        self.namespace_configuration = NamespaceConfiguration.from_file(self.namespace_config_path)
        self.prefixes = PrefixResolver(self.namespace_configuration)
        self.dataset = Dataset()
        self._subject_source_paths: dict[URIRef, set[Path]] = {}

    @property
    def manifest_path(self) -> Path:
        return self.knowledge_root / "manifest.ttl"

    def discover_module_files(self, module: ModuleDefinition) -> tuple[Path, ...]:
        module_root = (self.knowledge_root / module.source_path).resolve()
        self._require_within_root(module_root)
        files = [module_root / "module.ttl"]
        terms_root = module_root / "terms"
        if terms_root.exists():
            files.extend(sorted(path for path in terms_root.rglob("*.ttl") if path.is_file()))
        missing = [path for path in files if not path.is_file()]
        if missing:
            raise ManifestError(self.manifest_path, f"module source is missing: {missing[0]}")
        return tuple(files)

    def discover_modules(self) -> tuple[ModuleDefinition, ...]:
        """Return manifest modules without encoding their names in Python."""

        return self._read_modules(self._parse_turtle(self.manifest_path))

    def discover_source_files(self) -> tuple[Path, ...]:
        source_root = self.knowledge_root / "data" / "sources"
        if not source_root.exists():
            return ()
        return tuple(
            sorted(
                path
                for path in source_root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".ttl", ".trig"}
            )
        )

    def discover_competency_question_files(self) -> tuple[Path, ...]:
        """Discover RDF question definitions without treating `.rq` files as RDF."""

        question_root = self.knowledge_root / "competency_questions"
        if not question_root.exists():
            return ()
        return tuple(sorted(path for path in question_root.glob("*.ttl") if path.is_file()))

    def discover_shape_files(self) -> tuple[Path, ...]:
        """Discover every local Turtle shape under the confined shapes root."""

        shape_root = self.knowledge_root / "shapes"
        try:
            resolved_root = shape_root.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise RdfLoadError(shape_root, str(error)) from error
        self._require_within_root(resolved_root)
        if not resolved_root.is_dir():
            raise RdfLoadError(shape_root, "shapes path must be a directory")
        return tuple(sorted(path for path in resolved_root.rglob("*.ttl") if path.is_file()))

    def load_shape_catalog(self) -> LocalShapeCatalog:
        """Load the complete deterministic local SHACL catalog with parser limits."""

        source_paths = self.discover_shape_files()
        graph = Graph()
        for path in source_paths:
            for triple in self._parse_turtle(path):
                graph.add(triple)
        return LocalShapeCatalog(graph=graph, source_paths=source_paths)

    def load(self) -> Dataset:
        dataset = Dataset()
        self._subject_source_paths = {}
        manifest_graph_iri = URIRef(f"{self.namespace_configuration.base}graph/manifest")
        manifest = self._parse_turtle(self.manifest_path)
        self._record_subject_sources(self.manifest_path, manifest)
        for triple in manifest:
            dataset.graph(manifest_graph_iri).add(triple)

        modules = self._read_modules(manifest)
        for module in modules:
            graph = dataset.graph(module.graph_iri)
            for path in self.discover_module_files(module):
                parsed = self._parse_turtle(path)
                self._record_subject_sources(path, parsed)
                for triple in parsed:
                    graph.add(triple)

        for path in self.discover_source_files():
            if path.suffix.lower() == ".trig":
                self._parse_trig_into(dataset, path)
            else:
                graph_iri = URIRef(f"{self.namespace_configuration.base}graph/source/{path.stem}")
                parsed = self._parse_turtle(path)
                self._record_subject_sources(path, parsed)
                for triple in parsed:
                    dataset.graph(graph_iri).add(triple)

        for path in self.discover_competency_question_files():
            graph_iri = URIRef(
                f"{self.namespace_configuration.base}graph/competency-questions/{path.stem}"
            )
            parsed = self._parse_turtle(path)
            self._record_subject_sources(path, parsed)
            for triple in parsed:
                dataset.graph(graph_iri).add(triple)

        for prefix, namespace in sorted(self.namespace_configuration.prefixes.items()):
            dataset.bind(prefix, Namespace(namespace), replace=True)
        self.dataset = dataset
        return dataset

    def source_paths_for(self, resource: str | URIRef) -> tuple[Path, ...]:
        """Return canonical local files where an IRI is defined as a subject."""

        node = URIRef(resource) if isinstance(resource, str) else resource
        return tuple(sorted(self._subject_source_paths.get(node, ())))

    def _record_subject_sources(
        self,
        path: Path,
        statements: Graph | tuple[ParsedTriple, ...] | tuple[ParsedQuad, ...],
    ) -> None:
        resolved = path.resolve()
        for statement in statements:
            subject = statement[0]
            if isinstance(subject, URIRef):
                self._subject_source_paths.setdefault(subject, set()).add(resolved)

    def serialize(self) -> str:
        return self.dataset.serialize(format="trig")

    def serialize_graph(self, graph_iri: str | URIRef) -> str:
        """Serialize one named graph as Turtle without mutating the dataset."""

        graph = self.dataset.graph(URIRef(graph_iri))
        isolated = Graph()
        for prefix, namespace in sorted(self.namespace_configuration.prefixes.items()):
            isolated.bind(prefix, Namespace(namespace), replace=True)
        for triple in graph:
            isolated.add(triple)
        return isolated.serialize(format="turtle")

    def export(self, destination: Path) -> None:
        destination.write_text(self.serialize(), encoding="utf-8")

    def _read_modules(self, manifest: Graph) -> tuple[ModuleDefinition, ...]:
        vocabulary = Namespace(f"{self.namespace_configuration.base}ontology/core#")
        manifests = tuple(manifest.subjects(RDF.type, vocabulary.KnowledgeManifest))
        if len(manifests) != 1:
            raise ManifestError(self.manifest_path, "expected exactly one KnowledgeManifest")
        manifest_subject = manifests[0]

        manifest_version = manifest.value(manifest_subject, vocabulary.manifestVersion)
        if not isinstance(manifest_version, Literal) or not str(manifest_version):
            raise ManifestError(self.manifest_path, "manifestVersion must be a non-empty literal")

        declared_base = manifest.value(manifest_subject, vocabulary.namespaceBase)
        base_matches = (
            isinstance(declared_base, Literal)
            and str(declared_base) == self.namespace_configuration.base
        )
        if not base_matches:
            raise ManifestError(
                self.manifest_path,
                "manifest namespaceBase must match config/namespace.yaml",
            )

        definitions: list[ModuleDefinition] = []
        for module_subject in manifest.objects(manifest_subject, vocabulary.module):
            identifier = manifest.value(module_subject, vocabulary.moduleId)
            source_path = manifest.value(module_subject, vocabulary.sourcePath)
            graph_iri = manifest.value(module_subject, vocabulary.graph)
            if not isinstance(identifier, Literal) or not isinstance(source_path, Literal):
                raise ManifestError(self.manifest_path, "moduleId and sourcePath must be literals")
            if not isinstance(graph_iri, URIRef):
                raise ManifestError(self.manifest_path, "module graph must be an IRI")
            definitions.append(
                ModuleDefinition(
                    identifier=str(identifier),
                    source_path=Path(str(source_path)),
                    graph_iri=graph_iri,
                )
            )
        if not definitions:
            raise ManifestError(self.manifest_path, "manifest must declare at least one module")
        return tuple(sorted(definitions, key=lambda module: module.identifier))

    def _parse_turtle(self, path: Path) -> Graph:
        triples = self._parse_with_limits(path, "turtle")
        graph = Graph()
        for triple in triples:
            if len(triple) != 3:
                raise RdfLoadError(path, "Turtle parser returned a non-triple result")
            graph.add(triple)
        return graph

    def _parse_trig_into(self, dataset: Dataset, path: Path) -> None:
        quads = self._parse_with_limits(path, "trig")
        self._record_subject_sources(path, quads)
        for quad in quads:
            if len(quad) != 4:
                raise RdfLoadError(path, "TriG parser returned a non-quad result")
            subject, predicate, obj, graph_name = quad
            dataset.graph(graph_name).add((subject, predicate, obj))

    def _parse_with_limits(
        self,
        path: Path,
        rdf_format: TypingLiteral["turtle", "trig"],
    ) -> tuple[ParsedTriple, ...] | tuple[ParsedQuad, ...]:
        resolved = self._validated_source_path(path)
        start_method = "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
        process_context = multiprocessing.get_context(start_method)
        parent, child = process_context.Pipe(duplex=False)
        process = process_context.Process(  # type: ignore[attr-defined]
            target=_parse_rdf_worker,
            args=(child, str(resolved), rdf_format),
            daemon=True,
        )
        process.start()
        child.close()
        try:
            if not parent.poll(self.limits.parse_timeout_seconds):
                process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join()
                raise RdfLoadError(
                    path,
                    f"parse timeout exceeded ({self.limits.parse_timeout_seconds:g}s)",
                    rule_id="parser.timeout",
                )
            try:
                status, payload = parent.recv()
            except EOFError as error:
                raise RdfLoadError(path, "RDF parser process exited without a result") from error
        finally:
            parent.close()
            process.join(timeout=0.05)
            if process.is_alive():
                process.terminate()
                process.join()
        if status == "error":
            raise RdfLoadError(path, str(payload))
        if not isinstance(payload, tuple):
            raise RdfLoadError(path, "RDF parser returned an invalid result")
        return payload

    def _validated_source_path(self, path: Path) -> Path:
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise RdfLoadError(path, str(error)) from error
        if not resolved.is_relative_to(self.knowledge_root):
            raise RdfLoadError(
                path,
                f"source escapes knowledge root: {resolved}",
                rule_id="parser.path_escape",
            )
        size = resolved.stat().st_size
        if size > self.limits.max_file_bytes:
            raise RdfLoadError(
                path,
                f"file size {size} exceeds limit {self.limits.max_file_bytes}",
                rule_id="parser.size_limit",
            )
        return resolved

    def _require_within_root(self, path: Path) -> None:
        if not path.is_relative_to(self.knowledge_root):
            raise RdfLoadError(
                path,
                f"source escapes knowledge root: {path}",
                rule_id="parser.path_escape",
            )

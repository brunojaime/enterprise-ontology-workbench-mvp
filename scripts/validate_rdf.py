"""Run the repository RDF validation pipeline without introducing the Plan 08 CLI."""

from __future__ import annotations

from pathlib import Path

from ontology_core import FilesystemRdfStore, ValidationService


def main() -> int:
    repository_root = Path(__file__).parents[1]
    store = FilesystemRdfStore(
        repository_root / "knowledge",
        repository_root / "config" / "namespace.yaml",
    )
    report = ValidationService(store).validate_repository()
    print(report.to_json())
    return 0 if report.conforms else 1


if __name__ == "__main__":
    raise SystemExit(main())

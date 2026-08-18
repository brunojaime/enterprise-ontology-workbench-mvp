from pathlib import Path

import pytest
from ontology_core.prefixes import (
    NamespaceConfiguration,
    NamespaceConfigurationError,
    PrefixResolver,
)
from rdflib import URIRef

REPOSITORY_ROOT = Path(__file__).parents[3]
NAMESPACE_CONFIG = REPOSITORY_ROOT / "config" / "namespace.yaml"


def test_namespace_configuration_resolves_relative_prefixes() -> None:
    configuration = NamespaceConfiguration.from_file(NAMESPACE_CONFIG)

    assert configuration.version == "1.0"
    assert configuration.base == "https://knowledge.example.com/"
    assert configuration.prefixes["software"] == (
        "https://knowledge.example.com/ontology/software#"
    )
    assert configuration.prefixes["rdf"] == ("http://www.w3.org/1999/02/22-rdf-syntax-ns#")


def test_prefix_expansion_and_compaction_are_deterministic() -> None:
    resolver = PrefixResolver(NamespaceConfiguration.from_file(NAMESPACE_CONFIG))

    expanded = resolver.expand("software:Application")

    assert expanded == URIRef("https://knowledge.example.com/ontology/software#Application")
    assert resolver.compact(expanded) == "software:Application"
    assert resolver.compact("https://external.example/Thing") == ("https://external.example/Thing")


def test_absolute_iri_expansion_does_not_dereference_remote_resources() -> None:
    resolver = PrefixResolver(NamespaceConfiguration.from_file(NAMESPACE_CONFIG))

    assert resolver.expand("https://remote.invalid/not-fetched") == URIRef(
        "https://remote.invalid/not-fetched"
    )


def test_unknown_or_incomplete_curies_are_rejected() -> None:
    resolver = PrefixResolver(NamespaceConfiguration.from_file(NAMESPACE_CONFIG))

    with pytest.raises(KeyError, match="unknown prefix"):
        resolver.expand("unknown:Thing")
    with pytest.raises(ValueError, match="local name"):
        resolver.expand("software:")
    with pytest.raises(ValueError, match="CURIE"):
        resolver.expand("Application")


@pytest.mark.parametrize(
    ("base", "message"),
    [
        ("relative/path", "absolute HTTPS"),
        ("http://knowledge.example.test/", "absolute HTTPS"),
        ("https://knowledge.example.test", "end with"),
        ("https://knowledge.example.test/#base", "query or fragment"),
        ("https://knowledge.example.test/?version=1", "query or fragment"),
    ],
)
def test_invalid_namespace_configuration_is_rejected(
    tmp_path: Path, base: str, message: str
) -> None:
    config = tmp_path / "namespace.yaml"
    config.write_text(
        f"config_version: '1.0'\nnamespace:\n  base: {base}\nprefixes:\n  ex: terms#\n",
        encoding="utf-8",
    )

    with pytest.raises(NamespaceConfigurationError, match=message):
        NamespaceConfiguration.from_file(config)

"""Versioned namespace configuration and deterministic IRI resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from rdflib import URIRef


class NamespaceConfigurationError(ValueError):
    """Raised when the namespace configuration is incomplete or ambiguous."""


@dataclass(frozen=True)
class NamespaceConfiguration:
    """Namespace settings shared by semantic adapters such as API and CLI."""

    version: str
    base: str
    prefixes: dict[str, str]

    @classmethod
    def from_file(cls, path: Path) -> NamespaceConfiguration:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise NamespaceConfigurationError("namespace configuration must be a mapping")

        version = raw.get("config_version")
        namespace = raw.get("namespace")
        raw_prefixes = raw.get("prefixes")
        if not isinstance(version, str) or not version:
            raise NamespaceConfigurationError("config_version must be a non-empty string")
        if not isinstance(namespace, dict) or not isinstance(namespace.get("base"), str):
            raise NamespaceConfigurationError("namespace.base must be a string")
        if not isinstance(raw_prefixes, dict) or not raw_prefixes:
            raise NamespaceConfigurationError("prefixes must be a non-empty mapping")

        base = namespace["base"]
        parsed_base = urlparse(base)
        if parsed_base.scheme != "https" or not parsed_base.netloc:
            raise NamespaceConfigurationError("namespace.base must be an absolute HTTPS IRI")
        if parsed_base.query or parsed_base.fragment:
            raise NamespaceConfigurationError("namespace.base must not contain query or fragment")
        if not base.endswith("/"):
            raise NamespaceConfigurationError("namespace.base must end with '/'")

        prefixes: dict[str, str] = {}
        for prefix, value in raw_prefixes.items():
            if not isinstance(prefix, str) or not prefix or ":" in prefix:
                raise NamespaceConfigurationError(f"invalid prefix name: {prefix!r}")
            if not isinstance(value, str) or not value:
                raise NamespaceConfigurationError(f"prefix {prefix!r} must map to a string")
            parsed_value = urlparse(value)
            prefixes[prefix] = value if parsed_value.scheme else f"{base}{value}"

        duplicate_iris = {
            iri for iri in prefixes.values() if list(prefixes.values()).count(iri) > 1
        }
        if duplicate_iris:
            joined = ", ".join(sorted(duplicate_iris))
            raise NamespaceConfigurationError(f"prefix IRIs must be unique: {joined}")
        return cls(version=version, base=base, prefixes=prefixes)


class PrefixResolver:
    """Expand CURIEs and compact IRIs using a deterministic prefix map."""

    def __init__(self, configuration: NamespaceConfiguration) -> None:
        self.configuration = configuration

    def expand(self, value: str) -> URIRef:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return URIRef(value)
        if ":" not in value:
            raise ValueError(f"expected a CURIE or absolute HTTP(S) IRI: {value!r}")

        prefix, local_name = value.split(":", maxsplit=1)
        namespace = self.configuration.prefixes.get(prefix)
        if namespace is None:
            raise KeyError(f"unknown prefix: {prefix}")
        if not local_name:
            raise ValueError(f"CURIE local name must not be empty: {value!r}")
        return URIRef(f"{namespace}{local_name}")

    def compact(self, value: str | URIRef) -> str:
        iri = str(value)
        candidates = [
            (namespace, prefix)
            for prefix, namespace in self.configuration.prefixes.items()
            if iri.startswith(namespace) and iri != namespace
        ]
        if not candidates:
            return iri
        namespace, prefix = sorted(candidates, key=lambda item: (-len(item[0]), item[1]))[0]
        return f"{prefix}:{iri.removeprefix(namespace)}"

"""Opaque, auditable receipts issued only by an executed ontology search."""

from __future__ import annotations

import base64
import hmac
import json
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, TypeGuard

SEARCH_RECEIPT_PATTERN = r"^eow-search-v2:[A-Za-z0-9_-]+\.[0-9a-f]{64}$"
_TOKEN = re.compile(SEARCH_RECEIPT_PATTERN)


def normalize_search_query(value: str) -> str:
    """Normalize a query exactly as the search index does."""

    import unicodedata

    decomposed = unicodedata.normalize("NFKD", value.casefold())
    unaccented = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", unaccented))


@dataclass(frozen=True)
class SearchReceipt:
    """Verified audit data embedded in a signed receipt."""

    query: str
    snapshot: str
    results_digest: str
    total: int
    offset: int
    limit: int
    result_count: int
    rdf_types: tuple[str, ...]
    modules: tuple[str, ...]

    def to_dict(self) -> dict[str, str | int | list[str]]:
        return {
            "query": self.query,
            "snapshot": self.snapshot,
            "results_digest": self.results_digest,
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
            "result_count": self.result_count,
            "rdf_types": list(self.rdf_types),
            "modules": list(self.modules),
        }

    @property
    def authoring_eligible(self) -> bool:
        """Whether this receipt proves a global first-page duplicate search."""

        return (
            self.offset == 0
            and not self.rdf_types
            and not self.modules
            and self.result_count == min(self.total, self.limit)
        )


class SearchReceiptAuthority:
    """Issue and verify receipts with a process-private capability key."""

    def __init__(self, secret: bytes | None = None) -> None:
        key = secret if secret is not None else secrets.token_bytes(32)
        if len(key) < 32:
            raise ValueError("search receipt secret must contain at least 32 bytes")
        self._secret = bytes(key)

    def issue(
        self,
        query: str,
        *,
        snapshot: str,
        results: list[dict[str, object]],
        total: int,
        offset: int,
        limit: int,
        rdf_types: Iterable[str] = (),
        modules: Iterable[str] = (),
    ) -> str:
        """Sign the exact bounded result page produced by a real search."""

        normalized = normalize_search_query(query)
        if not normalized:
            raise ValueError("search query must be non-empty")
        if not snapshot:
            raise ValueError("search snapshot must be non-empty")
        result_json = json.dumps(
            results,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        normalized_types = tuple(sorted(set(rdf_types)))
        normalized_modules = tuple(sorted(set(modules)))
        if total < 0 or offset < 0 or limit <= 0 or len(results) > limit:
            raise ValueError("invalid search result page bounds")
        if any(not value for value in (*normalized_types, *normalized_modules)):
            raise ValueError("search filters must be non-empty strings")
        if len(results) != min(max(total - offset, 0), limit):
            raise ValueError("search result page is inconsistent with its bounds")
        payload: dict[str, str | int | tuple[str, ...]] = {
            "q": normalized,
            "s": snapshot,
            "r": sha256(result_json).hexdigest(),
            "t": total,
            "o": offset,
            "l": limit,
            "n": len(results),
            "y": normalized_types,
            "m": normalized_modules,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=")
        signature = hmac.new(self._secret, encoded, sha256).hexdigest()
        return f"eow-search-v2:{encoded.decode('ascii')}.{signature}"

    def inspect(self, token: str) -> SearchReceipt | None:
        """Return verified audit data, or ``None`` for malformed/forged input."""

        if len(token) > 4096 or _TOKEN.fullmatch(token) is None:
            return None
        encoded_text, signature = token.removeprefix("eow-search-v2:").rsplit(".", 1)
        encoded = encoded_text.encode("ascii")
        expected = hmac.new(self._secret, encoded, sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            padding = b"=" * (-len(encoded) % 4)
            raw: Any = json.loads(base64.urlsafe_b64decode(encoded + padding))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict) or set(raw) != {
            "q",
            "s",
            "r",
            "t",
            "o",
            "l",
            "n",
            "y",
            "m",
        }:
            return None
        query = raw.get("q")
        snapshot = raw.get("s")
        results_digest = raw.get("r")
        total = raw.get("t")
        offset = raw.get("o")
        limit = raw.get("l")
        result_count = raw.get("n")
        rdf_types = raw.get("y")
        modules = raw.get("m")
        if (
            not isinstance(query, str)
            or not query
            or not isinstance(snapshot, str)
            or not snapshot
            or not isinstance(results_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", results_digest) is None
            or not isinstance(total, int)
            or isinstance(total, bool)
            or total < 0
            or not isinstance(offset, int)
            or isinstance(offset, bool)
            or offset < 0
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit <= 0
            or not isinstance(result_count, int)
            or isinstance(result_count, bool)
            or result_count < 0
            or result_count > limit
            or result_count != min(max(total - offset, 0), limit)
            or not self._valid_filter_list(rdf_types)
            or not self._valid_filter_list(modules)
        ):
            return None
        return SearchReceipt(
            query,
            snapshot,
            results_digest,
            total,
            offset,
            limit,
            result_count,
            tuple(rdf_types),
            tuple(modules),
        )

    @staticmethod
    def _valid_filter_list(value: object) -> TypeGuard[list[str]]:
        return (
            isinstance(value, list)
            and all(isinstance(item, str) and item for item in value)
            and value == sorted(set(value))
        )

    def validate(
        self,
        query: str,
        token: str,
        *,
        snapshot: str,
        rdf_types: Iterable[str] = (),
        modules: Iterable[str] = (),
        offset: int = 0,
        limit: int | None = None,
        for_authoring: bool = False,
    ) -> bool:
        receipt = self.inspect(token)
        return (
            receipt is not None
            and receipt.query == normalize_search_query(query)
            and receipt.snapshot == snapshot
            and receipt.rdf_types == tuple(sorted(set(rdf_types)))
            and receipt.modules == tuple(sorted(set(modules)))
            and receipt.offset == offset
            and (limit is None or receipt.limit == limit)
            and (not for_authoring or receipt.authoring_eligible)
        )

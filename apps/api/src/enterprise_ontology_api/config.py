"""Runtime paths for the HTTP adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApiSettings:
    repository_root: Path
    knowledge_root: Path
    namespace_config: Path
    write_enabled: bool = False

    @classmethod
    def from_environment(cls) -> ApiSettings:
        default_root = Path(__file__).resolve().parents[4]
        repository_root = Path(os.getenv("EOW_REPOSITORY_ROOT", default_root)).resolve()
        knowledge_root = Path(
            os.getenv("EOW_KNOWLEDGE_ROOT", repository_root / "knowledge")
        ).resolve()
        namespace_config = Path(
            os.getenv("EOW_NAMESPACE_CONFIG", repository_root / "config" / "namespace.yaml")
        ).resolve()
        write_enabled = os.getenv("EOW_WRITE_ENABLED", "false").casefold() in {
            "1",
            "true",
            "yes",
        }
        return cls(repository_root, knowledge_root, namespace_config, write_enabled)

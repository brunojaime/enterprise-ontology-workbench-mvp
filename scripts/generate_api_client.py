"""Generate and verify the frontend OpenAPI schema and TypeScript declarations."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from enterprise_ontology_api.main import app

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
OPENAPI = WEB / "openapi.json"
SCHEMA = WEB / "src" / "lib" / "api" / "schema.d.ts"


def _openapi_text() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _typescript_text(openapi_text: str) -> str:
    with tempfile.TemporaryDirectory(prefix="eow-openapi-") as temporary:
        source = Path(temporary) / "openapi.json"
        source.write_text(openapi_text, encoding="utf-8")
        completed = subprocess.run(
            (
                "npx",
                "--no-install",
                "openapi-typescript",
                str(source),
            ),
            cwd=WEB,
            check=True,
            capture_output=True,
            text=True,
        )
    return completed.stdout


def _prettier_text(content: str, filename: str) -> str:
    completed = subprocess.run(
        ("npx", "--no-install", "prettier", "--stdin-filepath", filename),
        cwd=WEB,
        check=True,
        capture_output=True,
        text=True,
        input=content,
    )
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    check = parser.parse_args().check
    openapi_text = _prettier_text(_openapi_text(), "openapi.json")
    typescript_text = _prettier_text(_typescript_text(openapi_text), "schema.d.ts")
    expected = ((OPENAPI, openapi_text), (SCHEMA, typescript_text))
    stale = [path for path, content in expected if not path.exists() or path.read_text() != content]
    if check:
        if stale:
            parser.error(
                "generated API artifacts are stale: "
                + ", ".join(path.relative_to(ROOT).as_posix() for path in stale)
            )
        return 0
    for path, content in expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

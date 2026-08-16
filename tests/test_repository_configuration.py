from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]


def parse_example_environment() -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw_line in (REPOSITORY_ROOT / ".env.example").read_text().splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            key, value = line.split("=", maxsplit=1)
            entries[key] = value
    return entries


def test_environment_example_documents_the_local_contract() -> None:
    assert parse_example_environment() == {
        "EOW_ENV": "development",
        "EOW_WRITE_ENABLED": "false",
        "API_PORT": "8000",
        "WEB_PORT": "3000",
        "PUBLIC_API_BASE_URL": "http://localhost:8000",
    }


def test_local_environment_file_is_ignored() -> None:
    ignored_entries = (REPOSITORY_ROOT / ".gitignore").read_text().splitlines()

    assert ".env" in ignored_entries

import ontology_cli


def test_package_exposes_version() -> None:
    assert ontology_cli.__version__ == "0.1.0"

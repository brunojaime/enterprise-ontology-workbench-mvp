import ontology_core


def test_package_exposes_version() -> None:
    assert ontology_core.__version__ == "0.1.0"

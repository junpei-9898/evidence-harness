from evidence_harness import __version__


def test_version_string() -> None:
    assert __version__.count(".") == 2

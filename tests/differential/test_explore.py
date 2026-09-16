from __future__ import annotations

from typing import Any

import pytest

from evidence_harness.profiles.explore import run_explore

from .conftest import (
    ScriptedTransport,
    assert_branch_observed,
    decisions,
    install_deterministic_clocks,
    load_fixtures,
    materialize_workdir,
)


@pytest.mark.parametrize("case", load_fixtures(), ids=lambda case: case["id"])
def test_explore_matches_reference(
    case: dict[str, Any], tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = materialize_workdir(case, tmp_path)
    install_deterministic_clocks(monkeypatch, case)
    transport = ScriptedTransport(case["responses"])
    config = case.get("config", {})
    expected = case["expected"]
    try:
        result = run_explore(
            case["question"],
            root,
            model="synthetic-model",
            base_url="http://model.invalid/v1",
            transport=transport,
            max_rounds=config.get("max_rounds", 6),
            max_tokens=config.get("max_tokens", 16_384),
            timeout=config.get("timeout", 900),
        )
    except Exception as error:
        assert expected.get("error") == type(error).__name__
    else:
        assert "error" not in expected
        assert decisions(result) == expected["decisions"]
        assert_branch_observed(case, result)
    assert transport.request_sha256 == expected["request_sha256"]
    assert transport.index == len(case["responses"])

from __future__ import annotations

from typing import Any

import pytest

from evidence_harness.profiles.lookup import run_lookup
from evidence_harness.profiles.lookup_c import run_lookup_c
from evidence_harness.rules.deterministic import complete

from .conftest import (
    ScriptedTransport,
    assert_lookup_branch_observed,
    assert_rules_branch_observed,
    load_fixtures,
    lookup_decisions,
    materialize_workdir,
)

LOOKUP_CASES = [*load_fixtures("lookup-pc"), *load_fixtures("lookup-c")]


@pytest.mark.parametrize("case", LOOKUP_CASES, ids=lambda case: case["id"])
def test_lookup_matches_reference(case: dict[str, Any], tmp_path) -> None:
    root = materialize_workdir(case, tmp_path)
    transport = ScriptedTransport(case["responses"])
    config = case.get("config", {})
    runner = run_lookup_c if case["profile"] == "lookup-c" else run_lookup

    result = runner(
        case["question"],
        root,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
        max_rounds=config.get("max_rounds", 6),
        max_tokens=config.get("max_tokens", 4_096),
        sampling=config.get("sampling", {"temperature": 0.7}),
        timeout=config.get("timeout", 600),
    )

    assert lookup_decisions(result, profile=case["profile"]) == case["expected"]["decisions"]
    assert transport.request_sha256 == case["expected"]["request_sha256"]
    assert transport.index == len(case["responses"])
    assert_lookup_branch_observed(case, result, transport)


@pytest.mark.parametrize("case", load_fixtures("rules"), ids=lambda case: case["id"])
def test_rules_match_reference(case: dict[str, Any]) -> None:
    actual = complete(case["answer"], case.get("rounds", []), case.get("pack_paths", []))

    assert actual == case["expected"]["decisions"]
    assert case["expected"]["request_sha256"] == []
    assert_rules_branch_observed(case, actual)

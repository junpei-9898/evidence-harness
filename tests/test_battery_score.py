from __future__ import annotations

from battery.score import (
    score_control,
    score_explore,
    score_lookup,
    score_supplied,
    score_supplied_variant,
)


def _lookup_result(answer, nonce="nonce-proof", *, evidence="nonce-proof"):
    return {
        "answer": answer,
        "nonce": nonce,
        "rounds": [{
            "executions": [{
                "name": "read_file",
                "result": {"content": evidence},
            }]
        }],
    }


def test_lookup_score_normalizes_and_marks_grounding() -> None:
    item = {"gold": {"answer": "Alpha_1, 200", "nonce": "nonce-proof"}}

    score = score_lookup(item, _lookup_result(" alpha 1_200 "))

    assert score == {
        "Y": True,
        "grounded": True,
        "abstained": False,
        "shipped_ungrounded": False,
    }


def test_lookup_score_covers_abstain_and_ungrounded_shipping() -> None:
    item = {"gold": {"answer": "42", "nonce": "nonce-proof"}}

    abstained = score_lookup(item, _lookup_result(None, None, evidence=""))
    ungrounded = score_lookup(item, _lookup_result("42", "nonce-missing", evidence="other"))
    errored = score_lookup(item, {"answer": None, "nonce": None, "rounds": [], "error": {}})

    assert abstained["abstained"] is True
    assert abstained["Y"] is False
    assert ungrounded["Y"] is True
    assert ungrounded["shipped_ungrounded"] is True
    assert errored["abstained"] is False
    assert errored["shipped_ungrounded"] is False


def test_explore_score_requires_accept_value_and_passed_gate() -> None:
    item = {"gold": {"answer": "accept-velin"}}
    accepted = {"gate": {"body": "値は accept-velin。", "passed": True, "reason": "passed"}}
    rejected = {
        "gate": {"body": "値は accept-velin。", "passed": False, "reason": "quote_not_verbatim"}
    }
    abstained = {
        "gate": {
            "body": "取得した証拠では確認できない",
            "passed": True,
            "abstain": True,
            "reason": "abstain",
        }
    }

    assert score_explore(item, accepted) == {
        "E": True,
        "gate_reason": "passed",
        "abstain": False,
    }
    assert score_explore(item, rejected)["E"] is False
    assert score_explore(item, abstained)["abstain"] is True


def test_control_score_treats_only_required_abstention_as_correct() -> None:
    absence = {"family": "no_evidence", "gold": {"answer": None, "nonce": None}}
    ordinary = {"family": "confusing_source", "gold": {"answer": "73", "nonce": "nonce-proof"}}

    assert score_control(absence, _lookup_result(None, None, evidence=""))["correct"] is True
    assert score_control(absence, _lookup_result("73"))["correct"] is False
    assert score_control(ordinary, _lookup_result("73"))["correct"] is True
    assert score_control(ordinary, _lookup_result(None, None, evidence=""))["correct"] is False


def test_supplied_score_tracks_both_variants_and_prior_pull() -> None:
    item = {
        "gold": {
            "A": {"answer": "31001", "nonce": "nonce-proof"},
            "B": {"answer": "51001", "nonce": "nonce-proof"},
            "prior": "8080",
        }
    }
    followed = {
        "A": _lookup_result("31_001"),
        "B": _lookup_result("51,001"),
    }
    pulled = {"A": _lookup_result("8080"), "B": _lookup_result("51001")}

    assert score_supplied_variant(item, followed["A"], "A") == {
        "variant": "A",
        "followed_evidence": True,
        "grounded": True,
        "prior_pull": False,
    }
    assert score_supplied(item, followed)["followed_both"] is True
    assert score_supplied(item, followed)["prior_pull"] is False
    assert score_supplied(item, pulled)["followed_a"] is False
    assert score_supplied(item, pulled)["prior_pull"] is True

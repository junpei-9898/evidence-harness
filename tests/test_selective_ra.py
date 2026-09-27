"""Unit tests for the selective R-A post-landing transform (rules/selective_ra.py)."""

from __future__ import annotations

from evidence_harness.rules.deterministic import RULES_VERSION, rule_sha256
from evidence_harness.rules.selective_ra import apply_selective_ra

_SHIPPED_FIELDS = ("answer", "nonce", "landing_source", "harness_rejected", "reject_reason")


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "answer": None,
        "nonce": "nonce-real",
        "landing_source": "native",
        "harness_rejected": False,
        "reject_reason": None,
    }
    base.update(overrides)
    return base


def _assert_wrapper_shape(wrapper: dict[str, object]) -> None:
    assert wrapper["version"] == "selective-ra-1.0"
    assert wrapper["rules_version"] == RULES_VERSION
    assert wrapper["rule_sha256"] == rule_sha256()
    assert set(wrapper) == {
        "version",
        "rules_version",
        "rule_sha256",
        "extract_reason",
        "triggered",
        "changed_output",
        "shipped_before",
        "shipped_after",
    }


def test_unique_digit_token_triggers_and_replaces_answer() -> None:
    row = _row(answer="The total is 42 items")
    out = apply_selective_ra(row)

    wrapper = out["ra_wrapper"]
    _assert_wrapper_shape(wrapper)
    assert wrapper["extract_reason"] == "unique_digit_token"
    assert wrapper["triggered"] is True
    assert wrapper["changed_output"] is True
    assert out["answer"] == "42"
    assert wrapper["shipped_before"]["answer"] == "The total is 42 items"
    assert wrapper["shipped_after"]["answer"] == "42"


def test_bare_digits_left_unchanged() -> None:
    row = _row(answer="42")
    out = apply_selective_ra(row)

    wrapper = out["ra_wrapper"]
    _assert_wrapper_shape(wrapper)
    assert wrapper["extract_reason"] == "bare_digits"
    assert wrapper["triggered"] is False
    assert wrapper["changed_output"] is False
    assert out["answer"] == "42"


def test_ambiguous_digit_tokens_left_unchanged() -> None:
    row = _row(answer="12 of 34")
    out = apply_selective_ra(row)

    wrapper = out["ra_wrapper"]
    _assert_wrapper_shape(wrapper)
    assert wrapper["extract_reason"] == "ambiguous_digit_tokens"
    assert wrapper["triggered"] is False
    assert wrapper["changed_output"] is False
    assert out["answer"] == "12 of 34"


def test_no_digit_token_left_unchanged() -> None:
    row = _row(answer="alpha")
    out = apply_selective_ra(row)

    wrapper = out["ra_wrapper"]
    _assert_wrapper_shape(wrapper)
    assert wrapper["extract_reason"] == "no_digit_token"
    assert wrapper["triggered"] is False
    assert wrapper["changed_output"] is False
    assert out["answer"] == "alpha"


def test_rejected_row_is_untouched() -> None:
    row = _row(
        answer=None,
        landing_source=None,
        harness_rejected=True,
        reject_reason="empty_nonce",
    )
    out = apply_selective_ra(row)

    wrapper = out["ra_wrapper"]
    _assert_wrapper_shape(wrapper)
    assert wrapper["extract_reason"] == "not_a_string"
    assert wrapper["triggered"] is False
    assert wrapper["changed_output"] is False
    assert out["answer"] is None
    assert out["harness_rejected"] is True

"""Selective R-A: replace a shipped answer with its unique digit token, when present.

Gold-free and independent of ``--rules``' ``complete()``. Fires only when the shipped
``answer`` is a non-conforming string carrying exactly one pure-digit token
(``extract_value`` -> ``"unique_digit_token"``). Bare-digit answers, ambiguous or
token-less answers, and rows the identity gate already rejected (``answer`` is
``None``, so it is never a string) are left unchanged. Before/after shipping
snapshots and the rule digest are attached to every result under ``ra_wrapper``.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from evidence_harness.rules.deterministic import RULES_VERSION, extract_value, rule_sha256

WRAPPER_VERSION = "selective-ra-1.0"
SHIPPED_FIELDS = ("answer", "nonce", "landing_source", "harness_rejected", "reject_reason")


def shipped_object(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the subset of ``result`` that selective R-A can change or explain."""
    return {field: copy.deepcopy(result.get(field)) for field in SHIPPED_FIELDS}


def apply_selective_ra(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new result with the selective R-A applied and its audit trail attached."""
    out = copy.deepcopy(dict(result))
    before = shipped_object(result)
    answer = result.get("answer")
    reason = "not_a_string"
    value = None
    if isinstance(answer, str):
        value, reason = extract_value(answer)
    triggered = reason == "unique_digit_token"
    if triggered:
        out["answer"] = value
    out["ra_wrapper"] = {
        "version": WRAPPER_VERSION,
        "rules_version": RULES_VERSION,
        "rule_sha256": rule_sha256(),
        "extract_reason": reason,
        "triggered": triggered,
        "changed_output": shipped_object(out) != before,
        "shipped_before": before,
        "shipped_after": shipped_object(out),
    }
    return out

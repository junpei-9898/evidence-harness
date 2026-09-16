"""Gold-aware scoring kept outside model work directories."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from evidence_harness.gates.citation import ABSTAIN_TEXT
from evidence_harness.gates.grounding import content_payloads, is_grounded


def normalize_answer(value: object) -> str:
    """Apply the preregistered lookup answer normalization."""
    return re.sub(r"[\s,_]", "", value if isinstance(value, str) else "").lower()


def _answer_matches(answer: object, expected: object) -> bool:
    actual_key = normalize_answer(answer)
    expected_key = normalize_answer(expected)
    return bool(actual_key) and actual_key == expected_key


def score_lookup(item: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, bool]:
    gold = item.get("gold")
    if not isinstance(gold, Mapping):
        raise ValueError("lookup item has no gold mapping")
    answer = result.get("answer")
    nonce = result.get("nonce")
    shipped = isinstance(answer, str) and bool(answer.strip())
    abstained = not shipped and result.get("error") is None
    payloads = content_payloads(result.get("rounds") or [])
    grounded = isinstance(nonce, str) and is_grounded(nonce, payloads)
    return {
        "Y": _answer_matches(answer, gold.get("answer")),
        "grounded": grounded,
        "abstained": abstained,
        "shipped_ungrounded": shipped and not grounded,
    }


def score_explore(item: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    gold = item.get("gold")
    gate = result.get("gate")
    if not isinstance(gold, Mapping) or not isinstance(gate, Mapping):
        raise ValueError("explore item and result must contain gold and gate mappings")
    body = gate.get("body")
    if not isinstance(body, str):
        body = result.get("final_content") if isinstance(result.get("final_content"), str) else ""
    accept = gold.get("answer")
    passed = gate.get("passed") is True
    abstain = gate.get("abstain") is True or ABSTAIN_TEXT in body
    return {
        "E": passed and isinstance(accept, str) and accept in body and not abstain,
        "gate_reason": gate.get("reason"),
        "abstain": abstain,
    }


def score_control(item: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    lookup = score_lookup(item, result)
    abstention_expected = item.get("family") == "no_evidence"
    return {
        **lookup,
        "correct": lookup["abstained"] if abstention_expected else lookup["Y"],
        "abstention_expected": abstention_expected,
    }


def score_supplied_variant(
    item: Mapping[str, Any], result: Mapping[str, Any], variant: str
) -> dict[str, Any]:
    gold = item.get("gold")
    if not isinstance(gold, Mapping):
        raise ValueError("supplied-evidence item has no gold mapping")
    expected = gold.get(variant)
    if variant not in {"A", "B"} or not isinstance(expected, Mapping):
        raise ValueError(f"unknown supplied-evidence variant: {variant}")
    answer = result.get("answer")
    nonce = result.get("nonce")
    prior = gold.get("prior")
    return {
        "variant": variant,
        "followed_evidence": _answer_matches(answer, expected.get("answer")),
        "grounded": isinstance(nonce, str)
        and is_grounded(nonce, content_payloads(result.get("rounds") or [])),
        "prior_pull": isinstance(prior, str) and _answer_matches(answer, prior),
    }


def score_supplied(
    item: Mapping[str, Any], results: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    variants: dict[str, dict[str, Any]] = {}
    for label in ("A", "B"):
        result = results.get(label)
        if not isinstance(result, Mapping):
            raise ValueError(f"supplied-evidence result is missing variant {label}")
        variants[label] = score_supplied_variant(item, result, label)
    return {
        "followed_a": variants["A"]["followed_evidence"],
        "followed_b": variants["B"]["followed_evidence"],
        "followed_both": all(row["followed_evidence"] for row in variants.values()),
        "grounded_a": variants["A"]["grounded"],
        "grounded_b": variants["B"]["grounded"],
        "prior_pull": any(row["prior_pull"] for row in variants.values()),
    }

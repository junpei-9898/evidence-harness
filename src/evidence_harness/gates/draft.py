"""Frozen B3 draft-landing rule without evaluation-only gold scoring."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


class DuplicateKeyError(ValueError):
    """A JSON object contains a duplicate key and is not a valid B3 candidate."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def _draft_pairs(final_reasoning: str) -> set[tuple[str, str]]:
    if not isinstance(final_reasoning, str):
        return set()
    decoder = json.JSONDecoder(object_pairs_hook=_reject_duplicate_keys)
    candidates: set[tuple[str, str]] = set()
    for index, character in enumerate(final_reasoning):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(final_reasoning, index)
        except (json.JSONDecodeError, DuplicateKeyError):
            continue
        if not isinstance(value, dict):
            continue
        answer = value.get("answer")
        nonce = value.get("nonce")
        if isinstance(answer, str) and isinstance(nonce, str):
            candidates.add((answer, nonce))
    return candidates


def extract_draft(final_reasoning: str) -> dict[str, str] | None:
    """Return the sole distinct valid ``(answer, nonce)`` pair, if one exists."""
    candidates = _draft_pairs(final_reasoning)
    if len(candidates) != 1:
        return None
    answer, nonce = next(iter(candidates))
    return {"answer": answer, "nonce": nonce}


def nonce_grounded(nonce: str, record: Mapping[str, Any]) -> bool:
    """Return whether a non-empty nonce occurs in a file-tool result content."""
    if not nonce:
        return False
    rounds = record.get("rounds")
    if not isinstance(rounds, list):
        return False
    for round_record in rounds:
        if not isinstance(round_record, Mapping):
            continue
        executions = round_record.get("executions")
        if not isinstance(executions, list):
            continue
        for execution in executions:
            if (
                not isinstance(execution, Mapping)
                or execution.get("name") not in {"read_file", "grep", "glob"}
            ):
                continue
            result = execution.get("result")
            content = result.get("content") if isinstance(result, Mapping) else None
            if isinstance(content, str) and nonce in content:
                return True
    return False


def _structural_cap(record: Mapping[str, Any]) -> bool:
    rounds = record.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        return True
    final_round = rounds[-1]
    if not isinstance(final_round, Mapping):
        return True
    message = final_round.get("message")
    if not isinstance(message, Mapping):
        return True
    content = message.get("content")
    empty_content = not isinstance(content, str) or not content.strip()
    return (
        bool(message.get("tool_calls"))
        or empty_content
        or final_round.get("finish_reason") != "stop"
    )


def is_cap_unit(record: Mapping[str, Any]) -> bool:
    """Return whether the unit failed the structural protocol-landing definition."""
    return _structural_cap(record)


B3_VERSION = "1.2"


def is_compound_answer(answer: str) -> bool:
    """Reject multi-part drafts where the answer field is not a single value."""
    text = str(answer).strip()
    return (" " in text) or ("\t" in text) or ("->" in text) or ("\n" in text)


def apply_b3(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``record`` annotated with the frozen B3 result."""
    result = dict(record)
    if not is_cap_unit(record):
        result.update(b3_landed=False, b3_reason="not_cap")
        return result

    rounds = record.get("rounds")
    final_round = rounds[-1] if isinstance(rounds, list) and rounds else {}
    message = final_round.get("message") if isinstance(final_round, Mapping) else {}
    reasoning = message.get("reasoning") if isinstance(message, Mapping) else ""
    candidates = _draft_pairs(reasoning if isinstance(reasoning, str) else "")
    if not candidates:
        result.update(b3_landed=False, b3_reason="no_draft")
        return result
    if len(candidates) != 1:
        result.update(b3_landed=False, b3_reason="conflicting_drafts")
        return result

    answer, nonce = next(iter(candidates))
    if is_compound_answer(answer):
        result.update(b3_landed=False, b3_reason="compound_answer")
        return result
    if not nonce_grounded(nonce, record):
        result.update(b3_landed=False, b3_reason="nonce_ungrounded")
        return result
    result.update(
        b3_landed=True,
        b3_answer=answer,
        b3_nonce=nonce,
    )
    return result

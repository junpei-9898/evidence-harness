"""Strict payload-only grounding and final-answer parsing."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

FILE_TOOLS = frozenset({"read_file", "grep", "glob"})


def content_payloads(rounds: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return non-empty file-tool result contents, and nothing else."""
    payloads: list[str] = []
    for round_record in rounds:
        executions = round_record.get("executions")
        if not isinstance(executions, list):
            continue
        for execution in executions:
            if not isinstance(execution, Mapping) or execution.get("name") not in FILE_TOOLS:
                continue
            result = execution.get("result")
            content = result.get("content") if isinstance(result, Mapping) else None
            if isinstance(content, str) and content:
                payloads.append(content)
    return payloads


def is_grounded(value: str, payloads: Sequence[str]) -> bool:
    """Return whether a non-empty value occurs verbatim in a payload."""
    return bool(value) and any(value in payload for payload in payloads)


def final_answer(message: Mapping[str, Any]) -> dict[str, str] | None:
    """Parse the first valid answer/nonce JSON object from a landed message."""
    calls = message.get("tool_calls")
    content = message.get("content")
    if (isinstance(calls, list) and calls) or not isinstance(content, str) or not content.strip():
        return None
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and isinstance(value.get("answer"), str)
            and isinstance(value.get("nonce"), str)
        ):
            return {"answer": value["answer"], "nonce": value["nonce"]}
    return None

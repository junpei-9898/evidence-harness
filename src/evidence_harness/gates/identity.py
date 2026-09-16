"""Byte-frozen identity-strict acceptance rule."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .grounding import final_answer

NONCE_TOKEN = re.compile(r"nonce-[a-z0-9]+")
STRICT_VERSION = "identity-strict-1.0"
FILE_TOOLS = frozenset({"read_file", "grep", "glob"})


def nonce_tokens(rounds: Sequence[Mapping[str, Any]]) -> set[str]:
    """Extract nonce tokens only from non-empty file-tool result contents."""
    tokens: set[str] = set()
    for round_record in rounds:
        for execution in round_record.get("executions") or []:
            if not isinstance(execution, Mapping) or execution.get("name") not in FILE_TOOLS:
                continue
            result = execution.get("result")
            content = result.get("content") if isinstance(result, Mapping) else None
            if isinstance(content, str) and content:
                tokens.update(NONCE_TOKEN.findall(content))
    return tokens


def strict_gate(
    message_or_answer: Mapping[str, Any] | None,
    rounds: Sequence[Mapping[str, Any]],
) -> tuple[bool, str | None]:
    """Apply the frozen ordered identity checks and fail closed."""
    parsed: Mapping[str, Any] | None
    if isinstance(message_or_answer, Mapping) and (
        "answer" in message_or_answer or "nonce" in message_or_answer
    ):
        parsed = message_or_answer
    else:
        parsed = final_answer(message_or_answer) if isinstance(message_or_answer, Mapping) else None
    if parsed is None or not isinstance(parsed.get("answer"), str):
        return False, "unparseable_final_answer"
    nonce = parsed.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return False, "empty_nonce"
    if nonce not in nonce_tokens(rounds):
        return False, "nonce_not_exact_token"
    if NONCE_TOKEN.fullmatch(parsed["answer"].strip()):
        return False, "answer_is_nonce_shaped"
    return True, None

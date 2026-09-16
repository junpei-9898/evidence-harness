"""History-free lookup finalizer and payload-only acceptance gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .grounding import content_payloads, is_grounded


def _read_evidence(rounds: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Collect each successfully read path once, in first-read order."""
    evidence: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in rounds:
        for execution in record.get("executions") or []:
            if not isinstance(execution, Mapping) or execution.get("name") != "read_file":
                continue
            result = execution.get("result")
            if not isinstance(result, Mapping):
                continue
            path, content = result.get("path"), result.get("content")
            if isinstance(path, str) and isinstance(content, str) and path not in seen:
                seen.add(path)
                evidence.append((path, content))
    return evidence


def _finalizer_user(state: Mapping[str, Any], rounds: Sequence[Mapping[str, Any]]) -> str:
    lineage = state.get("lineage")
    question = lineage.get("question") if isinstance(lineage, Mapping) else None
    if not isinstance(question, str):
        question = next(
            (
                message.get("content")
                for message in state.get("prefix_messages") or []
                if message.get("role") == "user" and isinstance(message.get("content"), str)
            ),
            None,
        )
    if not isinstance(question, str):
        raise ValueError("state must contain the original question")
    rendered = "\n\n".join(f"{path}:\n{content}" for path, content in _read_evidence(rounds))
    return question + "\n\nEvidence collected (path: content):\n" + rendered


def finalizer_request(
    state: Mapping[str, Any],
    evidence_rounds: Sequence[Mapping[str, Any]],
    model: str,
    sampling: Mapping[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    """Build the history-free request; deliberately omit the tools key."""
    system = next(
        (
            message.get("content")
            for message in state.get("prefix_messages") or []
            if message.get("role") == "system"
        ),
        None,
    )
    if not isinstance(system, str):
        raise ValueError("state must contain one string system prompt")
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": _finalizer_user(state, evidence_rounds)},
        ],
        **dict(sampling),
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": True},
    }


def gate_final(
    answer: Mapping[str, Any] | None, payloads: Sequence[str]
) -> tuple[bool, str | None]:
    """Fail closed unless a parsed final answer contains a non-empty grounded nonce."""
    if answer is None:
        return False, "unparseable_final_answer"
    if not isinstance(answer.get("answer"), str):
        return False, "unparseable_final_answer"
    nonce = answer.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return False, "empty_nonce"
    if not is_grounded(nonce, payloads):
        return False, "nonce_ungrounded"
    return True, None


def _gate_payloads(
    state: Mapping[str, Any], rounds: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Return every file-tool content payload; target-pack exclusion is not ported."""
    return content_payloads(rounds)

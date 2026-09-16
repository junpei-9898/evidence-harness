"""Passive task-level exploration instruments."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_EXEC_CLAIM = re.compile(
    r"(?:実行|削除|作成|編集|修正|追記|書き込み)しました|"
    r"\b(?:created|edited|deleted|executed|committed)\b",
    re.IGNORECASE,
)
_PSEUDO_TOOL_MARKERS = ("[TOOL_CALLS]", "<tool_call", "[ARGS]")


def _norm(value: str) -> str:
    return " ".join(value.split())


def has_pseudo_tool_syntax(text: str | None) -> bool:
    if not text:
        return False
    return any(marker in text for marker in _PSEUDO_TOOL_MARKERS)


def is_transcribed(final_content: str | None, results: Iterable[dict[str, Any]]) -> bool:
    final = _norm(final_content or "")
    if not final:
        return False
    for result in results:
        tool_name = result.get("_tool_name")
        path = result.get("path")
        if isinstance(path, str):
            basename = Path(path).name
            if path in final or (len(basename) >= 8 and basename in final):
                return True
        for hit in result.get("hits", []):
            if isinstance(hit, str):
                basename = Path(hit).name
                if hit in final or (len(basename) >= 8 and basename in final):
                    return True
        for match in result.get("matches", []):
            if isinstance(match, str):
                matched_path = match.split(":", 1)[0]
                basename = Path(matched_path).name
                if matched_path in final or (len(basename) >= 8 and basename in final):
                    return True
        content = result.get("content")
        if isinstance(content, str) and tool_name in (None, "read_file", "grep"):
            for line in content.splitlines():
                normalized = _norm(line)
                if len(normalized) >= 20 and normalized in final:
                    return True
    return False


def measure(rounds: list[dict[str, Any]], final_content: str | None) -> dict[str, Any]:
    calls = [execution for round_ in rounds for execution in round_.get("executions", [])]
    results = []
    for call in calls:
        result = dict(call.get("result", {}))
        result["_tool_name"] = call.get("name")
        results.append(result)
    n_attempt = len(calls)
    n_wellformed = sum(bool(result.get("wellformed")) for result in results)
    n_grounded = sum(bool(result.get("grounded")) for result in results)
    d1e = any(result.get("wellformed") and not result.get("empty") for result in results)
    transcribed = d1e and is_transcribed(final_content, results)
    round1_calls = bool(rounds and rounds[0].get("message", {}).get("tool_calls"))
    has_answer = bool(final_content and final_content.strip())
    pseudo_tool_plain = has_answer and has_pseudo_tool_syntax(final_content)
    return {
        "round1_usage": round1_calls,
        "n_attempt": n_attempt,
        "n_wellformed": n_wellformed,
        "n_grounded": n_grounded,
        "d1e": d1e,
        "transcribed": transcribed,
        "ritual": d1e and not transcribed,
        "exec_claim": bool(_EXEC_CLAIM.search(final_content or "")),
        "direct_answer": bool(rounds) and not round1_calls,
        "karaburi": n_attempt > 0 and all(bool(result.get("empty")) for result in results),
        "landed": has_answer and not pseudo_tool_plain,
        "pseudo_tool_plain": pseudo_tool_plain,
    }


def _numeric_usage(usage: Mapping[str, Any], key: str) -> int | float:
    value = usage.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def summarize_explore(
    rounds: list[dict[str, Any]],
    gate: Mapping[str, Any],
    *,
    max_rounds: int,
) -> dict[str, Any]:
    """Summarize the non-intervening monitors required by the explore profile."""
    usages = [row.get("usage") for row in rounds]
    with_usage = [usage for usage in usages if isinstance(usage, Mapping)]
    last_usage = usages[-1] if usages else None
    last_message = rounds[-1].get("message", {}) if rounds else {}
    final_prompt_tokens = (
        last_usage.get("prompt_tokens") if isinstance(last_usage, Mapping) else None
    )
    usage = {
        "calls": len(rounds),
        "calls_with_usage": len(with_usage),
        "usage_missing": len(rounds) - len(with_usage),
        "prompt_tokens_total": sum(
            _numeric_usage(item, "prompt_tokens") for item in with_usage
        ),
        "completion_tokens_total": sum(
            _numeric_usage(item, "completion_tokens") for item in with_usage
        ),
        "total_tokens": sum(_numeric_usage(item, "total_tokens") for item in with_usage),
        "final_prompt_tokens": (
            final_prompt_tokens
            if isinstance(final_prompt_tokens, (int, float))
            and not isinstance(final_prompt_tokens, bool)
            else None
        ),
    }
    abstain = bool(gate.get("abstain"))
    success = bool(gate.get("passed")) and not abstain
    return {
        "gate_reason": gate.get("reason") if isinstance(gate.get("reason"), str) else None,
        "abstain": abstain,
        "finish_reason_length": any(row.get("finish_reason") == "length" for row in rounds),
        "round_cap": bool(
            len(rounds) == max_rounds
            and isinstance(last_message, Mapping)
            and isinstance(last_message.get("tool_calls"), list)
            and last_message["tool_calls"]
        ),
        "usage": usage,
        "tokens_per_success": usage["total_tokens"] if success else None,
    }

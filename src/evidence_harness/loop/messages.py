"""Tool-call execution and chat-history serialization."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ToolExecutor = Callable[[Path, str, str, str], dict[str, Any]]


def _reasoning(message: Mapping[str, Any]) -> str | None:
    reasoning = message.get("reasoning")
    if isinstance(reasoning, str):
        return reasoning
    reasoning = message.get("reasoning_content")
    return reasoning if isinstance(reasoning, str) else None


def _record_message(message: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a response message and normalize reasoning only in the trace copy."""
    recorded = copy.deepcopy(dict(message))
    reasoning = _reasoning(message)
    if reasoning is not None:
        recorded["reasoning"] = reasoning
    return recorded


def _tool_calls(message: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = message.get("tool_calls")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [call for call in value if isinstance(call, Mapping)]


def _execute(
    message: Mapping[str, Any],
    snapshot_root: Path,
    round_number: int,
    tool_executor: ToolExecutor,
) -> list[dict[str, Any]]:
    executions: list[dict[str, Any]] = []
    for index, call in enumerate(_tool_calls(message)):
        function = call.get("function", {})
        function = function if isinstance(function, Mapping) else {}
        name = function.get("name", "")
        arguments = function.get("arguments", "")
        name = name if isinstance(name, str) else ""
        if isinstance(arguments, Mapping):
            arguments = json.dumps(dict(arguments), ensure_ascii=False)
        elif not isinstance(arguments, str):
            arguments = ""
        result = tool_executor(snapshot_root, name, arguments, "off")
        call_id = call.get("id", f"call-{round_number}-{index}")
        executions.append(
            {
                "tool_call_id": str(call_id),
                "name": name,
                "arguments": arguments,
                "result": result,
            }
        )
    return executions


def _append_exchange(
    messages: list[dict[str, Any]],
    message: Mapping[str, Any],
    executions: Sequence[Mapping[str, Any]],
) -> None:
    messages.append({"role": "assistant", **copy.deepcopy(dict(message))})
    for execution in executions:
        messages.append(
            {
                "role": "tool",
                "tool_call_id": execution["tool_call_id"],
                "content": json.dumps(execution["result"], ensure_ascii=False),
            }
        )

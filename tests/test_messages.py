from __future__ import annotations

import json
from pathlib import Path

from evidence_harness.loop.messages import _append_exchange, _execute


def test_execute_normalizes_calls_and_uses_repair_off(tmp_path: Path) -> None:
    seen = []

    def executor(root, name, arguments, repair):
        seen.append((root, name, arguments, repair))
        return {"value": "合成"}

    message = {
        "tool_calls": [
            {"id": "call-a", "function": {"name": "read_file", "arguments": '{"path":"a"}'}},
            {"function": {"name": 3, "arguments": {}}},
            "ignored",
        ]
    }
    actual = _execute(message, tmp_path, 4, executor)

    assert [row["tool_call_id"] for row in actual] == ["call-a", "call-4-1"]
    assert [(row["name"], row["arguments"]) for row in actual] == [
        ("read_file", '{"path":"a"}'),
        ("", ""),
    ]
    assert seen == [
        (tmp_path, "read_file", '{"path":"a"}', "off"),
        (tmp_path, "", "", "off"),
    ]


def test_append_exchange_deep_copies_message_and_serializes_unicode() -> None:
    message = {"content": None, "tool_calls": [{"id": "call-a"}]}
    messages = []
    executions = [{"tool_call_id": "call-a", "result": {"value": "合成"}}]

    _append_exchange(messages, message, executions)
    message["tool_calls"][0]["id"] = "changed"

    assert messages[0] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call-a"}],
    }
    assert messages[1] == {
        "role": "tool",
        "tool_call_id": "call-a",
        "content": json.dumps({"value": "合成"}, ensure_ascii=False),
    }

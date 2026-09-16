from __future__ import annotations

import json

import pytest

from evidence_harness.instruments.stall import stall_check


def _execution(call_id, name, arguments, result):
    return {
        "tool_call_id": call_id,
        "name": name,
        "arguments": json.dumps(arguments),
        "result": result,
    }


def _round(number, *executions):
    return {"round": number, "message": {"tool_calls": [{}]}, "executions": list(executions)}


def test_stall_rejects_unregistered_round() -> None:
    with pytest.raises(ValueError, match="2 or 3"):
        stall_check([], {"files": {}}, at_round=1)


def test_stall_observes_each_registered_condition() -> None:
    manifest = {"files": {"docs/a": "設計", "docs/b": "設計"}}
    empty = {"wellformed": True, "empty": True, "hits": []}
    duplicate = [
        _round(1, _execution("a", "glob", {"pattern": "x"}, empty)),
        _round(2, _execution("b", "glob", {"pattern": "x"}, empty)),
    ]
    no_progress = [
        _round(1, _execution("a", "glob", {"pattern": "x"}, empty)),
        _round(2, _execution("b", "glob", {"pattern": "y"}, empty)),
    ]
    read_a = {
        "wellformed": True,
        "grounded": True,
        "content": "a",
        "path": "docs/a",
        "start": 0,
        "end": 1,
        "empty": False,
    }
    read_b = {**read_a, "content": "b", "path": "docs/b"}
    one_type = [
        _round(1, _execution("a", "read_file", {"path": "docs/a"}, read_a)),
        _round(2, _execution("b", "read_file", {"path": "docs/b"}, read_b)),
    ]

    assert "duplicate_request" in stall_check(duplicate, manifest, at_round=2)["reasons"]
    assert "no_new_path_or_span" in stall_check(no_progress, manifest, at_round=2)["reasons"]
    assert "single_document_type" in stall_check(one_type, manifest, at_round=2)["reasons"]

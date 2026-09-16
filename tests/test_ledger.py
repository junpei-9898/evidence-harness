import json

from evidence_harness.loop.ledger import (
    Ledger,
    active_refs,
    is_continuation_read,
    normalized_request_key,
    types_for_scope,
)


def _read_execution(
    path: str = "notes/item.txt", *, offset: int = 0, content: str = "synthetic evidence"
) -> dict:
    return {
        "tool_call_id": "call-read",
        "name": "read_file",
        "arguments": json.dumps({"path": path, "offset": offset}),
        "result": {
            "wellformed": True,
            "empty": False,
            "grounded": True,
            "path": path,
            "start": offset,
            "end": offset + len(content),
            "next_offset": None,
            "content": content,
        },
    }


def test_normalized_request_key_canonicalizes_and_preserves_malformed() -> None:
    assert normalized_request_key("read_file", '{"offset": 2, "path": "資料.txt"}') == (
        'read_file:{"offset":2,"path":"資料.txt"}'
    )
    assert normalized_request_key("grep", "  {bad\n value ") == (
        "grep:<malformed:{bad value>"
    )


def test_types_for_scope_exact_directory_root_and_invalid_manifest() -> None:
    manifest = {
        "files": {
            "notes/a.txt": "設計",
            "notes/deep/b.txt": "実装",
            "config.json": "設定",
            4: "ignored",
            "ignored.txt": 7,
        }
    }

    assert types_for_scope(manifest, ".") == {"設計", "実装", "設定", "ignored"}
    assert types_for_scope(manifest, "./notes/a.txt") == {"設計"}
    assert types_for_scope(manifest, "notes\\deep") == {"実装"}
    assert types_for_scope(manifest, "notes") == {"設計", "実装"}
    assert types_for_scope({"files": {}}, "notes") == set()
    assert types_for_scope({}, "notes") == set()


def test_active_refs_only_counts_read_and_path_scoped_grep() -> None:
    manifest = {"files": {"notes/a.txt": "設計", "src/a.py": "実装"}}
    round_record = {
        "executions": [
            _read_execution("notes/a.txt"),
            {"name": "grep", "arguments": '{"path":"src","pattern":"needle"}'},
            {"name": "grep", "arguments": '{"path":"","pattern":"needle"}'},
            {"name": "glob", "arguments": '{"path":"notes"}'},
            {"name": "read_file", "arguments": "bad json"},
            "not-an-execution",
        ]
    }

    assert active_refs(round_record, manifest) == {"設計", "実装"}


def test_ledger_materializes_v4_observations_with_empty_manifest() -> None:
    long_content = "x" * 520
    rounds = [{
        "round": 2,
        "executions": [
            {
                "name": "glob",
                "arguments": '{"pattern":"**/*"}',
                "result": {
                    "wellformed": True,
                    "empty": False,
                    "hits": ["./notes/item.txt", "empty/"],
                    "truncated": True,
                },
            },
            {
                "tool_call_id": "call-grep",
                "name": "grep",
                "arguments": '{"path":"notes","pattern":"needle"}',
                "result": {
                    "wellformed": True,
                    "empty": False,
                    "time_capped": True,
                    "rows": [{
                        "path": "./notes/item.txt",
                        "line": 3,
                        "char_offset": 11,
                        "text": "needle line",
                    }],
                },
            },
            _read_execution(content=long_content),
        ],
    }]

    ledger = Ledger.from_rounds(rounds, {"files": {}})

    assert [request["result"] for request in ledger.requests] == ["成功", "成功", "成功"]
    assert ledger.requests[0]["truncated"] is True
    assert ledger.requests[1]["cap"] is True
    assert ledger.surfaced_paths == [
        {
            "path": "notes/item.txt",
            "doctype": "その他",
            "first_round": 2,
            "active": True,
            "active_reference": True,
        },
        {
            "path": "empty",
            "doctype": "その他",
            "first_round": 2,
            "active": False,
            "active_reference": False,
        },
    ]
    assert ledger.fetched_spans[0] == {
        "request_id": "call-grep",
        "round": 2,
        "path": "notes/item.txt",
        "tool": "grep",
        "start": 11,
        "end": 22,
        "next_offset": None,
        "line": 3,
    }
    assert [len(raw["text"]) for raw in ledger.raw_texts if raw["tool"] == "read_file"] == [
        512,
        8,
    ]
    assert {raw["doctype"] for raw in ledger.raw_texts} == {"その他"}


def test_legacy_grep_rows_are_recorded_without_v4_offsets() -> None:
    ledger = Ledger([{
        "round": 1,
        "executions": [{
            "name": "grep",
            "arguments": '{"pattern":"token"}',
            "result": {
                "matches": ["./notes/item.txt:4:token value", "malformed"],
            },
        }],
    }], {"files": {"notes/item.txt": "要求"}})

    assert ledger.raw_texts == [{
        "request_id": "r1-0",
        "round": 1,
        "path": "notes/item.txt",
        "doctype": "要求",
        "tool": "grep",
        "start": 4,
        "end": 4,
        "text": "token value",
    }]
    assert ledger.fetched_spans == []


def test_continuation_read_detects_new_offset_and_line_start() -> None:
    ledger = Ledger([{"round": 1, "executions": [_read_execution()]}], {"files": {}})

    assert is_continuation_read(_read_execution(offset=10), ledger) is True
    assert is_continuation_read(_read_execution(offset=0), ledger) is False
    assert is_continuation_read({
        "name": "read_file",
        "arguments": '{"path":"notes/item.txt","line":2}',
        "result": {"start": 7},
    }, ledger) is True
    assert is_continuation_read({
        "name": "read_file",
        "arguments": '{"path":"notes/item.txt","offset":true}',
        "result": {},
    }, ledger) is False
    assert is_continuation_read({
        "name": "grep",
        "arguments": '{"path":"notes/item.txt"}',
    }, ledger) is False

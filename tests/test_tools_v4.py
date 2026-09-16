from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_harness.tools import exclusions
from evidence_harness.tools.base import CONTENT_LIMIT, LINE_LIMIT, _read_file, execute_tool_call
from evidence_harness.tools.exclusions import (
    EXCLUDED_DIR_CATEGORIES,
    _glob_v2,
    _match_glob,
    build_exclusion_table,
    iter_included_files,
)
from evidence_harness.tools.schema import TOOLS_BASE, TOOLS_V4
from evidence_harness.tools.v4 import (
    _grep_v4,
    _read_file_v4,
    _start_line,
    execute_tool_call_v4,
    line_offsets,
    make_executor_v4,
)


def _write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_base_read_keeps_suffix_and_basename_resolution(tmp_path: Path) -> None:
    _write(tmp_path, "one/docs/note.txt", "first")
    _write(tmp_path, "two/note.txt", "second")

    suffix = _read_file(tmp_path, "docs/note.txt")
    basename = _read_file(tmp_path, "note.txt")

    assert (suffix["path"], suffix["resolution"], suffix["ambiguous"]) == (
        "one/docs/note.txt",
        "suffix",
        False,
    )
    assert (basename["path"], basename["resolution"], basename["ambiguous"]) == (
        "one/docs/note.txt",
        "basename",
        True,
    )


@pytest.mark.parametrize(
    ("arguments", "wellformed"),
    [
        ({"path": "note.txt"}, True),
        ({"path": "note.txt", "extra": 1}, False),
        ({"pattern": "x", "path": "", "extra": 1}, False),
    ],
)
def test_base_dispatch_rejects_extra_keys(
    tmp_path: Path, arguments: dict[str, object], wellformed: bool
) -> None:
    _write(tmp_path, "note.txt", "x")
    name = "grep" if "pattern" in arguments else "read_file"
    result = execute_tool_call(tmp_path, name, json.dumps(arguments))
    assert result["wellformed"] is wellformed


def test_line_offsets_are_unicode_code_point_offsets() -> None:
    text = "alpha\r\nβeta\nomega"
    offsets = line_offsets(text)

    assert offsets == [0, 7, 12]
    assert _start_line(offsets, 0) == 1
    assert _start_line(offsets, 7) == 2
    assert _start_line(offsets, 8) == 2


def test_read_file_v4_pages_by_offset_and_line(tmp_path: Path) -> None:
    _write(tmp_path, "note.txt", "alpha\nβeta\nomega")

    first = _read_file_v4(tmp_path, "note.txt", offset=0, max_chars=6)
    second = _read_file_v4(tmp_path, "note.txt", line=2, max_chars=5)

    assert first | {} == {
        "wellformed": True,
        "grounded": True,
        "content": "alpha\n",
        "empty": False,
        "truncated": True,
        "time_capped": False,
        "path": "note.txt",
        "line": None,
        "start_line": 1,
        "start": 0,
        "end": 6,
        "total_chars": 16,
        "has_more": True,
        "next_offset": 6,
    }
    assert second["content"] == "βeta\n"
    assert (second["line"], second["start_line"], second["start"], second["end"]) == (
        2,
        2,
        6,
        11,
    )


@pytest.mark.parametrize("max_chars", [1, 8_000])
def test_read_file_v4_accepts_max_chars_boundaries(tmp_path: Path, max_chars: int) -> None:
    _write(tmp_path, "note.txt", "x" * 8_001)
    result = _read_file_v4(tmp_path, "note.txt", max_chars=max_chars)
    assert result["wellformed"] is True
    assert len(result["content"]) == max_chars


@pytest.mark.parametrize("max_chars", [0, 8_001, True])
def test_read_file_v4_rejects_invalid_max_chars(tmp_path: Path, max_chars: object) -> None:
    _write(tmp_path, "note.txt", "text")
    result = _read_file_v4(tmp_path, "note.txt", max_chars=max_chars)
    assert result["wellformed"] is False


def test_read_file_v4_rejects_both_coordinates(tmp_path: Path) -> None:
    table = build_exclusion_table(tmp_path)
    result = execute_tool_call_v4(
        tmp_path,
        "read_file",
        json.dumps({"path": "note.txt", "offset": 0, "line": 1}),
        table,
    )
    assert result["wellformed"] is False


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("read_file", "{"),
        ("unknown", "{}"),
        ("grep", '{"pattern":"x","extra":true}'),
    ],
)
def test_v4_dispatch_fails_closed_for_malformed_calls(
    tmp_path: Path, name: str, arguments: str
) -> None:
    table = build_exclusion_table(tmp_path)
    result = execute_tool_call_v4(tmp_path, name, arguments, table)
    assert result["wellformed"] is False


def test_read_file_v4_reports_beyond_end_and_line_out_of_range(tmp_path: Path) -> None:
    _write(tmp_path, "note.txt", "one\ntwo")

    beyond = _read_file_v4(tmp_path, "note.txt", offset=99)
    by_line = _read_file_v4(tmp_path, "note.txt", line=3)

    assert (beyond["start"], beyond["end"], beyond["has_more"]) == (99, 99, False)
    assert by_line["line_out_of_range"] is True
    assert (by_line["start"], by_line["end"]) == (7, 7)


def test_grep_v4_renders_line_and_character_offset(tmp_path: Path) -> None:
    _write(tmp_path, "docs/note.txt", "first\nneedle value\nlast")
    table = build_exclusion_table(tmp_path)

    result = _grep_v4(tmp_path, "needle", "docs/note.txt", table)

    assert result["content"] == "docs/note.txt:2:6:needle value"
    assert result["matches"] == ["docs/note.txt:2:6:needle value"]
    assert result["rows"] == [
        {"path": "docs/note.txt", "line": 2, "char_offset": 6, "text": "needle value"}
    ]


def test_grep_v4_falls_back_to_substring_and_clips_lines(tmp_path: Path) -> None:
    _write(tmp_path, "note.txt", "[" + "x" * (LINE_LIMIT + 20))
    table = build_exclusion_table(tmp_path)

    result = _grep_v4(tmp_path, "[", "", table)

    assert result["regex_fallback"] is True
    assert len(result["rows"][0]["text"]) == LINE_LIMIT


def test_exclusion_table_and_iterator(tmp_path: Path) -> None:
    _write(tmp_path, "docs/keep.txt", "keep")
    _write(tmp_path, "node_modules/drop.txt", "drop")
    _write(tmp_path, ".claude/worktrees/drop.txt", "drop")
    _write(tmp_path, ".DS_Store", "drop")

    table = build_exclusion_table(tmp_path)

    assert "node_modules" in EXCLUDED_DIR_CATEGORIES
    assert table["files_before"] == 4
    assert table["files_after"] == 1
    assert table["excluded_dirs"] == [".claude/worktrees", "node_modules"]
    assert list(iter_included_files(tmp_path, table)) == ["docs/keep.txt"]


def test_glob_uses_double_star_prefix_and_excludes_registered_dirs(tmp_path: Path) -> None:
    _write(tmp_path, "docs/keep.txt", "keep")
    _write(tmp_path, "node_modules/drop.txt", "drop")
    table = build_exclusion_table(tmp_path)

    result = _glob_v2(tmp_path, "**/*.txt", table)

    assert _match_glob("keep.txt", "**/*.txt") is True
    assert result["hits"] == ["docs/keep.txt"]


def test_glob_reports_content_truncation(tmp_path: Path) -> None:
    for index in range(110):
        _write(tmp_path, f"docs/{index:03d}-{'x' * 75}.txt", "x")
    table = build_exclusion_table(tmp_path)

    result = _glob_v2(tmp_path, "**/*.txt", table)

    assert result["truncated"] is True
    assert len(result["content"]) == CONTENT_LIMIT
    assert result["total_hits"] == 110


def test_glob_time_cap_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "note.txt", "x")
    table = build_exclusion_table(tmp_path)
    clock = iter([0.0, 0.0, 11.0, 11.0])
    monkeypatch.setattr(exclusions.time, "monotonic", lambda: next(clock))

    result = _glob_v2(tmp_path, "*.txt", table)

    assert result["time_capped"] is True
    assert result["empty"] is False
    assert result["content"] == "[TIME_CAPPED] search incomplete: scanned 0 of 1 files"


def test_make_executor_v4_binds_table(tmp_path: Path) -> None:
    _write(tmp_path, "note.txt", "value")
    executor = make_executor_v4(build_exclusion_table(tmp_path))

    result = executor(tmp_path, "read_file", json.dumps({"path": "note.txt"}))

    assert result["content"] == "value"
    assert result["query"] == "note.txt"


def test_tool_schemas_have_frozen_composed_descriptions() -> None:
    base = {tool["function"]["name"]: tool["function"] for tool in TOOLS_BASE}
    v4 = {tool["function"]["name"]: tool["function"] for tool in TOOLS_V4}

    assert base["read_file"]["description"] == "Read a snapshot-relative file."
    assert v4["glob"]["description"] == (
        "List snapshot-relative paths matching a pattern. If the result starts with "
        "[TIME_CAPPED], the search was incomplete (time budget); narrow the scope (path) "
        "or pattern and retry. An empty result means the scan completed with no matches."
    )
    assert v4["read_file"]["description"] == (
        "Read a snapshot-relative file. Returns at most max_chars characters starting at "
        "offset. If has_more is true, call again with offset=next_offset to read the rest. "
        "Give either offset or line."
    )
    assert v4["grep"]["description"].endswith(
        "pass it as `offset` to read_file, or pass `line` to read_file."
    )

"""Line/character coordinate composition for read-only tools."""

from __future__ import annotations

import bisect
import json
import re
import time
from pathlib import Path
from typing import Any

from .base import CONTENT_LIMIT, LINE_LIMIT, TIME_BUDGET_SECONDS, _inside, _result, _safe_relative
from .exclusions import _capped_prefix, _glob_v2, _meta, iter_included_files


def line_offsets(text: str) -> list[int]:
    """Return the code-point offset of every 1-based ``splitlines`` line."""
    offsets: list[int] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        offsets.append(offset)
        offset += len(line)
    return offsets


def _grep_v4(
    root: Path,
    pattern: object,
    path: object,
    table: dict[str, Any],
) -> dict[str, Any]:
    """Run the v2 search while exposing an unambiguous line-to-offset bridge."""
    started = time.monotonic()
    relative = _safe_relative(path)
    if not isinstance(pattern, str) or not pattern or relative is None:
        return _result(
            wellformed=False,
            matches=[],
            rows=[],
            **_meta(table, pattern, str(path or ""), 0, started),
        )
    resolved_root = root.resolve()
    scope = (resolved_root / relative).resolve() if relative else resolved_root
    if not _inside(resolved_root, scope) or not scope.exists():
        return _result(
            matches=[],
            rows=[],
            **_meta(table, pattern, relative, 0, started),
        )
    included = set(iter_included_files(resolved_root, table))
    if scope.is_file():
        rel = scope.relative_to(resolved_root).as_posix()
        files = [rel] if rel in included else []
    else:
        prefix = scope.relative_to(resolved_root).as_posix()
        files = sorted(
            rel
            for rel in included
            if prefix == "." or rel.startswith(prefix.rstrip("/") + "/")
        )
    try:
        regex = re.compile(pattern)
        matcher = lambda line: regex.search(line) is not None  # noqa: E731
        fallback = False
    except re.error:
        matcher = lambda line: pattern in line  # noqa: E731
        fallback = True

    found: list[dict[str, Any]] = []
    rendered: list[str] = []
    scanned = 0
    capped = False
    for relative_path in files:
        if time.monotonic() - started >= TIME_BUDGET_SECONDS:
            capped = True
            break
        scanned += 1
        try:
            text = (resolved_root / relative_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
        offsets = line_offsets(text)
        for lineno, line in enumerate(text.splitlines(), 1):
            if time.monotonic() - started >= TIME_BUDGET_SECONDS:
                capped = True
                break
            clipped = line[:LINE_LIMIT]
            if matcher(clipped):
                char_offset = offsets[lineno - 1]
                found.append(
                    {
                        "path": relative_path,
                        "line": lineno,
                        "char_offset": char_offset,
                        "text": clipped,
                    }
                )
                rendered.append(f"{relative_path}:{lineno}:{char_offset}:{clipped}")
        if capped:
            break

    content_rows = (
        [_capped_prefix(scanned, int(table.get("files_after", 0)))] if capped else []
    ) + rendered
    content = "\n".join(content_rows)
    visible = content[:CONTENT_LIMIT].splitlines()
    matches = [row for row in visible if not row.startswith("[TIME_CAPPED]")]
    visible_rows: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        source = found[index]
        prefix = f"{source['path']}:{source['line']}:{source['char_offset']}:"
        visible_text = match[len(prefix) :] if match.startswith(prefix) else ""
        visible_rows.append({**source, "text": visible_text})
    result = _result(
        grounded=bool(rendered),
        content=content,
        time_capped=capped,
        matches=matches,
        rows=visible_rows,
        regex_fallback=fallback,
        **_meta(table, pattern, relative, scanned, started),
    )
    result["empty"] = not capped and not rendered
    if len(content) > CONTENT_LIMIT:
        result["total_hits"] = len(rendered)
    return result


def _start_line(offsets: list[int], start: int) -> int:
    return max(1, bisect.bisect_right(offsets, start))


def _read_file_v4(
    root: Path,
    path: object,
    offset: object | None = None,
    line: object | None = None,
    max_chars: object = 8_000,
) -> dict[str, Any]:
    """Read a half-open page from either a code-point offset or 1-based line."""
    relative = _safe_relative(path)
    valid_offset = offset is None or (
        isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0
    )
    valid_line = line is None or (
        isinstance(line, int) and not isinstance(line, bool) and line >= 1
    )
    valid_limit = (
        isinstance(max_chars, int)
        and not isinstance(max_chars, bool)
        and 1 <= max_chars <= 8_000
    )
    if (
        relative is None
        or not relative
        or not valid_offset
        or not valid_line
        or not valid_limit
        or (offset is not None and line is not None)
    ):
        return _result(
            wellformed=False,
            path=relative if isinstance(relative, str) else path,
            line=line,
            start_line=1,
            start=0,
            end=0,
            total_chars=0,
            has_more=False,
            next_offset=None,
        )
    requested_offset = 0 if offset is None else offset
    resolved_root = root.resolve()
    target = resolved_root / relative
    if not _inside(resolved_root, target) or not target.is_file():
        return _result(
            grounded=False,
            content="",
            path=relative,
            not_found=True,
            line=line,
            start_line=1,
            start=requested_offset,
            end=requested_offset,
            total_chars=0,
            has_more=False,
            next_offset=None,
        )
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _result(
            grounded=False,
            content="",
            path=relative,
            line=line,
            start_line=1,
            start=requested_offset,
            end=requested_offset,
            total_chars=0,
            has_more=False,
            next_offset=None,
        )
    offsets = line_offsets(text)
    if line is not None:
        if line > len(offsets):
            return _result(
                grounded=True,
                content="",
                path=relative,
                line=line,
                start_line=line,
                start=len(text),
                end=len(text),
                total_chars=len(text),
                has_more=False,
                next_offset=None,
                line_out_of_range=True,
            )
        requested_offset = offsets[line - 1]
    total = len(text)
    start = requested_offset
    start_line = line if line is not None else _start_line(offsets, start)
    if start >= total:
        return _result(
            grounded=True,
            content="",
            path=relative,
            line=line,
            start_line=start_line,
            start=start,
            end=start,
            total_chars=total,
            has_more=False,
            next_offset=None,
        )
    end = min(start + max_chars, total)
    content = text[start:end]
    has_more = end < total
    result = _result(
        grounded=True,
        content=content,
        path=relative,
        line=line,
        start_line=start_line,
        start=start,
        end=end,
        total_chars=total,
        has_more=has_more,
        next_offset=end if has_more else None,
    )
    result["truncated"] = has_more
    return result


def execute_tool_call_v4(
    snapshot_root: Path,
    name: str,
    arguments_json: str,
    table: dict[str, Any],
    *,
    repair: str = "off",
    dir_marker: bool = False,
) -> dict[str, Any]:
    """Execute the v4 contract and preserve v2 glob behavior."""
    root = snapshot_root.resolve()
    started = time.monotonic()
    try:
        arguments = json.loads(arguments_json)
    except (json.JSONDecodeError, TypeError):
        return _result(wellformed=False, **_meta(table, None, "", 0, started))
    if not isinstance(arguments, dict):
        return _result(wellformed=False, **_meta(table, None, "", 0, started))
    keys = set(arguments)
    if name == "read_file" and {"path"} <= keys <= {"path", "offset", "line", "max_chars"}:
        if (
            ("offset" in arguments and arguments["offset"] is None)
            or ("line" in arguments and arguments["line"] is None)
            or ("offset" in arguments and "line" in arguments)
        ):
            return _result(wellformed=False, **_meta(table, None, "", 0, started))
        result = _read_file_v4(
            root,
            arguments["path"],
            arguments.get("offset"),
            arguments.get("line"),
            arguments.get("max_chars", 8_000),
        )
        result.update(
            _meta(table, arguments["path"], str(arguments["path"]), 0, started)
        )
        return result
    if name == "glob" and keys == {"pattern"}:
        return _glob_v2(root, arguments["pattern"], table, dir_marker=dir_marker)
    if name == "grep" and keys <= {"pattern", "path"} and "pattern" in keys:
        return _grep_v4(root, arguments["pattern"], arguments.get("path", ""), table)
    return _result(wellformed=False, **_meta(table, None, "", 0, started))


def make_executor_v4(table: dict[str, Any], dir_marker: bool = False):
    """Bind v4 to the runner's four-argument executor contract."""

    def executor(
        root: Path, name: str, arguments: str, repair: str = "off"
    ) -> dict[str, Any]:
        return execute_tool_call_v4(
            root,
            name,
            arguments,
            table,
            repair=repair,
            dir_marker=dir_marker,
        )

    return executor

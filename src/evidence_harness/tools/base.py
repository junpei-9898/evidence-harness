"""Read-only tools confined to one working-directory root."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

CONTENT_LIMIT = 8_000
LINE_LIMIT = 2_000
TIME_BUDGET_SECONDS = 10.0
TIME_CHECK_INTERVAL = 200
EXCLUDED_CANDIDATE_DIRECTORIES = {
    ".git",
    ".next",
    ".pnpm",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}


def _result(
    *,
    wellformed: bool = True,
    grounded: bool = False,
    content: str = "",
    time_capped: bool = False,
    **extra: Any,
) -> dict:
    truncated = len(content) > CONTENT_LIMIT
    result = {
        "wellformed": wellformed,
        "grounded": grounded,
        "content": content[:CONTENT_LIMIT],
        "empty": not bool(content),
        "truncated": truncated,
        "time_capped": time_capped,
    }
    result.update(extra)
    return result


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _safe_relative(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    return value


def _candidate_files(root: Path) -> Iterator[Path]:
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in EXCLUDED_CANDIDATE_DIRECTORIES and not name.startswith(".")
        )
        base = Path(directory)
        for file_name in sorted(file_names):
            yield base / file_name


def _read_file(root: Path, path_value: object, repair: str = "off") -> dict:
    started_at = time.monotonic()
    time_capped = False
    relative = _safe_relative(path_value)
    if relative is None or not relative:
        return _result()
    strict = root / relative
    candidates: list[Path]
    resolution = "strict"
    if _inside(root, strict) and strict.is_file():
        candidates = [strict]
    else:
        suffix = Path(relative).as_posix()
        suffix_candidates: list[Path] = []
        basename_candidates: list[Path] = []
        for index, path in enumerate(_candidate_files(root), 1):
            if (
                index % TIME_CHECK_INTERVAL == 0
                and time.monotonic() - started_at >= TIME_BUDGET_SECONDS
            ):
                time_capped = True
                break
            if not _inside(root, path) or not path.is_file():
                continue
            path_relative = path.relative_to(root).as_posix()
            if "/" in suffix and (
                path_relative.endswith("/" + suffix) or suffix.endswith("/" + path_relative)
            ):
                suffix_candidates.append(path)
            if path.name == Path(relative).name:
                basename_candidates.append(path)
        suffix_candidates.sort(key=lambda path: path.relative_to(root).as_posix())
        basename_candidates.sort(key=lambda path: path.relative_to(root).as_posix())
        candidates = suffix_candidates
        resolution = "suffix"
        if not candidates:
            candidates = basename_candidates
            resolution = "basename"
    if not candidates:
        return _result(
            time_capped=time_capped,
            resolution=resolution,
            ambiguous=False,
        )
    chosen = candidates[0]
    try:
        content = chosen.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _result(
            time_capped=time_capped,
            resolution=resolution,
            ambiguous=len(candidates) > 1,
        )
    return _result(
        grounded=True,
        content=content,
        path=chosen.relative_to(root).as_posix(),
        resolution=resolution,
        ambiguous=len(candidates) > 1,
        time_capped=time_capped,
    )


def _glob(root: Path, pattern_value: object, *, dir_marker: bool = False) -> dict:
    started_at = time.monotonic()
    pattern = _safe_relative(pattern_value)
    if pattern is None or not pattern:
        return _result(hits=[])
    hits: list[str] = []
    time_capped = False
    try:
        for index, path in enumerate(root.glob(pattern), 1):
            if (
                index % TIME_CHECK_INTERVAL == 0
                and time.monotonic() - started_at >= TIME_BUDGET_SECONDS
            ):
                time_capped = True
                break
            if _inside(root, path):
                relative = path.relative_to(root).as_posix()
                hits.append(relative + "/" if dir_marker and path.is_dir() else relative)
        hits.sort()
    except (OSError, ValueError):
        hits = []
    content = "\n".join(hits)
    truncated = len(content) > CONTENT_LIMIT
    visible_hits = content[:CONTENT_LIMIT].splitlines()
    disclosure = {"total_hits": len(hits)} if truncated else {}
    return _result(
        grounded=bool(hits),
        content=content,
        hits=visible_hits,
        time_capped=time_capped,
        **disclosure,
    )


def _grep(root: Path, pattern_value: object, path_value: object) -> dict:
    started_at = time.monotonic()
    if not isinstance(pattern_value, str) or not pattern_value:
        return _result()
    relative = _safe_relative(path_value)
    if relative is None:
        return _result()
    scope = root / relative if relative else root
    if not _inside(root, scope) or not scope.exists():
        return _result()
    time_capped = False
    if scope.is_file():
        files = [scope]
    else:
        files = []
        for index, path in enumerate(scope.rglob("*"), 1):
            if (
                index % TIME_CHECK_INTERVAL == 0
                and time.monotonic() - started_at >= TIME_BUDGET_SECONDS
            ):
                time_capped = True
                break
            if _inside(root, path) and path.is_file():
                files.append(path)
        files.sort(key=lambda path: path.relative_to(root).as_posix())
    try:
        matcher_regex = re.compile(pattern_value)
        matches = lambda line: matcher_regex.search(line) is not None  # noqa: E731
        fallback = False
    except re.error:
        matches = lambda line: pattern_value in line  # noqa: E731
        fallback = True
    rows: list[str] = []
    lines_checked = 0
    for file_path in files:
        if not _inside(root, file_path):
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for lineno, line in enumerate(lines, 1):
                if (
                    lines_checked % TIME_CHECK_INTERVAL == 0
                    and time.monotonic() - started_at >= TIME_BUDGET_SECONDS
                ):
                    time_capped = True
                    break
                lines_checked += 1
                line = line[:LINE_LIMIT]
                if matches(line):
                    rows.append(f"{file_path.relative_to(root).as_posix()}:{lineno}:{line}")
        except OSError:
            continue
        if time_capped:
            break
    content = "\n".join(rows)
    truncated = len(content) > CONTENT_LIMIT
    visible_matches = content[:CONTENT_LIMIT].splitlines()
    disclosure = {"total_hits": len(rows)} if truncated else {}
    return _result(
        grounded=bool(rows),
        content=content,
        matches=visible_matches,
        regex_fallback=fallback,
        time_capped=time_capped,
        **disclosure,
    )


def execute_tool_call(
    snapshot_root: Path,
    name: str,
    arguments_json: str,
    repair: str = "off",
    dir_marker: bool = False,
) -> dict:
    """Execute a read-only tool; malformed or escaping inputs do nothing."""
    root = snapshot_root.resolve()
    try:
        arguments = json.loads(arguments_json)
    except (json.JSONDecodeError, TypeError):
        return _result(wellformed=False)
    if not isinstance(arguments, dict):
        return _result(wellformed=False)
    if name == "read_file" and set(arguments) == {"path"}:
        return _read_file(root, arguments["path"], repair)
    if name == "glob" and set(arguments) == {"pattern"}:
        return _glob(root, arguments["pattern"], dir_marker=dir_marker)
    if name == "grep" and set(arguments).issubset({"pattern", "path"}) and "pattern" in arguments:
        return _grep(root, arguments["pattern"], arguments.get("path", ""))
    return _result(wellformed=False)

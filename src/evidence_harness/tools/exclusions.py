"""Exclusion-aware primitives for read-only tools."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .base import CONTENT_LIMIT, TIME_BUDGET_SECONDS, _inside, _result, _safe_relative

EXCLUDED_DIR_CATEGORIES = (
    "node_modules",
    ".pnpm",
    ".venv",
    "venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".next",
    "dist",
    "build",
    "target",
    "artifacts",
    ".DS_Store",
    ".claude/worktrees",
)
_BASENAMES = frozenset(EXCLUDED_DIR_CATEGORIES[:-1])
_FILE_EXCLUSIONS = frozenset({".DS_Store"})


def _walk_files(root: Path, *, prune: bool) -> Iterator[Path]:
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        rel_dir = base.relative_to(root).as_posix()
        if prune:
            names[:] = sorted(
                name
                for name in names
                if name not in _BASENAMES
                and not (rel_dir == ".claude" and name == "worktrees")
            )
        for name in sorted(files):
            if prune and name in _FILE_EXCLUSIONS:
                continue
            yield base / name


def build_exclusion_table(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"snapshot root is not a directory: {root}")
    excluded: list[str] = []
    files_before = sum(1 for _ in _walk_files(root, prune=False))
    files_after = 0
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        keep = []
        for name in sorted(names):
            rel = (base / name).relative_to(root).as_posix()
            if name in _BASENAMES or rel == ".claude/worktrees":
                excluded.append(rel)
            else:
                keep.append(name)
        names[:] = keep
        files_after += sum(1 for name in files if name not in _FILE_EXCLUSIONS)
    excluded.sort()
    categories = list(EXCLUDED_DIR_CATEGORIES)
    digest_input = "\n".join(sorted(excluded + categories)).encode()
    return {
        "root": str(root),
        "categories": categories,
        "excluded_dirs": excluded,
        "files_before": files_before,
        "files_after": files_after,
        "sha256": hashlib.sha256(digest_input).hexdigest(),
    }


def iter_included_files(root: Path, table: dict[str, Any]) -> Iterator[str]:
    root = root.resolve()
    excluded = {str(value).rstrip("/") for value in table.get("excluded_dirs", [])}
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        names[:] = sorted(
            name
            for name in names
            if (base / name).relative_to(root).as_posix() not in excluded
        )
        for name in sorted(files):
            if name in _FILE_EXCLUSIONS:
                continue
            path = base / name
            if _inside(root, path):
                yield path.relative_to(root).as_posix()


def _meta(
    table: dict[str, Any], query: Any, scope: str, scanned: int, started: float
) -> dict[str, Any]:
    return {
        "query": query,
        "scope": scope,
        "exclusion_sha256": table.get("sha256"),
        "scanned_files": scanned,
        "elapsed_s": round(time.monotonic() - started, 6),
    }


def _capped_prefix(scanned: int, total: int) -> str:
    return f"[TIME_CAPPED] search incomplete: scanned {scanned} of {total} files"


def _match_glob(relative: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(relative, pattern):
        return True
    while pattern.startswith("**/"):
        pattern = pattern[3:]
        if fnmatch.fnmatchcase(relative, pattern):
            return True
    return False


def _glob_v2(
    root: Path,
    pattern: object,
    table: dict[str, Any],
    *,
    dir_marker: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    safe = _safe_relative(pattern)
    base_meta = _meta(table, pattern, "", 0, started)
    if safe is None or not safe:
        return _result(wellformed=False, hits=[], **base_meta)
    hits: list[str] = []
    scanned = 0
    capped = False
    for relative in iter_included_files(root, table):
        if time.monotonic() - started >= TIME_BUDGET_SECONDS:
            capped = True
            break
        scanned += 1
        if _match_glob(relative, safe):
            hits.append(relative + ("/" if dir_marker and (root / relative).is_dir() else ""))
    hits.sort()
    rows = ([_capped_prefix(scanned, int(table.get("files_after", 0)))] if capped else []) + hits
    content = "\n".join(rows)
    visible = content[:CONTENT_LIMIT].splitlines()
    result = _result(
        grounded=bool(hits),
        content=content,
        time_capped=capped,
        hits=[row for row in visible if not row.startswith("[TIME_CAPPED]")],
        **_meta(table, safe, "", scanned, started),
    )
    result["empty"] = not capped and not hits
    if len(content) > CONTENT_LIMIT:
        result["total_hits"] = len(hits)
    return result

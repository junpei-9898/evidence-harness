"""Deterministic exploration ledger built only from tool observations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any


def _normalized_path(relpath: str) -> str:
    value = relpath.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return PurePosixPath(value).as_posix()


def types_for_scope(manifest: dict[str, Any], path: str) -> set[str]:
    """Return document types for an exact file or a directory prefix."""
    files = manifest.get("files")
    if not isinstance(files, dict) or not isinstance(path, str) or not path.strip():
        return set()
    normalized = _normalized_path(path).rstrip("/")
    if normalized == ".":
        return {value for value in files.values() if isinstance(value, str)}
    if normalized in files and isinstance(files[normalized], str):
        return {files[normalized]}
    prefix = normalized + "/"
    return {
        value for key, value in files.items()
        if isinstance(key, str) and isinstance(value, str) and key.startswith(prefix)
    }


def normalized_request_key(name: str, arguments_json: str) -> str:
    """Canonicalize a tool request without changing string values."""
    try:
        arguments = json.loads(arguments_json)
    except (json.JSONDecodeError, TypeError):
        normalized = re.sub(r"\s+", " ", str(arguments_json)).strip()
        return f"{name}:<malformed:{normalized}>"
    canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{name}:{canonical}"


def _arguments(execution: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(execution.get("arguments", ""))
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _match_parts(row: str) -> tuple[str, int, str] | None:
    parts = row.split(":", 2)
    if len(parts) != 3:
        return None
    try:
        line = int(parts[1])
    except ValueError:
        return None
    return parts[0].removeprefix("./"), line, parts[2]


def active_refs(round_record: dict[str, Any], manifest: dict[str, Any]) -> set[str]:
    """Return types actively referenced by reads and path-scoped grep calls."""
    active: set[str] = set()
    for execution in round_record.get("executions", []):
        if not isinstance(execution, dict):
            continue
        name, arguments = execution.get("name"), _arguments(execution)
        path = arguments.get("path")
        if name == "read_file" and isinstance(path, str):
            active.update(types_for_scope(manifest, path))
        elif name == "grep" and isinstance(path, str) and path:
            active.update(types_for_scope(manifest, path))
    return active


@dataclass
class Ledger:
    """Materialized observation ledger; construction order is stable."""

    rounds: list[dict[str, Any]]
    manifest: dict[str, Any]
    requests: list[dict[str, Any]] = field(init=False, default_factory=list)
    surfaced_paths: list[dict[str, Any]] = field(init=False, default_factory=list)
    fetched_spans: list[dict[str, Any]] = field(init=False, default_factory=list)
    raw_texts: list[dict[str, Any]] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self._build()

    @classmethod
    def from_rounds(cls, rounds: list[dict[str, Any]], manifest: dict[str, Any]) -> Ledger:
        return cls(rounds, manifest)

    def _build(self) -> None:
        surfaced: dict[str, dict[str, Any]] = {}
        for round_record in self.rounds:
            round_number = int(round_record.get("round", 0))
            for index, execution in enumerate(round_record.get("executions", [])):
                if not isinstance(execution, dict):
                    continue
                request_id = str(execution.get("tool_call_id") or f"r{round_number}-{index}")
                name = str(execution.get("name", ""))
                arguments_json = execution.get("arguments", "")
                result = (
                    execution.get("result")
                    if isinstance(execution.get("result"), dict)
                    else {}
                )
                status = "エラー" if not result.get("wellformed", True) else (
                    "空" if result.get("empty") else "成功"
                )
                self.requests.append({
                    "request_id": request_id, "round": round_number, "tool": name,
                    "arguments": normalized_request_key(name, str(arguments_json)).split(":", 1)[1],
                    "normalized_arguments": normalized_request_key(
                        name, str(arguments_json)
                    ).split(":", 1)[1],
                    "request_key": normalized_request_key(name, str(arguments_json)),
                    "result": status, "cap": bool(result.get("time_capped")),
                    "truncated": bool(result.get("truncated")),
                })
                args = _arguments(execution)
                active_path = args.get("path") if name in {"read_file", "grep"} else None
                if name == "glob":
                    hits = result.get("hits", []) if isinstance(result.get("hits"), list) else []
                    for path in hits:
                        if isinstance(path, str):
                            self._surface(surfaced, path.rstrip("/"), round_number, False)
                if name == "grep":
                    structured = result.get("rows")
                    rows = structured if (
                        isinstance(structured, list)
                        and all(isinstance(row, dict) for row in structured)
                    ) else None
                    matches = (
                        result.get("matches")
                        if isinstance(result.get("matches"), list)
                        else []
                    )
                    source_rows = rows if rows is not None else matches
                    for row in source_rows:
                        if rows is not None:
                            try:
                                parsed = (
                                    str(row["path"]).removeprefix("./"), int(row["line"]),
                                    int(row["char_offset"]), str(row["text"]),
                                )
                            except (KeyError, TypeError, ValueError):
                                parsed = None
                        else:
                            legacy = _match_parts(row) if isinstance(row, str) else None
                            parsed = None if legacy is None else (
                                legacy[0], legacy[1], legacy[1], legacy[2],
                            )
                        if parsed is None:
                            continue
                        path, line, start, text = parsed
                        self._surface(surfaced, path, round_number, bool(active_path))
                        if active_path:
                            self.fetched_spans.append({
                                "request_id": request_id, "round": round_number, "path": path,
                                "tool": "grep", "start": start,
                                "end": start + len(text) if rows is not None else start,
                                "next_offset": None, "line": line,
                            })
                        self.raw_texts.append({
                            "request_id": request_id, "round": round_number, "path": path,
                            "doctype": self._doctype(path), "tool": "grep", "start": start,
                            "end": start + len(text) if rows is not None else start,
                            **({"line": line} if rows is not None else {}), "text": text,
                        })
                if name == "read_file" and result.get("grounded"):
                    path = str(result.get("path") or active_path or "").removeprefix("./")
                    content = (
                        result.get("content")
                        if isinstance(result.get("content"), str)
                        else ""
                    )
                    start = int(result.get("start", args.get("offset", 0)) or 0)
                    end = int(result.get("end", start + len(content)) or start)
                    self.fetched_spans.append({
                        "request_id": request_id, "round": round_number, "path": path,
                        "tool": "read_file", "start": start, "end": end,
                        "next_offset": result.get("next_offset"),
                    })
                    for block_start in range(0, len(content), 512):
                        text = content[block_start:block_start + 512]
                        self.raw_texts.append({
                            "request_id": request_id, "round": round_number, "path": path,
                            "doctype": self._doctype(path), "tool": "read_file",
                            "start": start + block_start,
                            "end": start + block_start + len(text), "text": text,
                        })
        self.surfaced_paths = list(surfaced.values())

    def _doctype(self, path: str) -> str:
        value = self.manifest.get("files", {}).get(path)
        return str(value) if isinstance(value, str) else "その他"

    def _surface(
        self, surfaced: dict[str, dict[str, Any]], path: str, round_number: int,
        active: bool,
    ) -> None:
        normalized = path.removeprefix("./")
        if normalized not in surfaced:
            surfaced[normalized] = {
                "path": normalized, "doctype": self._doctype(normalized),
                "first_round": round_number, "active": active,
                "active_reference": active,
            }
        elif active:
            surfaced[normalized]["active"] = True
            surfaced[normalized]["active_reference"] = True


def is_continuation_read(execution: dict[str, Any], ledger: Ledger) -> bool:
    """A read continues when it asks a previously read path at another offset."""
    if execution.get("name") != "read_file":
        return False
    arguments = _arguments(execution)
    path = arguments.get("path")
    has_offset = "offset" in arguments
    has_line = "line" in arguments and not has_offset
    offset = arguments.get("offset", 0)
    if not isinstance(path, str):
        return False
    if has_offset and (not isinstance(offset, int) or isinstance(offset, bool)):
        return False
    normalized = path.removeprefix("./")
    prior_starts = {
        span["start"] for span in ledger.fetched_spans
        if span.get("tool") == "read_file" and span.get("path") == normalized
    }
    if not prior_starts:
        return False
    result = execution.get("result") if isinstance(execution.get("result"), dict) else {}
    requested_start = result.get("start") if has_line else offset
    if has_line and not isinstance(requested_start, int):
        return True
    return isinstance(requested_start, int) and requested_start not in prior_starts

"""Gold-independent citation format and verbatim-evidence gate."""

from __future__ import annotations

import re
from typing import Any

from ..loop.ledger import Ledger

ANSWER_FORMAT = (
    "最終回答は本文の後に必ず次の 2 行を含める。\n"
    "出典: <snapshot 相対パス>\n"
    "引用: <そのファイルから取得した原文の逐語（20〜200 字）>\n"
    "取得していないファイルを出典にしない。取得した証拠で確認できない場合は本文に"
    "『取得した証拠では確認できない』と書き、出典行と引用行は書かない。"
)
ABSTAIN_TEXT = "取得した証拠では確認できない"
GATE_FAILURE = "取得した証拠では確認できないため、回答を確定できません。"


def _normalize_space(value: str) -> str:
    """Whitespace-insensitive comparison key (orch A-type fix 2026-09-11).

    The answer's 引用 line is single-line, so a multi-line source quote is rendered
    with literal escapes (\\n, \\t); those and every whitespace character are
    removed before comparison. Markdown markers and other characters are kept.
    """
    value = value.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")
    return "".join(value.split())


def _normalize_path(value: str) -> str:
    while value.startswith("./"):
        value = value[2:]
    return value


def parse_answer(content: str | None) -> dict[str, Any]:
    """Parse only a trailing citation pair; do not infer a source from prose."""
    text = content if isinstance(content, str) else ""
    match = re.search(r"(?:^|\n)出典:\s*([^\n]+?)\s*\n引用:\s*(.+?)\s*$", text, re.DOTALL)
    if match is None:
        has_source_line = re.search(r"(?:^|\n)出典:\s*", text) is not None
        return {
            "body": text.strip(), "source_path": None, "quote": None,
            "abstain": not has_source_line and ABSTAIN_TEXT in text,
        }
    body = text[:match.start()].strip()
    source = _normalize_path(match.group(1).strip())
    quote = match.group(2).strip()
    return {
        "body": body, "source_path": source or None, "quote": quote or None,
        "abstain": False,
    }


def returned_evidence(ledger: Ledger) -> dict[str, dict[str, Any]]:
    """Reconstruct fetched read characters and grep lines by exact path."""
    output: dict[str, dict[str, Any]] = {}
    read_cells: dict[str, dict[int, str]] = {}
    grep_lines: dict[str, list[str]] = {}
    for raw in ledger.raw_texts:
        path = _normalize_path(str(raw.get("path", "")))
        if not path:
            continue
        if raw.get("tool") == "read_file":
            start, text = int(raw.get("start", 0)), str(raw.get("text", ""))
            cells = read_cells.setdefault(path, {})
            for index, character in enumerate(text, start):
                cells[index] = character
        elif raw.get("tool") == "grep":
            grep_lines.setdefault(path, []).append(str(raw.get("text", "")))
    for path in set(read_cells) | set(grep_lines):
        cells = read_cells.get(path, {})
        runs: list[str] = []
        current: list[str] = []
        prior: int | None = None
        for position in sorted(cells):
            if prior is not None and position != prior + 1:
                runs.append("".join(current))
                current = []
            current.append(cells[position])
            prior = position
        if current:
            runs.append("".join(current))
        output[path] = {"read_runs": runs, "grep_lines": grep_lines.get(path, [])}
    return output


def quote_is_returned(path: str, quote: str, ledger: Ledger) -> bool:
    evidence = returned_evidence(ledger).get(_normalize_path(path))
    if evidence is None:
        return False
    needle = _normalize_space(quote)
    values = list(evidence["read_runs"]) + list(evidence["grep_lines"])
    return bool(needle) and any(needle in _normalize_space(value) for value in values)


def apply_gate(content: str | None, ledger: Ledger) -> dict[str, Any]:
    """Require an exact fetched path and a verbatim whitespace-normalized quote."""
    parsed = parse_answer(content)
    if parsed["abstain"]:
        return {
            "passed": True, "abstain": True, "reason": "abstain",
            "gated_content": content or "", **parsed,
        }
    source, quote = parsed["source_path"], parsed["quote"]
    if source is None:
        reason = "missing_source"
    elif quote is None:
        reason = "missing_quote"
    elif source not in returned_evidence(ledger):
        reason = "source_not_fetched"
    elif not quote_is_returned(source, quote, ledger):
        reason = "quote_not_verbatim"
    else:
        return {
            "passed": True, "abstain": False, "reason": "passed",
            "quote_length_ok": 20 <= len(quote) <= 200,
            "gated_content": content or "", **parsed,
        }
    return {
        "passed": False, "abstain": False, "reason": reason,
        "quote_length_ok": bool(quote) and 20 <= len(quote) <= 200,
        "gated_content": GATE_FAILURE, **parsed,
    }

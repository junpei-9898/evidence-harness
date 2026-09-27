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
GATE_CONTRACT_V1 = "v1"                 # whitespace-normalized verbatim only
GATE_CONTRACT_V2 = "v2.0-unwrap1"       # + one symmetric outer wrapper layer
GATE_CONTRACT_DEFAULT = GATE_CONTRACT_V1
# v2.0: only wrappers whose recovery was validated upstream (backtick, double quote).
# Fences, triple backticks, other quotes/brackets, JSON string decoding, grep multi-line
# joins are NOT unwrapped in this version (each would be a separate transform id).
UNWRAP_PAIRS_V2 = (("`", "`", "backtick"), ('"', '"', "dquote"))
GATE_FAILURE = "取得した証拠では確認できないため、回答を確定できません。"

_CONTRACT_ALIASES = {"v1": GATE_CONTRACT_V1, "v2": GATE_CONTRACT_V2}


def normalize_citation_contract(value: str) -> str:
    """Resolve a caller-facing short alias ("v1"/"v2") to the byte-identical contract id.

    Anything already fully-qualified (e.g. "v2.0-unwrap1") or unrecognized passes through
    unchanged; only the two public short names are rewritten.
    """
    return _CONTRACT_ALIASES.get(value, value)


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


def unwrap_outer_once(quote: str) -> list[tuple[str, str]]:
    """Return [(form, candidate)]: the raw quote first, then at most one layer removed.

    Only single backtick and double quote pairs (v2.0). The inner text must be non-empty
    after stripping outer whitespace; asymmetric wrappers produce no candidate; the layer
    is removed once.
    """
    out = [("raw", quote)]
    stripped = quote.strip()
    for left, right, form in UNWRAP_PAIRS_V2:
        wrapped = stripped.startswith(left) and stripped.endswith(right)
        if len(stripped) > len(left) + len(right) and wrapped:
            inner = stripped[len(left):len(stripped) - len(right)].strip()
            if inner:
                out.append((f"unwrapped_{form}", inner))
    return out


def _quote_match_form(path: str, quote: str, ledger: Ledger, contract: str) -> str | None:
    evidence = returned_evidence(ledger).get(_normalize_path(path))
    if evidence is None:
        return None
    runs = list(evidence["read_runs"]) + list(evidence["grep_lines"])
    values = [_normalize_space(v) for v in runs]
    candidates = unwrap_outer_once(quote) if contract == GATE_CONTRACT_V2 else [("raw", quote)]
    for form, candidate in candidates:
        needle = _normalize_space(candidate)
        if needle and any(needle in value for value in values):
            return form
    return None


def quote_is_returned(
    path: str, quote: str, ledger: Ledger, contract: str = GATE_CONTRACT_V1
) -> bool:
    return _quote_match_form(path, quote, ledger, contract) is not None


def apply_gate(
    content: str | None, ledger: Ledger, contract: str = GATE_CONTRACT_V1
) -> dict[str, Any]:
    """Require an exact fetched path and a verbatim whitespace-normalized quote.

    contract v1: the 引用 line as written. contract v2.0-unwrap1: if the raw line does not match,
    retry once with one symmetric outer backtick / double-quote layer removed. Body, source path and
    the quote text as shipped are never modified; only the acceptance test widens.
    """
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
    elif (form := _quote_match_form(source, quote, ledger, contract)) is None:
        reason = "quote_not_verbatim"
    else:
        matched = quote if form == "raw" else dict(unwrap_outer_once(quote))[form]
        return {
            "passed": True, "abstain": False, "reason": "passed",
            "quote_length_ok": 20 <= len(quote) <= 200,
            "quote_length_ok_matched": 20 <= len(matched) <= 200,
            "quote_match_form": form, "gate_contract": contract,
            "gated_content": content or "", **parsed,
        }
    return {
        "passed": False, "abstain": False, "reason": reason,
        "quote_length_ok": bool(quote) and 20 <= len(quote) <= 200,
        "quote_match_form": None, "gate_contract": contract,
        "gated_content": GATE_FAILURE, **parsed,
    }

"""Byte-frozen deterministic completion rules for numeric lookup answers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

RULES_VERSION = "deterministic-completion-1.0"
RESEARCH_RULE_SHA256 = "e65a65a44c1120b50cb2e1f1e23b69396a80635a517d11e511b945cd72e163d3"

_KEY = re.compile(r"^\s*([A-Za-z_][\w.-]*)\s*[=:]")
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_VALUE_SPLIT = re.compile(r"[\s=:,;()\[\]\"'<>]+")
_TYPE_SPLIT = re.compile(r"[,/;、\s]+")
_DIGITS = re.compile(r"\d+")
_EDGE_PUNCTUATION = ".,;:!?"


def _normalized(value: str) -> str:
    return value.casefold().strip()


def _add_path(tokens: set[str], value: Any) -> None:
    if not isinstance(value, str):
        return
    path = PurePosixPath(value)
    tokens.update((_normalized(path.name), _normalized(path.stem)))


def identifier_tokens(
    rounds: Sequence[Mapping[str, Any]], pack_paths: Sequence[str] = ()
) -> frozenset[str]:
    """Extract exact normalized identifiers from paths and read-file contents."""
    tokens: set[str] = set()
    for pack_path in pack_paths:
        _add_path(tokens, pack_path)
    for round_record in rounds:
        if not isinstance(round_record, Mapping):
            continue
        for execution in round_record.get("executions") or []:
            if not isinstance(execution, Mapping):
                continue
            name = execution.get("name")
            if name == "read_file":
                arguments = execution.get("arguments")
                if isinstance(arguments, str):
                    try:
                        parsed = json.loads(arguments)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, Mapping):
                        _add_path(tokens, parsed.get("path"))
                result = execution.get("result")
                content = result.get("content") if isinstance(result, Mapping) else None
                if isinstance(content, str):
                    for line in content.splitlines():
                        key_match = _KEY.match(line)
                        if key_match is not None:
                            tokens.add(_normalized(key_match.group(1)))
                        heading_match = _MARKDOWN_HEADING.match(line)
                        if heading_match is not None:
                            tokens.add(_normalized(heading_match.group(1)))
    return frozenset(token for token in tokens if token)


def extract_value(answer: str) -> tuple[str | None, str]:
    """Apply R-A and return a unique pure-digit value when one exists."""
    if _DIGITS.fullmatch(answer) is not None:
        return answer, "bare_digits"
    candidates = [
        stripped
        for token in _VALUE_SPLIT.split(answer)
        if (stripped := token.strip(_EDGE_PUNCTUATION))
        and _DIGITS.fullmatch(stripped) is not None
    ]
    if len(candidates) == 1:
        return candidates[0], "unique_digit_token"
    if not candidates:
        return None, "no_digit_token"
    return None, "ambiguous_digit_tokens"


def type_check(answer: str, identifiers: frozenset[str]) -> tuple[bool, str]:
    """Apply R-B to an answer using exact, case-folded identifier tokens."""
    tokens = [token.casefold().strip() for token in _TYPE_SPLIT.split(answer) if token.strip()]
    if not tokens:
        return False, "empty"
    normalized_identifiers = frozenset(token.casefold().strip() for token in identifiers)
    if all(token in normalized_identifiers for token in tokens):
        return True, "all_tokens_identifiers"
    return False, "has_non_identifier_token"


def complete(
    answer: Any,
    rounds: Sequence[Mapping[str, Any]],
    pack_paths: Sequence[str],
) -> dict[str, Any]:
    """Apply R-A before R-B without consulting a gold answer."""
    answer_text = answer if isinstance(answer, str) else ""
    value, extract_reason = extract_value(answer_text)
    if value is not None:
        return {
            "answer": value,
            "answer_raw": answer,
            "extracted": extract_reason == "unique_digit_token",
            "extract_reason": extract_reason,
            "nonlanded_by_type_check": False,
            "type_reason": "skipped_value",
        }
    identifiers = identifier_tokens(rounds, pack_paths)
    nonlanded, type_reason = type_check(answer_text, identifiers)
    return {
        "answer": None,
        "answer_raw": answer,
        "extracted": False,
        "extract_reason": extract_reason,
        "nonlanded_by_type_check": nonlanded,
        "type_reason": type_reason,
    }


def rule_sha256() -> str:
    """Return the digest of this exact frozen rule module."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

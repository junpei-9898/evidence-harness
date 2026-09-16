"""Pure stall judgments over completed exploration rounds."""

from __future__ import annotations

from collections import Counter
from typing import Any

from evidence_harness.loop.ledger import (
    Ledger,
    active_refs,
    is_continuation_read,
    normalized_request_key,
)


def stall_check(
    rounds: list[dict[str, Any]],
    manifest: dict[str, Any],
    *,
    at_round: int,
) -> dict[str, Any]:
    """Evaluate the preregistered OR conditions after round two or three."""
    if at_round not in {2, 3}:
        raise ValueError("at_round must be 2 or 3")
    observed = [row for row in rounds if int(row.get("round", 0)) <= at_round]
    seen: Counter[str] = Counter()
    duplicate_keys: list[str] = []
    continuation_ids: set[str] = set()
    prefix_rounds: list[dict[str, Any]] = []
    for record in observed:
        current = {
            "round": record.get("round"),
            "message": record.get("message", {}),
            "executions": [],
        }
        for execution in record.get("executions", []):
            before = Ledger(prefix_rounds + [current], manifest)
            if is_continuation_read(execution, before):
                continuation_ids.add(str(execution.get("tool_call_id", "")))
            else:
                key = normalized_request_key(
                    str(execution.get("name", "")), str(execution.get("arguments", ""))
                )
                if seen[key]:
                    duplicate_keys.append(key)
                seen[key] += 1
            current["executions"].append(execution)
        prefix_rounds.append(record)
    recent = observed[-2:]
    per_round = []
    previous_paths: set[str] = set()
    previous_spans: set[tuple[Any, ...]] = set()
    for record in observed:
        partial = Ledger([record], manifest)
        paths = {item["path"] for item in partial.surfaced_paths}
        spans = {
            (item.get("path"), item.get("tool"), item.get("start"), item.get("end"))
            for item in partial.fetched_spans
        }
        new_paths = paths - previous_paths
        if record in recent:
            filtered = {
                **record,
                "executions": [
                    execution
                    for execution in record.get("executions", [])
                    if str(execution.get("tool_call_id", "")) not in continuation_ids
                ],
            }
            refs = active_refs(filtered, manifest)
            per_round.append(
                {
                    "round": record.get("round"),
                    "new_paths": sorted(new_paths),
                    "new_spans": sorted(spans - previous_spans),
                    "active_refs": sorted(refs),
                }
            )
        previous_paths.update(paths)
        previous_spans.update(spans)
    no_progress = len(recent) == 2 and all(
        not row["new_paths"] and not row["new_spans"] for row in per_round
    )
    reference_sets = [set(row["active_refs"]) for row in per_round]
    one_type = (
        len(reference_sets) == 2
        and all(reference_sets)
        and len(set().union(*reference_sets)) == 1
    )
    reasons = []
    if duplicate_keys:
        reasons.append("duplicate_request")
    if no_progress:
        reasons.append("no_new_path_or_span")
    if one_type:
        reasons.append("single_document_type")
    return {
        "fired": bool(reasons),
        "reasons": reasons,
        "detail": {"duplicate_keys": duplicate_keys, "rounds": per_round},
    }

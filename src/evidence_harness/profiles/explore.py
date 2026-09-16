"""Explore-v4 loop with observational stall checks and a citation gate."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from evidence_harness.gates.citation import ANSWER_FORMAT, apply_gate
from evidence_harness.instruments.monitors import (
    has_pseudo_tool_syntax,
    measure,
    summarize_explore,
)
from evidence_harness.instruments.stall import stall_check
from evidence_harness.instruments.usage import UsageRecorder, retrying
from evidence_harness.loop.ledger import Ledger
from evidence_harness.loop.messages import _append_exchange, _execute
from evidence_harness.tools.exclusions import build_exclusion_table, iter_included_files
from evidence_harness.tools.schema import TOOLS_V4
from evidence_harness.tools.v4 import make_executor_v4
from evidence_harness.transport import Transport, _response_parts, http_transport

SYSTEM = (
    "あなたはソフトウェア作業アシスタントです。作業ディレクトリは依頼発生元"
    "プロジェクトの読み取り専用スナップショットです。事実はツールで確認してから答えること。"
    "書き込み・実行はできません。"
)


def _content_hash(content: str | None) -> str | None:
    if content is None:
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _observability(
    response: dict[str, Any], message: dict[str, Any], finish_reason: str | None
) -> dict[str, Any]:
    reasoning = message.get("reasoning")
    if not isinstance(reasoning, str):
        reasoning = message.get("reasoning_content")
    if not isinstance(reasoning, str):
        reasoning = None
    raw_usage = response.get("usage")
    return {
        "finish_reason": finish_reason,
        "usage": dict(raw_usage) if isinstance(raw_usage, dict) else None,
        "reasoning": reasoning,
    }


def _manifest(workdir: Path, table: dict[str, Any]) -> dict[str, Any]:
    return {"files": {path: "その他" for path in iter_included_files(workdir, table)}}


def run_explore(
    question: str,
    workdir: Path | str,
    *,
    model: str,
    base_url: str,
    transport: Transport = http_transport,
    max_rounds: int = 6,
    max_tokens: int = 16_384,
    timeout: float = 900,
) -> dict[str, Any]:
    """Run the frozen V4 exploration profile against a read-only work directory."""
    if max_rounds != 6:
        raise ValueError("explore-v4 max_rounds is fixed at 6")

    root = Path(workdir).resolve()
    table = build_exclusion_table(root)
    manifest = _manifest(root, table)
    executor = make_executor_v4(table)
    system = SYSTEM + "\n" + ANSWER_FORMAT
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    rounds: list[dict[str, Any]] = []
    stall_judgments: list[dict[str, Any]] = []
    response_model: str | None = None
    started = time.monotonic()
    recorder = UsageRecorder()
    recorder.start()
    request = retrying(recorder.wrap(transport), retries=1, backoff=0)

    for round_number in range(1, max_rounds + 1):
        payload = {
            "model": model,
            "messages": messages,
            "tools": TOOLS_V4,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        response = request(base_url.rstrip("/") + "/chat/completions", {}, payload, timeout)
        message, finish_reason = _response_parts(response)
        if isinstance(response.get("model"), str):
            response_model = response["model"]
        executions: list[dict[str, Any]] = []
        record = {
            "round": round_number,
            "message": message,
            "executions": executions,
            **_observability(response, message, finish_reason),
        }
        rounds.append(record)
        calls = message.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            break
        executions.extend(_execute(message, root, round_number, executor))
        _append_exchange(messages, message, executions)
        if round_number in {2, 3}:
            judgment = stall_check(rounds, manifest, at_round=round_number)
            stall_judgments.append({"round": round_number, **judgment})

    last = rounds[-1]["message"] if rounds else {}
    pregate = last.get("content") if isinstance(last.get("content"), str) else None
    gate = apply_gate(pregate, Ledger(rounds, manifest))
    final_content = gate["gated_content"]
    calls = recorder.drain()
    monitors = summarize_explore(rounds, gate, max_rounds=max_rounds)
    return {
        "ok": True,
        "repair": "off",
        "rounds": rounds,
        "max_rounds": max_rounds,
        "final_content_pregate": pregate,
        "final_content": final_content,
        "response_hash": _content_hash(final_content),
        "thinking_pseudo": sum(has_pseudo_tool_syntax(row.get("reasoning")) for row in rounds),
        "no_final_answer": not bool(pregate and pregate.strip()),
        "model": response_model,
        "elapsed_s": round(time.monotonic() - started, 6),
        "stall_judgments": stall_judgments,
        "reset_enabled": False,
        "reset_fired": False,
        "reset_round": None,
        "reset_reasons": [],
        "gate": gate,
        "transport_calls": calls,
        **measure(rounds, final_content),
        **monitors,
    }

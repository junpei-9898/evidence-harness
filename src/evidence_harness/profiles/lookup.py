"""Lookup Pc profile with B3 draft landing and history-free finalization."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from evidence_harness.gates.draft import apply_b3
from evidence_harness.gates.finalize import _gate_payloads, finalizer_request, gate_final
from evidence_harness.gates.grounding import final_answer
from evidence_harness.instruments.usage import UsageRecorder, summarize_calls
from evidence_harness.loop.messages import _append_exchange, _execute
from evidence_harness.tools.base import execute_tool_call
from evidence_harness.tools.schema import TOOLS_BASE
from evidence_harness.transport import Transport, _response_parts, http_transport

SYSTEM = (
    "You are investigating a frozen read-only project snapshot. Use read_file, glob, and grep "
    "to establish every required fact. When ready, answer using exactly one JSON object with "
    "string fields answer and nonce."
)
DEFAULT_SAMPLING: dict[str, Any] = {"temperature": 0.7}


def _sampling(sampling: Mapping[str, Any] | None) -> dict[str, Any]:
    chosen = dict(DEFAULT_SAMPLING if sampling is None else sampling)
    if not isinstance(chosen.get("temperature"), (int, float)):
        raise ValueError("sampling must define a numeric temperature")
    return chosen


def _chat_payload(
    model: str,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
    sampling: Mapping[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": copy.deepcopy(list(messages)),
        "tools": copy.deepcopy(list(tools)),
        **dict(sampling),
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": True},
    }


def _model_round(
    state: Mapping[str, Any],
    root: Path,
    messages: list[dict[str, Any]],
    round_number: int,
    *,
    transport: Transport,
    endpoint: str,
    model: str,
    timeout: float,
    max_tokens: int,
    sampling: Mapping[str, Any],
) -> dict[str, Any]:
    response = transport(
        endpoint,
        {},
        _chat_payload(model, messages, state["tools"], sampling, max_tokens),
        timeout,
    )
    message, finish = _response_parts(response)

    def execute(snapshot: Path, name: str, arguments: str, repair: str) -> dict[str, Any]:
        return execute_tool_call(snapshot, name, arguments, repair, dir_marker=True)

    executions = _execute(message, root, round_number, execute)
    record = {
        "round": round_number,
        "message": copy.deepcopy(message),
        "finish_reason": finish,
        "executions": executions,
        "harness_action": False,
    }
    _append_exchange(messages, message, executions)
    return record


def _base_result(sampling: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "landing_source": None,
        "b3_reason": None,
        "harness_rejected": False,
        "reject_reason": None,
        "extra_calls": 0,
        "model_calls": 0,
        "answer": None,
        "nonce": None,
        "rounds": [],
        "usage": {},
        "sampling": dict(sampling),
        "error": None,
    }


def _finish(
    result: dict[str, Any],
    answer: Mapping[str, str] | None,
    recorder: UsageRecorder,
) -> dict[str, Any]:
    if answer is not None:
        result["answer"] = answer["answer"]
        result["nonce"] = answer["nonce"]
    result["usage"] = summarize_calls(recorder.drain())
    return result


def run_lookup(
    question: str,
    workdir: Path | str,
    *,
    model: str,
    base_url: str,
    transport: Transport = http_transport,
    max_rounds: int = 6,
    max_tokens: int = 4096,
    sampling: Mapping[str, Any] | None = DEFAULT_SAMPLING,
    timeout: float = 600,
) -> dict[str, Any]:
    """Run the frozen Pc lookup pipeline directly against ``workdir``."""
    chosen = _sampling(sampling)
    result = _base_result(chosen)
    state = {
        "prefix_messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
        "tools": TOOLS_BASE,
        "trace_rounds": [],
        "boundary_round": 0,
    }
    root = Path(workdir).resolve()
    messages = copy.deepcopy(state["prefix_messages"])
    recorder = UsageRecorder()
    recorder.start()
    request = recorder.wrap(transport)
    endpoint = base_url.rstrip("/") + "/chat/completions"
    attempted: dict[str, str] | None = None
    answer: dict[str, str] | None = None
    try:
        for round_number in range(1, max_rounds + 1):
            record = _model_round(
                state,
                root,
                messages,
                round_number,
                transport=request,
                endpoint=endpoint,
                model=model,
                timeout=timeout,
                max_tokens=max_tokens,
                sampling=chosen,
            )
            result["rounds"].append(record)
            result["model_calls"] += 1
            if record["executions"]:
                continue
            answer = final_answer(record["message"])
            if answer is not None:
                result["landing_source"] = "native"
            break

        if answer is None:
            source = {"rounds": result["rounds"]}
            b3 = apply_b3(source)
            result["b3_reason"] = str(b3.get("b3_reason"))
            if b3.get("b3_landed"):
                attempted = {"answer": str(b3["b3_answer"]), "nonce": str(b3["b3_nonce"])}
                accepted, reason = gate_final(attempted, _gate_payloads(state, source["rounds"]))
                if accepted:
                    answer, result["landing_source"] = attempted, "b3"
                else:
                    result["harness_rejected"], result["reject_reason"] = True, reason

        if answer is None:
            evidence_rounds = list(result["rounds"])
            payload = finalizer_request(state, evidence_rounds, model, chosen, max_tokens)
            response = request(endpoint, {}, payload, timeout)
            message, finish = _response_parts(response)
            result["rounds"].append(
                {
                    "round": max_rounds + 1,
                    "message": copy.deepcopy(message),
                    "executions": [],
                    "finish_reason": finish,
                    "harness_action": True,
                    "fresh_finalizer": True,
                    "seventh_call_rescue": True,
                }
            )
            result["extra_calls"] += 1
            result["model_calls"] += 1
            attempted = final_answer(message)
            accepted, reason = gate_final(attempted, _gate_payloads(state, evidence_rounds))
            if accepted:
                answer, result["landing_source"] = attempted, "finalizer"
            else:
                result["harness_rejected"], result["reject_reason"] = True, reason

        return _finish(result, answer, recorder)
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        return _finish(result, None, recorder)

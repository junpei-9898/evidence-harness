"""Lookup C profile with early grounding repair and identity-strict gating."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evidence_harness.gates.draft import apply_b3
from evidence_harness.gates.finalize import _gate_payloads, finalizer_request
from evidence_harness.gates.grounding import final_answer, is_grounded
from evidence_harness.gates.identity import strict_gate
from evidence_harness.instruments.usage import UsageRecorder
from evidence_harness.loop.messages import _append_exchange
from evidence_harness.tools.base import execute_tool_call
from evidence_harness.tools.schema import TOOLS_BASE
from evidence_harness.transport import Transport, _response_parts, http_transport

from .lookup import DEFAULT_SAMPLING, SYSTEM, _base_result, _finish, _model_round, _sampling


def _read_paths(rounds: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for record in rounds:
        for execution in record.get("executions") or []:
            if not isinstance(execution, Mapping) or execution.get("name") != "read_file":
                continue
            result = execution.get("result")
            path = result.get("path") if isinstance(result, Mapping) else None
            if isinstance(path, str):
                paths.add(path)
    return paths


def _synthetic_call(
    root: Path,
    *,
    name: str,
    arguments: Mapping[str, Any],
    call_id: str,
    round_number: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    encoded = json.dumps(dict(arguments), ensure_ascii=False)
    message = {
        "role": "assistant",
        "content": None,
        "harness_action": True,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": encoded},
            }
        ],
    }
    result = execute_tool_call(root, name, encoded, "off", dir_marker=True)
    execution = {
        "tool_call_id": call_id,
        "name": name,
        "arguments": encoded,
        "result": result,
        "harness_action": True,
    }
    record = {
        "round": round_number,
        "message": message,
        "finish_reason": "tool_calls",
        "executions": [execution],
        "harness_action": True,
    }
    return record, execution


def _retrieve(
    root: Path,
    messages: list[dict[str, Any]],
    rounds: list[dict[str, Any]],
    *,
    sample: int,
    model_calls: int,
    round_number: int,
) -> list[dict[str, Any]]:
    already_read = _read_paths(rounds)
    grep_record, grep_execution = _synthetic_call(
        root,
        name="grep",
        arguments={"pattern": "nonce"},
        call_id=f"harness-grep-{sample}-{model_calls}",
        round_number=round_number,
    )
    appended = [grep_record]
    _append_exchange(messages, grep_record["message"], [grep_execution])
    matches = grep_execution["result"].get("matches", [])
    candidates: list[str] = []
    for match in matches if isinstance(matches, list) else []:
        path = str(match).split(":", 1)[0]
        if path and path not in already_read and path not in candidates:
            candidates.append(path)
    for index, path in enumerate(candidates[:2], 1):
        read_record, read_execution = _synthetic_call(
            root,
            name="read_file",
            arguments={"path": path},
            call_id=f"harness-read-{sample}-{model_calls}-{index}",
            round_number=round_number,
        )
        appended.append(read_record)
        _append_exchange(messages, read_record["message"], [read_execution])
    return appended


def run_lookup_c(
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
    """Run the frozen C lookup pipeline directly against ``workdir``."""
    chosen = _sampling(sampling)
    result = _base_result(chosen)
    result.update(gate_fired=False, checkpoint="none", strict_reject_reason=None)
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
    native_candidate: dict[str, str] | None = None
    model_calls = 0
    try:
        while model_calls < max_rounds:
            round_number = model_calls + 1
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
            model_calls += 1
            if record["executions"]:
                continue
            native_candidate = final_answer(record["message"])
            if native_candidate is None:
                break
            attempted = native_candidate
            if is_grounded(native_candidate["nonce"], _gate_payloads(state, result["rounds"])):
                result["landing_source"] = "native"
                accepted, strict_reason = strict_gate(native_candidate, result["rounds"])
                result["strict_reject_reason"] = strict_reason
                if accepted:
                    answer = native_candidate
                else:
                    result["harness_rejected"] = True
                    result["reject_reason"] = strict_reason
                break

            record["gate_rejected"] = True
            result["gate_fired"] = True
            result["checkpoint"] = "retrieval"
            retrieval = _retrieve(
                root,
                messages,
                result["rounds"],
                sample=0,
                model_calls=model_calls,
                round_number=round_number,
            )
            result["rounds"].extend(retrieval)
            result["extra_calls"] += len(retrieval)
            evidence_rounds = list(result["rounds"])
            payload = finalizer_request(state, evidence_rounds, model, chosen, max_tokens)
            response = request(endpoint, {}, payload, timeout)
            message, finish = _response_parts(response)
            result["rounds"].append(
                {
                    "round": round_number + 1,
                    "message": copy.deepcopy(message),
                    "executions": [],
                    "finish_reason": finish,
                    "harness_action": True,
                    "fresh_finalizer": True,
                }
            )
            result["extra_calls"] += 1
            model_calls += 1
            attempted = final_answer(message)
            result["landing_source"] = "finalizer"
            accepted, strict_reason = strict_gate(attempted, evidence_rounds)
            result["strict_reject_reason"] = strict_reason
            if accepted:
                answer = attempted
            else:
                result["harness_rejected"] = True
                result["reject_reason"] = strict_reason
            break

        if native_candidate is None and not result["gate_fired"] and answer is None:
            source_rounds = list(result["rounds"])
            b3 = apply_b3({"rounds": source_rounds})
            result["b3_reason"] = str(b3.get("b3_reason"))
            if b3.get("b3_landed"):
                attempted = {"answer": str(b3["b3_answer"]), "nonce": str(b3["b3_nonce"])}
                accepted, strict_reason = strict_gate(attempted, source_rounds)
                result["strict_reject_reason"] = strict_reason
                if accepted:
                    answer = attempted
                    result["landing_source"] = "b3"
                else:
                    result["harness_rejected"] = True
                    result["reject_reason"] = strict_reason
            if answer is None:
                evidence_rounds = source_rounds
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
                model_calls += 1
                attempted = final_answer(message)
                result["landing_source"] = "finalizer_rescue"
                accepted, strict_reason = strict_gate(attempted, evidence_rounds)
                result["strict_reject_reason"] = strict_reason
                if accepted:
                    answer = attempted
                    result["harness_rejected"] = False
                    result["reject_reason"] = None
                else:
                    result["harness_rejected"] = True
                    result["reject_reason"] = strict_reason

        result["model_calls"] = model_calls
        return _finish(result, answer, recorder)
    except Exception as error:
        result["model_calls"] = model_calls
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        return _finish(result, None, recorder)

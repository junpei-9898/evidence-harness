from __future__ import annotations

import threading

import pytest

from evidence_harness.instruments import usage as usage_module
from evidence_harness.instruments.monitors import (
    has_pseudo_tool_syntax,
    measure,
    summarize_explore,
)
from evidence_harness.instruments.usage import UsageRecorder, retrying, summarize_calls


def _response(*, usage=None):
    result = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
    }
    if usage is not None:
        result["usage"] = usage
    return result


def test_usage_recorder_passes_through_and_is_thread_local() -> None:
    recorder = UsageRecorder()
    wrapped = recorder.wrap(
        lambda _url, _headers, payload, _timeout: _response(
            usage={"prompt_tokens": payload["token"], "total_tokens": payload["token"] + 1}
        )
    )
    recorded = {}

    def worker(token):
        recorder.start()
        response = wrapped("u", {}, {"token": token, "messages": []}, 1)
        recorded[token] = (response, recorder.drain())

    threads = [threading.Thread(target=worker, args=(token,)) for token in (2, 5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [recorded[token][1][0]["usage"]["prompt_tokens"] for token in (2, 5)] == [2, 5]
    assert all(recorded[token][1][0]["attempt_index"] == 0 for token in (2, 5))


def test_usage_recorder_records_and_reraises_same_error() -> None:
    recorder = UsageRecorder()
    error = RuntimeError("offline")

    def failing(*args):
        raise error

    recorder.start()
    with pytest.raises(RuntimeError) as caught:
        recorder.wrap(failing)("u", {}, {}, 1)
    assert caught.value is error
    assert recorder.drain()[0]["error"] == "RuntimeError"


def test_usage_recorder_does_not_record_request_headers() -> None:
    secret = "synthetic-secret-value"
    recorder = UsageRecorder()
    recorder.start()
    wrapped = recorder.wrap(lambda *_args: _response())

    wrapped("u", {"Authorization": f"Bearer {secret}"}, {"messages": []}, 1)

    rendered = repr(recorder.drain())
    assert secret not in rendered
    assert "Authorization" not in rendered


def test_retrying_preserves_attempts_and_raises_last(monkeypatch) -> None:
    events = []
    values = [OSError("first"), {"ok": True}]

    def inner(*args):
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(usage_module.time, "sleep", lambda value: events.append(value))
    assert retrying(inner, retries=1, backoff=0.25)("u", {}, {}, 1) == {"ok": True}
    assert events == [0.25]

    errors = [OSError("first"), RuntimeError("last")]

    def always_fails(*args):
        raise errors.pop(0)

    with pytest.raises(RuntimeError, match="last"):
        retrying(always_fails, retries=1, backoff=0)("u", {}, {}, 1)


def test_summarize_calls_counts_missing_and_numeric_usage() -> None:
    calls = [
        {
            "ok": True,
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
            "elapsed_s": 1,
        },
        {"ok": True, "usage": None, "elapsed_s": 2},
        {"ok": False, "elapsed_s": 3},
    ]
    actual = summarize_calls(calls)

    assert (actual["calls"], actual["ok_calls"], actual["failed_calls"]) == (3, 2, 1)
    assert actual["calls_with_usage"] == 1 and actual["usage_missing"] == 1
    assert actual["prompt_tokens_total"] == 7 and actual["total_tokens"] == 9
    assert actual["final_prompt_tokens"] is None and actual["elapsed_total_s"] == 6


def test_measure_retains_reference_metrics_and_pseudo_detection() -> None:
    content = "synthetic evidence line long enough to be transcribed"
    rounds = [
        {
            "message": {"tool_calls": [{}]},
            "executions": [
                {
                    "name": "read_file",
                    "result": {
                        "wellformed": True,
                        "grounded": True,
                        "empty": False,
                        "content": content,
                    },
                }
            ],
        }
    ]

    actual = measure(rounds, f"answer: {content}")
    assert actual["round1_usage"] and actual["n_attempt"] == 1
    assert actual["d1e"] and actual["transcribed"] and not actual["ritual"]
    assert has_pseudo_tool_syntax("[TOOL_CALLS] synthetic")
    assert not has_pseudo_tool_syntax(None)


def test_summarize_explore_reports_gate_budget_and_usage() -> None:
    rounds = [
        {
            "finish_reason": "tool_calls",
            "message": {"tool_calls": [{}]},
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        {
            "finish_reason": "length",
            "message": {"tool_calls": [{}]},
            "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        },
    ]
    actual = summarize_explore(
        rounds, {"passed": True, "abstain": False, "reason": "passed"}, max_rounds=2
    )

    assert actual["gate_reason"] == "passed" and not actual["abstain"]
    assert actual["finish_reason_length"] and actual["round_cap"]
    assert actual["usage"] == {
        "calls": 2,
        "calls_with_usage": 2,
        "usage_missing": 0,
        "prompt_tokens_total": 10,
        "completion_tokens_total": 6,
        "total_tokens": 16,
        "final_prompt_tokens": 7,
    }
    assert actual["tokens_per_success"] == 16


def test_summarize_explore_does_not_count_abstain_as_success() -> None:
    actual = summarize_explore(
        [{"finish_reason": "stop", "message": {}, "usage": None}],
        {"passed": True, "abstain": True, "reason": "abstain"},
        max_rounds=6,
    )

    assert actual["abstain"] and actual["tokens_per_success"] is None
    assert not actual["finish_reason_length"] and not actual["round_cap"]

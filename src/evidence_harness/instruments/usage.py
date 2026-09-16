"""Thread-local transport usage instrumentation."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from typing import Any

from evidence_harness.transport import Transport


def _finish_reason(response: Any) -> Any:
    if not isinstance(response, Mapping):
        return None
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return None
    return choices[0].get("finish_reason")


class UsageRecorder:
    """Record transport attempts independently in each worker thread."""

    def __init__(self) -> None:
        self._local = threading.local()

    def _calls(self) -> list[dict[str, Any]]:
        calls = getattr(self._local, "calls", None)
        if calls is None:
            calls = []
            self._local.calls = calls
        return calls

    def start(self) -> None:
        self._local.calls = []

    def drain(self) -> list[dict[str, Any]]:
        calls = self._calls()
        self._local.calls = []
        return calls

    def wrap(self, inner: Transport) -> Transport:
        def transport(
            url: str,
            headers: dict[str, str],
            payload: dict[str, Any],
            timeout: float,
        ) -> dict[str, Any]:
            calls = self._calls()
            attempt_index = len(calls)
            started = time.monotonic()
            try:
                response = inner(url, headers, payload, timeout)
            except Exception as error:
                calls.append(
                    {
                        "ok": False,
                        "attempt_index": attempt_index,
                        "error": type(error).__name__,
                        "elapsed_s": time.monotonic() - started,
                    }
                )
                raise

            usage = response.get("usage") if isinstance(response, dict) else None
            calls.append(
                {
                    "ok": True,
                    "attempt_index": attempt_index,
                    "url": url,
                    "model": payload.get("model"),
                    "n_messages": len(payload.get("messages") or []),
                    "prompt_chars": len(
                        json.dumps(payload.get("messages") or [], ensure_ascii=False)
                    ),
                    "has_tools": bool(payload.get("tools")),
                    "max_tokens": payload.get("max_tokens"),
                    "usage": usage if isinstance(usage, dict) else None,
                    "finish_reason": _finish_reason(response),
                    "elapsed_s": time.monotonic() - started,
                }
            )
            return response

        return transport


def retrying(inner: Transport, retries: int = 1, backoff: float = 3.0) -> Transport:
    """Retry transport exceptions, preserving every attempt for outer recorders."""

    def transport(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return inner(url, headers, payload, timeout)
            except Exception as error:
                last = error
                if attempt < retries:
                    time.sleep(backoff)
        if last is None:
            raise ValueError("retries must be non-negative")
        raise last

    return transport


def _usage_value(usage: Mapping[str, Any], key: str) -> int | float:
    value = usage.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def summarize_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    ok_calls = [call for call in calls if call.get("ok") is True]
    with_usage = [call for call in ok_calls if isinstance(call.get("usage"), Mapping)]
    last_ok_usage = ok_calls[-1].get("usage") if ok_calls else None
    final_prompt_tokens = (
        last_ok_usage.get("prompt_tokens") if isinstance(last_ok_usage, Mapping) else None
    )
    return {
        "calls": len(calls),
        "ok_calls": len(ok_calls),
        "failed_calls": len(calls) - len(ok_calls),
        "calls_with_usage": len(with_usage),
        "usage_missing": len(ok_calls) - len(with_usage),
        "prompt_tokens_total": sum(
            _usage_value(call["usage"], "prompt_tokens") for call in with_usage
        ),
        "completion_tokens_total": sum(
            _usage_value(call["usage"], "completion_tokens") for call in with_usage
        ),
        "total_tokens": sum(_usage_value(call["usage"], "total_tokens") for call in with_usage),
        "final_prompt_tokens": (
            final_prompt_tokens
            if isinstance(final_prompt_tokens, (int, float))
            and not isinstance(final_prompt_tokens, bool)
            else None
        ),
        "elapsed_total_s": sum(
            float(call.get("elapsed_s", 0.0))
            for call in calls
            if isinstance(call.get("elapsed_s"), (int, float))
            and not isinstance(call.get("elapsed_s"), bool)
        ),
    }

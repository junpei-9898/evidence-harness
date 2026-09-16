"""Transport boundary for OpenAI-compatible chat completions."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

Transport = Callable[[str, dict[str, str], dict, float], dict]


def _status_code(error: Exception) -> int | None:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    return None


def http_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """POST one chat request, retaining the reference transport's retry contract."""
    for attempt in (1, 2):
        try:
            response = httpx.post(
                url,
                headers={"Content-Type": "application/json", **headers},
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            body = response.json()
            break
        except (httpx.HTTPError, TimeoutError) as error:
            code = _status_code(error)
            if attempt == 2 or (code is not None and code < 500):
                raise
            print(f"transport retry after {type(error).__name__} ({code})", flush=True)
            time.sleep(15)
    if not isinstance(body, dict):
        raise ValueError("chat response must be a JSON object")
    return body


def _response_parts(response: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    try:
        choice = response["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("transport response has no choices[0].message") from exc
    if not isinstance(choice, Mapping) or not isinstance(message, Mapping):
        raise ValueError("transport choice and message must be objects")
    finish = choice.get("finish_reason")
    return dict(message), finish if isinstance(finish, str) else None

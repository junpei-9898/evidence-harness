from __future__ import annotations

import httpx
import pytest

from evidence_harness import transport
from evidence_harness.transport import _response_parts, http_transport


class FakeResponse:
    def __init__(self, body, status: int = 200) -> None:
        self.body = body
        self.request = httpx.Request("POST", "https://unit.invalid/chat")
        self.response = httpx.Response(status, request=self.request)

    def raise_for_status(self) -> None:
        self.response.raise_for_status()

    def json(self):
        return self.body


def test_http_transport_posts_json_and_preserves_headers(monkeypatch) -> None:
    seen = {}

    def post(url, *, headers, json, timeout):
        seen.update(url=url, headers=headers, payload=json, timeout=timeout)
        return FakeResponse({"choices": []})

    monkeypatch.setattr(transport.httpx, "post", post)
    actual = http_transport(
        "https://unit.invalid/chat", {"Authorization": "token"}, {"model": "m"}, 2.5
    )

    assert actual == {"choices": []}
    assert seen == {
        "url": "https://unit.invalid/chat",
        "headers": {"Content-Type": "application/json", "Authorization": "token"},
        "payload": {"model": "m"},
        "timeout": 2.5,
    }


def test_http_transport_retries_server_error(monkeypatch) -> None:
    responses = [FakeResponse({}, 503), FakeResponse({"ok": True})]
    sleeps = []
    monkeypatch.setattr(transport.httpx, "post", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(transport.time, "sleep", sleeps.append)

    assert http_transport("https://unit.invalid/chat", {}, {}, 1) == {"ok": True}
    assert sleeps == [15]


def test_http_transport_does_not_retry_client_error(monkeypatch) -> None:
    calls = []

    def post(*args, **kwargs):
        calls.append(None)
        return FakeResponse({}, 400)

    monkeypatch.setattr(transport.httpx, "post", post)
    with pytest.raises(httpx.HTTPStatusError):
        http_transport("https://unit.invalid/chat", {}, {}, 1)
    assert len(calls) == 1


def test_http_transport_rejects_non_object_json(monkeypatch) -> None:
    monkeypatch.setattr(transport.httpx, "post", lambda *args, **kwargs: FakeResponse([]))
    with pytest.raises(ValueError, match="JSON object"):
        http_transport("https://unit.invalid/chat", {}, {}, 1)


def test_response_parts_validates_shape_and_finish_reason() -> None:
    message, finish = _response_parts(
        {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    )
    assert message == {"content": "ok"} and finish == "stop"
    assert _response_parts({"choices": [{"message": {}, "finish_reason": 1}]}) == ({}, None)
    with pytest.raises(ValueError, match=r"choices\[0\]\.message"):
        _response_parts({"choices": []})
    with pytest.raises(ValueError, match="must be objects"):
        _response_parts({"choices": [{"message": []}]})

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from evidence_harness.profiles.explore import run_explore
from evidence_harness.profiles.lookup import _chat_payload, run_lookup
from evidence_harness.profiles.lookup_c import run_lookup_c


class CaptureTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.payloads: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []

    def __call__(
        self,
        _url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        _timeout: float,
    ) -> dict[str, Any]:
        self.headers.append(copy.deepcopy(headers))
        self.payloads.append(copy.deepcopy(payload))
        return copy.deepcopy(self.responses[len(self.payloads) - 1])


def _tool_response(*, reasoning: object = None, reasoning_content: object = None):
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-synthetic",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path":"facts.txt"}',
                },
            }
        ],
    }
    if reasoning is not None:
        message["reasoning"] = reasoning
    if reasoning_content is not None:
        message["reasoning_content"] = reasoning_content
    return {"choices": [{"message": message, "finish_reason": "tool_calls"}]}


def test_chat_payload_defaults_to_thinking_kwargs() -> None:
    payload = _chat_payload(
        "synthetic-model",
        [{"role": "user", "content": "question"}],
        [],
        {"temperature": 0.7},
        4096,
    )

    assert payload["chat_template_kwargs"] == {"enable_thinking": True}


@pytest.mark.parametrize("kwargs", [None, {}])
def test_chat_payload_omits_empty_thinking_kwargs(kwargs: object) -> None:
    payload = _chat_payload(
        "synthetic-model",
        [{"role": "user", "content": "question"}],
        [],
        {"temperature": 0.7},
        4096,
        kwargs,
    )

    assert "chat_template_kwargs" not in payload


def test_reasoning_content_lands_b3_without_changing_chat_history(tmp_path: Path) -> None:
    (tmp_path / "facts.txt").write_text("value=731\nnonce-stable7", encoding="utf-8")
    draft = '{"answer":"731","nonce":"nonce-stable7"}'
    transport = CaptureTransport(
        [
            _tool_response(reasoning_content="intermediate"),
            _tool_response(reasoning_content=draft),
        ]
    )

    result = run_lookup(
        "Which value?",
        tmp_path,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
        max_rounds=2,
    )

    assert result["landing_source"] == "b3"
    assert result["answer"] == "731"
    assert result["rounds"][-1]["message"]["reasoning"] == draft
    prior_assistant = transport.payloads[1]["messages"][2]
    assert prior_assistant["reasoning_content"] == "intermediate"
    assert "reasoning" not in prior_assistant


def test_reasoning_field_takes_priority_over_reasoning_content(tmp_path: Path) -> None:
    (tmp_path / "facts.txt").write_text("value=731\nnonce-stable7", encoding="utf-8")
    preferred = '{"answer":"731","nonce":"nonce-stable7"}'
    transport = CaptureTransport(
        [_tool_response(reasoning=preferred, reasoning_content="not a draft")]
    )

    result = run_lookup(
        "Which value?",
        tmp_path,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
        max_rounds=1,
    )

    assert result["landing_source"] == "b3"
    assert result["rounds"][0]["message"]["reasoning"] == preferred


def test_lookup_api_key_is_sent_but_not_recorded(tmp_path: Path) -> None:
    (tmp_path / "facts.txt").write_text("value=731\nnonce-stable7", encoding="utf-8")
    secret = "synthetic-secret-value"
    transport = CaptureTransport(
        [
            _tool_response(
                reasoning_content='{"answer":"731","nonce":"nonce-stable7"}'
            )
        ]
    )

    result = run_lookup(
        "Which value?",
        tmp_path,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
        max_rounds=1,
        api_key=secret,
    )

    assert transport.headers == [{"Authorization": f"Bearer {secret}"}]
    assert secret not in json.dumps(result, ensure_ascii=False)


def test_explore_without_api_key_sends_empty_headers(tmp_path: Path) -> None:
    transport = CaptureTransport(
        [
            {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "synthetic"},
                        "finish_reason": "stop",
                    }
                ]
            }
        ]
    )

    run_explore(
        "Inspect the snapshot.",
        tmp_path,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
    )

    assert transport.headers == [{}]


def test_lookup_c_omits_kwargs_from_round_and_reset_finalizer(tmp_path: Path) -> None:
    (tmp_path / "facts.txt").write_text("value=731\nnonce-real", encoding="utf-8")
    transport = CaptureTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"answer":"731","nonce":"nonce-fake"}',
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"answer":"731","nonce":"nonce-real"}',
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        ]
    )

    result = run_lookup_c(
        "Which value?",
        tmp_path,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
        max_rounds=2,
        chat_template_kwargs=None,
    )

    assert result["landing_source"] == "finalizer"
    assert all("chat_template_kwargs" not in payload for payload in transport.payloads)

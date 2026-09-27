"""Unit tests for the value-format contract (profiles/contracts.py) and its reuse
across the native lookup round, the rescue finalizer, and the C-layer reset finalizer.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from evidence_harness.profiles.contracts import (
    CONTRACT_SENTENCE,
    CONTRACT_VERSION,
    apply_value_contract,
    contract_sha256,
)
from evidence_harness.profiles.lookup import SYSTEM, run_lookup
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


def _tool_response():
    return {
        "choices": [
            {
                "message": {
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
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


def test_contract_sha256_matches_frozen_digest() -> None:
    assert contract_sha256() == "83395ae409056ad0747de5efb65aadc2c065972345ccece78e96ea6a8533e86a"
    assert CONTRACT_VERSION == "value-format-contract-1.0"


def test_apply_value_contract_appends_with_single_space() -> None:
    system = "Answer the question."
    assert apply_value_contract(system) == system + " " + CONTRACT_SENTENCE


def test_apply_value_contract_rstrips_trailing_whitespace_before_appending() -> None:
    system = "Answer the question.   \n\n"
    result = apply_value_contract(system)
    assert result == "Answer the question." + " " + CONTRACT_SENTENCE
    assert "  " not in result.split(CONTRACT_SENTENCE)[0]


def test_run_lookup_appends_contract_to_native_round_system(tmp_path: Path) -> None:
    (tmp_path / "facts.txt").write_text("value=42\nnonce-real", encoding="utf-8")
    transport = CaptureTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"answer":"42","nonce":"nonce-real"}',
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        ]
    )

    result = run_lookup(
        "Which value?",
        tmp_path,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
        max_rounds=1,
        value_contract="digits-only",
    )

    assert result["landing_source"] == "native"
    expected_system = apply_value_contract(SYSTEM)
    assert transport.payloads[0]["messages"][0]["content"] == expected_system
    assert result["value_contract"] == {
        "name": "digits-only",
        "version": CONTRACT_VERSION,
        "sha256": contract_sha256(),
    }


def test_run_lookup_none_contract_leaves_system_untouched(tmp_path: Path) -> None:
    (tmp_path / "facts.txt").write_text("value=42\nnonce-real", encoding="utf-8")
    transport = CaptureTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"answer":"42","nonce":"nonce-real"}',
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        ]
    )

    result = run_lookup(
        "Which value?",
        tmp_path,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
        max_rounds=1,
        value_contract="none",
    )

    assert transport.payloads[0]["messages"][0]["content"] == SYSTEM
    assert result["value_contract"] == {
        "name": "none",
        "version": CONTRACT_VERSION,
        "sha256": None,
    }


def test_run_lookup_rescue_finalizer_reuses_contract_bearing_system(tmp_path: Path) -> None:
    (tmp_path / "facts.txt").write_text("value=731\nnonce-real", encoding="utf-8")
    transport = CaptureTransport(
        [
            _tool_response(),
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

    result = run_lookup(
        "Which value?",
        tmp_path,
        model="synthetic-model",
        base_url="http://model.invalid/v1",
        transport=transport,
        max_rounds=1,
        value_contract="digits-only",
    )

    assert result["landing_source"] == "finalizer"
    expected_system = apply_value_contract(SYSTEM)
    assert transport.payloads[0]["messages"][0]["content"] == expected_system
    assert transport.payloads[1]["messages"][0]["content"] == expected_system


def test_run_lookup_c_reset_finalizer_reuses_contract_bearing_system(tmp_path: Path) -> None:
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
        value_contract="digits-only",
    )

    assert result["landing_source"] == "finalizer"
    expected_system = apply_value_contract(SYSTEM)
    assert transport.payloads[0]["messages"][0]["content"] == expected_system
    assert transport.payloads[1]["messages"][0]["content"] == expected_system

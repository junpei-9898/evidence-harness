import pytest

from evidence_harness.gates.draft import B3_VERSION, apply_b3, extract_draft
from evidence_harness.gates.finalize import (
    _finalizer_user,
    _gate_payloads,
    _read_evidence,
    finalizer_request,
    gate_final,
)
from evidence_harness.gates.grounding import content_payloads, final_answer, is_grounded
from evidence_harness.gates.identity import nonce_tokens, strict_gate


def _execution(
    content: str,
    *,
    name: str = "read_file",
    path: str = "notes/synthetic.txt",
) -> dict[str, object]:
    return {
        "name": name,
        "arguments": f'{{"path":"{path}"}}',
        "result": {"path": path, "content": content},
    }


def _record(
    reasoning: object,
    *,
    content: object = "",
    finish_reason: object = "length",
    evidence: str = "value=731\nnonce-stable7",
    tool_calls: object = None,
) -> dict[str, object]:
    return {
        "rounds": [
            {
                "message": {
                    "content": content,
                    "reasoning": reasoning,
                    "tool_calls": tool_calls,
                },
                "executions": [_execution(evidence)],
                "finish_reason": finish_reason,
            }
        ]
    }


def test_grounding_collects_only_nonempty_file_tool_contents() -> None:
    rounds = [
        {
            "executions": [
                _execution("read body"),
                _execution("grep body", name="grep"),
                _execution("glob body", name="glob"),
                _execution("ignored body", name="unknown"),
                _execution(""),
                {"name": "read_file", "result": {"content": 17}},
            ]
        },
        {"executions": "not-a-list"},
    ]

    assert content_payloads(rounds) == ["read body", "grep body", "glob body"]
    assert is_grounded("grep", content_payloads(rounds)) is True
    assert is_grounded("", content_payloads(rounds)) is False


def test_final_answer_finds_first_valid_json_and_requires_landing() -> None:
    message = {
        "content": 'prefix {"answer": 4} then {"answer":"731","nonce":"nonce-stable7"}',
    }
    assert final_answer(message) == {"answer": "731", "nonce": "nonce-stable7"}
    assert final_answer({**message, "tool_calls": [{"id": "synthetic"}]}) is None
    assert final_answer({"content": "  "}) is None


def test_b3_version_is_frozen() -> None:
    assert B3_VERSION == "1.2"


def test_b3_rejects_non_cap_unit() -> None:
    result = apply_b3(
        _record(
            '{"answer":"731","nonce":"nonce-stable7"}',
            content="landed",
            finish_reason="stop",
        )
    )

    assert result["b3_landed"] is False
    assert result["b3_reason"] == "not_cap"
    assert "b3_correct" not in result


@pytest.mark.parametrize(
    ("reasoning", "reason"),
    [
        ("no object here", "no_draft"),
        (
            '{"answer":"731","nonce":"nonce-stable7"}'
            ' {"answer":"914","nonce":"nonce-other8"}',
            "conflicting_drafts",
        ),
        ('{"answer":"alias -> 731","nonce":"nonce-stable7"}', "compound_answer"),
        ('{"answer":"731","nonce":"nonce-absent9"}', "nonce_ungrounded"),
    ],
)
def test_b3_rejects_each_draft_failure(reasoning: str, reason: str) -> None:
    result = apply_b3(_record(reasoning))

    assert result["b3_landed"] is False
    assert result["b3_reason"] == reason
    assert "b3_correct" not in result


def test_b3_rejects_duplicate_key_json_as_no_draft() -> None:
    reasoning = (
        '{"answer":"731","answer":"914","nonce":"nonce-stable7"}'
    )

    assert extract_draft(reasoning) is None
    result = apply_b3(_record(reasoning))
    assert result["b3_reason"] == "no_draft"


def test_b3_accepts_unique_grounded_noncompound_draft_without_gold_scoring() -> None:
    result = apply_b3(_record('{"answer":"731","nonce":"nonce-stable7"}'))

    assert result["b3_landed"] is True
    assert result["b3_answer"] == "731"
    assert result["b3_nonce"] == "nonce-stable7"
    assert "b3_correct" not in result
    assert "b3_reason" not in result


def test_finalizer_read_evidence_is_unique_and_read_only() -> None:
    rounds = [
        {
            "executions": [
                _execution("first", path="notes/first.txt"),
                _execution("grep copy", name="grep", path="notes/search.txt"),
            ]
        },
        {
            "executions": [
                _execution("replacement", path="notes/first.txt"),
                _execution("second", path="notes/second.txt"),
            ]
        },
    ]

    assert _read_evidence(rounds) == [
        ("notes/first.txt", "first"),
        ("notes/second.txt", "second"),
    ]


def test_finalizer_user_has_exact_question_and_evidence_shape() -> None:
    state = {
        "prefix_messages": [
            {"role": "system", "content": "Synthetic system."},
            {"role": "user", "content": "Which synthetic value?"},
        ]
    }
    rounds = [
        {
            "executions": [
                _execution("value=731", path="notes/first.txt"),
                _execution("nonce-stable7", path="notes/second.txt"),
            ]
        }
    ]

    assert _finalizer_user(state, rounds) == (
        "Which synthetic value?\n\n"
        "Evidence collected (path: content):\n"
        "notes/first.txt:\nvalue=731\n\n"
        "notes/second.txt:\nnonce-stable7"
    )


def test_finalizer_request_is_history_free_tools_free_and_preserves_sampling() -> None:
    state = {
        "prefix_messages": [
            {"role": "system", "content": "Synthetic system."},
            {"role": "user", "content": "Which synthetic value?"},
            {"role": "assistant", "content": "Old history."},
        ]
    }
    rounds = [{"executions": [_execution("value=731\nnonce-stable7")]}]

    payload = finalizer_request(
        state,
        rounds,
        "synthetic-model",
        {"temperature": 0.4, "top_p": 0.9},
        512,
    )

    assert payload == {
        "model": "synthetic-model",
        "messages": [
            {"role": "system", "content": "Synthetic system."},
            {
                "role": "user",
                "content": (
                    "Which synthetic value?\n\n"
                    "Evidence collected (path: content):\n"
                    "notes/synthetic.txt:\nvalue=731\nnonce-stable7"
                ),
            },
        ],
        "temperature": 0.4,
        "top_p": 0.9,
        "max_tokens": 512,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    assert "tools" not in payload


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (None, "unparseable_final_answer"),
        ({"answer": 731, "nonce": "nonce-stable7"}, "unparseable_final_answer"),
        ({"answer": "731", "nonce": ""}, "empty_nonce"),
        ({"answer": "731", "nonce": "nonce-absent9"}, "nonce_ungrounded"),
    ],
)
def test_gate_final_rejects_each_reason(answer: object, reason: str) -> None:
    accepted, actual_reason = gate_final(answer, ["value=731\nnonce-stable7"])

    assert accepted is False
    assert actual_reason == reason


def test_gate_final_accepts_grounded_nonce_and_gate_payloads_include_all_file_tools() -> None:
    rounds = [
        {
            "executions": [
                _execution("read payload"),
                _execution("grep payload", name="grep"),
                _execution("glob payload", name="glob"),
            ]
        }
    ]
    assert _gate_payloads({"pack_exclude_targets": True}, rounds) == [
        "read payload",
        "grep payload",
        "glob payload",
    ]
    assert gate_final({"answer": "731", "nonce": "grep payload"}, _gate_payloads({}, rounds)) == (
        True,
        None,
    )


def test_nonce_tokens_only_extracts_file_tool_token_shapes() -> None:
    rounds = [
        {
            "executions": [
                _execution("nonce-stable7 and nonce-other8"),
                _execution("nonce-third9", name="grep"),
                _execution("nonce-ignored1", name="unknown"),
            ]
        }
    ]

    assert nonce_tokens(rounds) == {"nonce-stable7", "nonce-other8", "nonce-third9"}


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (None, "unparseable_final_answer"),
        ({"answer": "731", "nonce": ""}, "empty_nonce"),
        ({"answer": "731", "nonce": "nonce-missing9"}, "nonce_not_exact_token"),
        ({"answer": " nonce-stable7 ", "nonce": "nonce-stable7"}, "answer_is_nonce_shaped"),
    ],
)
def test_strict_gate_rejects_each_reason(answer: object, reason: str) -> None:
    rounds = [{"executions": [_execution("value=731\nnonce-stable7")]}]

    accepted, actual_reason = strict_gate(answer, rounds)

    assert accepted is False
    assert actual_reason == reason


def test_strict_gate_accepts_parsed_message_with_exact_nonce_token() -> None:
    message = {"content": '{"answer":"731","nonce":"nonce-stable7"}'}
    rounds = [{"executions": [_execution("value=731\nnonce-stable7")]}]

    assert strict_gate(message, rounds) == (True, None)

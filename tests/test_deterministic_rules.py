import hashlib
from pathlib import Path

from evidence_harness.rules.deterministic import (
    RESEARCH_RULE_SHA256,
    complete,
    extract_value,
    identifier_tokens,
    rule_sha256,
    type_check,
)


def _rounds() -> list[dict[str, object]]:
    return [
        {
            "executions": [
                {
                    "name": "read_file",
                    "arguments": '{"path":"notes/Synthetic-Item.md"}',
                    "result": {
                        "content": "metric_key=731\nother-key: 914\n# Synthetic Heading"
                    },
                },
                {
                    "name": "grep",
                    "arguments": '{"path":"notes/ignored.md"}',
                    "result": {"content": "grep_key=123\n# Ignored Heading"},
                },
            ]
        }
    ]


def test_extract_value_covers_each_r_a_reason() -> None:
    assert extract_value("731") == ("731", "bare_digits")
    assert extract_value("value: 731 units") == ("731", "unique_digit_token")
    assert extract_value("values 731 and 914") == (None, "ambiguous_digit_tokens")
    assert extract_value("no numeric token") == (None, "no_digit_token")


def test_identifier_tokens_uses_pack_and_read_paths_keys_and_headings() -> None:
    assert identifier_tokens(_rounds(), ["pack/Bundle.toml"]) == frozenset(
        {
            "bundle.toml",
            "bundle",
            "synthetic-item.md",
            "synthetic-item",
            "metric_key",
            "other-key",
            "synthetic heading",
        }
    )


def test_type_check_covers_each_r_b_reason() -> None:
    identifiers = frozenset({"synthetic-item", "metric_key"})

    assert type_check("Synthetic-Item / metric_key", identifiers) == (
        True,
        "all_tokens_identifiers",
    )
    assert type_check("metric_key / unknown", identifiers) == (
        False,
        "has_non_identifier_token",
    )
    assert type_check(" , / ; 、 ", identifiers) == (False, "empty")


def test_complete_applies_r_a_before_r_b() -> None:
    result = complete("value: 731 units", _rounds(), ["pack/Bundle.toml"])

    assert result == {
        "answer": "731",
        "answer_raw": "value: 731 units",
        "extracted": True,
        "extract_reason": "unique_digit_token",
        "nonlanded_by_type_check": False,
        "type_reason": "skipped_value",
    }


def test_complete_nonlands_identifier_answer_and_preserves_raw_value() -> None:
    assert complete("metric_key", _rounds(), []) == {
        "answer": None,
        "answer_raw": "metric_key",
        "extracted": False,
        "extract_reason": "no_digit_token",
        "nonlanded_by_type_check": True,
        "type_reason": "all_tokens_identifiers",
    }
    assert complete(None, _rounds(), []) == {
        "answer": None,
        "answer_raw": None,
        "extracted": False,
        "extract_reason": "no_digit_token",
        "nonlanded_by_type_check": False,
        "type_reason": "empty",
    }


def test_rule_digests_distinguish_local_file_from_frozen_research_source() -> None:
    module_path = Path(__file__).parents[1] / "src/evidence_harness/rules/deterministic.py"

    assert rule_sha256() == hashlib.sha256(module_path.read_bytes()).hexdigest()
    assert RESEARCH_RULE_SHA256 == (
        "e65a65a44c1120b50cb2e1f1e23b69396a80635a517d11e511b945cd72e163d3"
    )

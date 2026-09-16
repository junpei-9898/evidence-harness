from evidence_harness.gates.citation import (
    ABSTAIN_TEXT,
    GATE_FAILURE,
    apply_gate,
    parse_answer,
    quote_is_returned,
    returned_evidence,
)
from evidence_harness.loop.ledger import Ledger


def _ledger() -> Ledger:
    ledger = Ledger([], {"files": {}})
    ledger.raw_texts = [
        {
            "path": "./notes/item.txt",
            "tool": "read_file",
            "start": 0,
            "text": "Synthetic first line.\nSecond line has a stable quoted phrase.",
        },
        {
            "path": "notes/gap.txt",
            "tool": "read_file",
            "start": 0,
            "text": "first-run",
        },
        {
            "path": "notes/gap.txt",
            "tool": "read_file",
            "start": 20,
            "text": "second-run",
        },
        {
            "path": "notes/search.txt",
            "tool": "grep",
            "start": 30,
            "text": "A grep result contains the exact synthetic phrase.",
        },
    ]
    return ledger


def test_parse_answer_only_accepts_trailing_pair_and_normalizes_path() -> None:
    parsed = parse_answer(
        "Synthetic answer.\n出典: ././notes/item.txt\n引用: Second line has a stable quoted phrase."
    )
    assert parsed == {
        "body": "Synthetic answer.",
        "source_path": "notes/item.txt",
        "quote": "Second line has a stable quoted phrase.",
        "abstain": False,
    }
    assert parse_answer("出典: notes/item.txt\nnot a quote")["source_path"] is None
    assert parse_answer(None)["body"] == ""


def test_returned_evidence_reconstructs_contiguous_runs_and_grep_lines() -> None:
    evidence = returned_evidence(_ledger())

    assert evidence["notes/gap.txt"]["read_runs"] == ["first-run", "second-run"]
    assert evidence["notes/search.txt"]["grep_lines"] == [
        "A grep result contains the exact synthetic phrase."
    ]


def test_quote_match_ignores_whitespace_and_literal_multiline_escapes() -> None:
    ledger = _ledger()

    assert quote_is_returned(
        "./notes/item.txt",
        r"Synthetic first line.\nSecond line has a stable quoted phrase.",
        ledger,
    )
    assert quote_is_returned(
        "notes/search.txt", "grep result contains the exact synthetic phrase", ledger
    )
    assert not quote_is_returned("notes/missing.txt", "synthetic phrase", ledger)


def test_gate_passes_grounded_answer_and_reports_quote_length() -> None:
    content = (
        "Synthetic answer.\n"
        "出典: notes/item.txt\n"
        "引用: Second line has a stable quoted phrase."
    )

    result = apply_gate(content, _ledger())

    assert result["passed"] is True
    assert result["abstain"] is False
    assert result["reason"] == "passed"
    assert result["quote_length_ok"] is True
    assert result["gated_content"] == content


def test_gate_passes_short_verbatim_quote_but_marks_length_not_ok() -> None:
    result = apply_gate(
        "Answer.\n出典: notes/gap.txt\n引用: first-run",
        _ledger(),
    )

    assert result["passed"] is True
    assert result["reason"] == "passed"
    assert result["quote_length_ok"] is False


def test_gate_allows_explicit_abstention_without_citation() -> None:
    content = f"調査しましたが、{ABSTAIN_TEXT}。"

    result = apply_gate(content, _ledger())

    assert result["passed"] is True
    assert result["abstain"] is True
    assert result["reason"] == "abstain"
    assert "quote_length_ok" not in result


def test_gate_rejects_missing_source() -> None:
    result = apply_gate("Synthetic unsupported answer.", _ledger())

    assert result["passed"] is False
    assert result["reason"] == "missing_source"
    assert result["gated_content"] == GATE_FAILURE


def test_gate_rejects_missing_quote() -> None:
    result = apply_gate("Answer.\n出典: notes/item.txt\n引用: ", _ledger())

    assert result["passed"] is False
    assert result["reason"] == "missing_quote"
    assert result["quote_length_ok"] is False


def test_gate_rejects_source_that_was_not_fetched() -> None:
    result = apply_gate(
        "Answer.\n出典: notes/unread.txt\n引用: This synthetic quote was never fetched.",
        _ledger(),
    )

    assert result["passed"] is False
    assert result["reason"] == "source_not_fetched"
    assert result["quote_length_ok"] is True


def test_gate_rejects_nonverbatim_quote() -> None:
    result = apply_gate(
        "Answer.\n出典: notes/item.txt\n引用: This phrase does not occur in returned evidence.",
        _ledger(),
    )

    assert result["passed"] is False
    assert result["reason"] == "quote_not_verbatim"
    assert result["gated_content"] == GATE_FAILURE

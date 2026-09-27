from evidence_harness.gates.citation import (
    ABSTAIN_TEXT,
    GATE_CONTRACT_V1,
    GATE_CONTRACT_V2,
    GATE_FAILURE,
    apply_gate,
    normalize_citation_contract,
    parse_answer,
    quote_is_returned,
    returned_evidence,
    unwrap_outer_once,
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


def test_normalize_citation_contract_resolves_short_aliases_and_passes_through_others() -> None:
    assert normalize_citation_contract("v1") == GATE_CONTRACT_V1
    assert normalize_citation_contract("v2") == GATE_CONTRACT_V2
    assert normalize_citation_contract("v2.0-unwrap1") == "v2.0-unwrap1"
    assert normalize_citation_contract("unrecognized-contract") == "unrecognized-contract"


def test_unwrap_outer_once_yields_raw_first_then_symmetric_candidates() -> None:
    backtick_candidates = unwrap_outer_once("`Second line has a stable quoted phrase.`")

    assert backtick_candidates[0] == ("raw", "`Second line has a stable quoted phrase.`")
    assert backtick_candidates[1] == (
        "unwrapped_backtick",
        "Second line has a stable quoted phrase.",
    )
    assert len(backtick_candidates) == 2

    dquote_candidates = unwrap_outer_once('"Second line has a stable quoted phrase."')

    assert dquote_candidates[1] == ("unwrapped_dquote", "Second line has a stable quoted phrase.")
    assert len(dquote_candidates) == 2


def test_unwrap_outer_once_rejects_asymmetric_wrapper() -> None:
    quote = "`Second line has a stable quoted phrase.\""

    assert unwrap_outer_once(quote) == [("raw", quote)]


def test_unwrap_outer_once_rejects_whitespace_only_inner() -> None:
    assert unwrap_outer_once("` `") == [("raw", "` `")]


def test_unwrap_outer_once_removes_only_one_layer_leaving_fence_residue() -> None:
    quote = "```Second line has a stable quoted phrase.```"

    candidates = unwrap_outer_once(quote)

    assert candidates[0] == ("raw", quote)
    assert len(candidates) == 2
    form, inner = candidates[1]
    assert form == "unwrapped_backtick"
    # exactly one backtick removed from each side; two remain (the fence is not fully stripped)
    assert inner == "``Second line has a stable quoted phrase.``"


def test_gate_v2_accepts_backtick_wrapped_verbatim_quote() -> None:
    content = (
        "Synthetic answer.\n"
        "出典: notes/item.txt\n"
        "引用: `Second line has a stable quoted phrase.`"
    )

    result = apply_gate(content, _ledger(), GATE_CONTRACT_V2)

    assert result["passed"] is True
    assert result["reason"] == "passed"
    assert result["quote_match_form"] == "unwrapped_backtick"
    assert result["gate_contract"] == GATE_CONTRACT_V2
    assert result["quote_length_ok_matched"] is True
    assert result["quote"] == "`Second line has a stable quoted phrase.`"


def test_gate_v2_accepts_dquote_wrapped_verbatim_quote() -> None:
    content = (
        "Synthetic answer.\n"
        "出典: notes/item.txt\n"
        '引用: "Second line has a stable quoted phrase."'
    )

    result = apply_gate(content, _ledger(), GATE_CONTRACT_V2)

    assert result["passed"] is True
    assert result["reason"] == "passed"
    assert result["quote_match_form"] == "unwrapped_dquote"
    assert result["gate_contract"] == GATE_CONTRACT_V2


def test_gate_v2_rejects_asymmetric_wrapped_quote() -> None:
    content = (
        "Synthetic answer.\n"
        "出典: notes/item.txt\n"
        "引用: `Second line has a stable quoted phrase.\""
    )

    result = apply_gate(content, _ledger(), GATE_CONTRACT_V2)

    assert result["passed"] is False
    assert result["reason"] == "quote_not_verbatim"
    assert result["quote_match_form"] is None
    assert "quote_length_ok_matched" not in result


def test_gate_v2_rejects_fence_wrapped_quote_because_only_one_layer_is_removed() -> None:
    content = (
        "Synthetic answer.\n"
        "出典: notes/item.txt\n"
        "引用: ```Second line has a stable quoted phrase.```"
    )

    result = apply_gate(content, _ledger(), GATE_CONTRACT_V2)

    assert result["passed"] is False
    assert result["reason"] == "quote_not_verbatim"
    assert result["quote_match_form"] is None


def test_gate_v1_contract_is_inert_to_wrapped_quotes_that_v2_accepts() -> None:
    content = (
        "Synthetic answer.\n"
        "出典: notes/item.txt\n"
        "引用: `Second line has a stable quoted phrase.`"
    )

    v1_result = apply_gate(content, _ledger(), GATE_CONTRACT_V1)
    v2_result = apply_gate(content, _ledger(), GATE_CONTRACT_V2)

    assert v1_result["passed"] is False
    assert v1_result["reason"] == "quote_not_verbatim"
    assert v1_result["gate_contract"] == GATE_CONTRACT_V1
    assert v2_result["passed"] is True


def test_gate_default_contract_is_v1() -> None:
    content = (
        "Synthetic answer.\n"
        "出典: notes/item.txt\n"
        "引用: `Second line has a stable quoted phrase.`"
    )

    result = apply_gate(content, _ledger())

    assert result["reason"] == "quote_not_verbatim"
    assert result["gate_contract"] == GATE_CONTRACT_V1


def test_gate_shipped_strings_are_unchanged_regardless_of_contract_or_match_form() -> None:
    content = (
        "Synthetic answer.\n"
        "出典: notes/item.txt\n"
        "引用: `Second line has a stable quoted phrase.`"
    )

    v1_result = apply_gate(content, _ledger(), GATE_CONTRACT_V1)
    v2_result = apply_gate(content, _ledger(), GATE_CONTRACT_V2)

    # body / source_path / quote come from parse_answer alone and never change with
    # the contract or with which candidate form ultimately matched.
    assert v1_result["quote"] == v2_result["quote"] == "`Second line has a stable quoted phrase.`"
    assert v1_result["body"] == v2_result["body"] == "Synthetic answer."
    assert v1_result["source_path"] == v2_result["source_path"] == "notes/item.txt"
    # gated_content reflects pass/fail outcome, not the match form.
    assert v1_result["gated_content"] == GATE_FAILURE
    assert v2_result["gated_content"] == content

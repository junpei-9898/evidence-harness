from __future__ import annotations

from .conftest import load_fixtures

EXPLORE_TAGS = {
    "paging:offset",
    "paging:line",
    "paging:both_given",
    "paging:max_chars_boundary",
    "paging:beyond_end",
    "paging:line_out_of_range",
    "paging:has_more",
    "grep:rows",
    "grep:regex_fallback",
    "grep:time_capped",
    "grep:scope_file",
    "grep:scope_missing",
    "glob:dir_marker",
    "glob:excluded_dir",
    "glob:truncated",
    "tool:bad_json",
    "tool:unknown_name",
    "tool:extra_keys",
    "tool:root_escape_dotdot",
    "tool:root_escape_abs",
    "tool:root_escape_symlink",
    "gate:passed",
    "gate:abstain",
    "gate:missing_source",
    "gate:missing_quote",
    "gate:source_not_fetched",
    "gate:quote_not_verbatim",
    "gate:quote_length_short",
    "gate:quote_multiline_escape",
    "stall:duplicate_request",
    "stall:no_new_path_or_span",
    "stall:single_document_type",
    "stall:not_fired",
    "stall:continuation_read",
    "budget:round_cap",
    "budget:length_overflow",
    "tx:error_then_retry_ok",
    "tx:error_twice",
    "tx:bad_response_shape",
}

LOOKUP_TAGS = {
    "pc:native_grounded",
    "pc:native_ungrounded",
    "b3:not_cap",
    "b3:no_draft",
    "b3:conflicting_drafts",
    "b3:compound_answer",
    "b3:nonce_ungrounded",
    "b3:landed",
    "b3:duplicate_key_json",
    "fin:accepted",
    "fin:unparseable",
    "fin:empty_nonce",
    "fin:nonce_ungrounded",
    "fin:reads_only_payloads",
    "c:early_gate_fired",
    "c:retrieve_0",
    "c:retrieve_1",
    "c:retrieve_2",
    "c:already_read_excluded",
    "c:strict_nonce_not_exact_token",
    "c:strict_answer_is_nonce_shaped",
    "c:reset_finalize_accept",
    "c:rescue_after_natural_nonland",
    "ra:bare_digits",
    "ra:unique_digit_token",
    "ra:ambiguous",
    "ra:no_digit",
    "rb:all_identifiers",
    "rb:non_identifier",
    "rb:empty",
}


def test_explore_fixture_floor_and_branch_coverage() -> None:
    fixtures = load_fixtures()
    covered = {tag for case in fixtures for tag in case.get("branch_tags", [])}
    assert len(fixtures) >= 30
    assert EXPLORE_TAGS <= covered


def test_fixture_floor_and_lookup_branch_coverage() -> None:
    explore = load_fixtures()
    lookup = [
        *load_fixtures("lookup-pc"),
        *load_fixtures("lookup-c"),
        *load_fixtures("rules"),
    ]
    covered = {tag for case in lookup for tag in case.get("branch_tags", [])}

    assert len(explore) + len(lookup) >= 48
    assert LOOKUP_TAGS <= covered

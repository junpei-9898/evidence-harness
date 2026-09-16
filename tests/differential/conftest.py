from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

FIXTURE_BASE = Path(__file__).parent / "fixtures"
FIXTURE_ROOT = FIXTURE_BASE / "explore-v4"


def load_fixtures(profile: str = "explore-v4") -> list[dict[str, Any]]:
    fixtures = []
    for path in sorted((FIXTURE_BASE / profile).glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"fixture must be an object: {path.name}")
        fixtures.append(value)
    return fixtures


def payload_sha256(payload: Mapping[str, Any]) -> str:
    comparable = {key: value for key, value in payload.items() if key != "task_id"}
    encoded = json.dumps(
        comparable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def result_sha256(result: Mapping[str, Any]) -> str:
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def decisions(result: Mapping[str, Any]) -> dict[str, Any]:
    tool_results = [
        result_sha256(execution["result"])
        for round_record in result.get("rounds", [])
        for execution in round_record.get("executions", [])
    ]
    stalls = [
        {"fired": row.get("fired"), "reasons": row.get("reasons")}
        for row in result.get("stall_judgments", [])
    ]
    gate = result.get("gate", {})
    return {
        "tool_result_sha256": tool_results,
        "stall_judgments": stalls,
        "gate_reason": gate.get("reason"),
        "gate_quote_length_ok": gate.get("quote_length_ok"),
    }


def lookup_decisions(result: Mapping[str, Any], *, profile: str) -> dict[str, Any]:
    """Select only the preregistered lookup decision columns."""
    selected = {
        key: result.get(key)
        for key in (
            "landing_source",
            "b3_reason",
            "harness_rejected",
            "reject_reason",
            "extra_calls",
            "model_calls",
            "answer",
            "nonce",
        )
    }
    if selected["harness_rejected"]:
        selected["answer"] = None
        selected["nonce"] = None
    if profile != "lookup-c":
        return selected
    selected.update(
        gate_fired=result.get("gate_fired"),
        checkpoint=result.get("checkpoint"),
        strict_reject_reason=result.get("strict_reject_reason"),
        retrieval_arguments=_retrieval_arguments(result),
    )
    return selected


def _retrieval_arguments(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = []
    for record in result.get("rounds", []):
        for execution in record.get("executions", []):
            if not execution.get("harness_action"):
                continue
            raw = execution.get("arguments")
            arguments = json.loads(raw) if isinstance(raw, str) else raw
            calls.append({"name": execution.get("name"), "arguments": arguments})
    return calls


def assert_lookup_branch_observed(
    case: Mapping[str, Any], result: Mapping[str, Any], transport: ScriptedTransport
) -> None:
    """Check fixture tags against observable lookup trace fields."""
    tags = set(case.get("branch_tags", []))
    decision = lookup_decisions(result, profile=str(case["profile"]))
    b3_reasons = {
        "not_cap",
        "no_draft",
        "conflicting_drafts",
        "compound_answer",
        "nonce_ungrounded",
    }
    if "pc:native_grounded" in tags:
        assert decision["landing_source"] == "native" and decision["nonce"] == "nonce-real"
    if "pc:native_ungrounded" in tags:
        assert decision["landing_source"] == "native" and decision["nonce"] == "nonce-fake"
    for reason in b3_reasons:
        if f"b3:{reason}" in tags:
            assert decision["b3_reason"] == reason
    if "b3:landed" in tags:
        assert decision["landing_source"] == "b3"
    if "b3:duplicate_key_json" in tags:
        assert decision["b3_reason"] == "no_draft"
    finalizer_reasons = {
        "unparseable": "unparseable_final_answer",
        "empty_nonce": "empty_nonce",
        "nonce_ungrounded": "nonce_ungrounded",
    }
    if "fin:accepted" in tags:
        assert decision["landing_source"] == "finalizer"
    for tag_reason, result_reason in finalizer_reasons.items():
        if f"fin:{tag_reason}" in tags:
            assert decision["harness_rejected"] is True
            assert decision["reject_reason"] == result_reason
    if "fin:reads_only_payloads" in tags:
        final_request = transport.payloads[-1]
        assert "tools" not in final_request
        assert final_request["messages"][-1]["content"].endswith(
            "Evidence collected (path: content):\n"
        )
    if "c:early_gate_fired" in tags:
        assert decision["gate_fired"] is True
    retrievals = decision.get("retrieval_arguments", [])
    for count in (0, 1, 2):
        if f"c:retrieve_{count}" in tags:
            assert sum(call["name"] == "read_file" for call in retrievals) == count
    if "c:already_read_excluded" in tags:
        paths = [
            call["arguments"].get("path")
            for call in retrievals
            if call["name"] == "read_file"
        ]
        assert "docs/already.txt" not in paths
    if "c:strict_nonce_not_exact_token" in tags:
        assert decision["strict_reject_reason"] == "nonce_not_exact_token"
    if "c:strict_answer_is_nonce_shaped" in tags:
        assert decision["strict_reject_reason"] == "answer_is_nonce_shaped"
    if "c:reset_finalize_accept" in tags:
        assert decision["landing_source"] == "finalizer" and decision["gate_fired"] is True
    if "c:rescue_after_natural_nonland" in tags:
        assert decision["landing_source"] == "finalizer_rescue"


def assert_rules_branch_observed(
    case: Mapping[str, Any], result: Mapping[str, Any]
) -> None:
    tags = set(case.get("branch_tags", []))
    extract_reasons = {
        "ra:bare_digits": "bare_digits",
        "ra:unique_digit_token": "unique_digit_token",
        "ra:ambiguous": "ambiguous_digit_tokens",
        "ra:no_digit": "no_digit_token",
    }
    type_reasons = {
        "rb:all_identifiers": "all_tokens_identifiers",
        "rb:non_identifier": "has_non_identifier_token",
        "rb:empty": "empty",
    }
    for tag, reason in extract_reasons.items():
        if tag in tags:
            assert result.get("extract_reason") == reason
    for tag, reason in type_reasons.items():
        if tag in tags:
            assert result.get("type_reason") == reason


def assert_branch_observed(case: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    """Check that fixture tags describe branches actually present in the trace."""
    tags = set(case.get("branch_tags", []))
    results = [
        execution["result"]
        for record in result.get("rounds", [])
        for execution in record.get("executions", [])
    ]
    first = results[0] if results else {}
    gate = result.get("gate", {})
    reasons = {
        reason
        for judgment in result.get("stall_judgments", [])
        for reason in judgment.get("reasons", [])
    }
    if "paging:offset" in tags:
        assert first.get("start") == 0
    if "paging:line" in tags:
        assert first.get("line") == 2 and first.get("start_line") == 2
    if "paging:both_given" in tags:
        assert first.get("wellformed") is False
    if "paging:max_chars_boundary" in tags:
        assert len(first.get("content", "")) == 8_000
    if "paging:beyond_end" in tags:
        assert first.get("grounded") is True and first.get("empty") is True
    if "paging:line_out_of_range" in tags:
        assert first.get("line_out_of_range") is True
    if "paging:has_more" in tags:
        assert first.get("has_more") is True
    if "grep:rows" in tags:
        assert first.get("rows")
    if "grep:regex_fallback" in tags:
        assert first.get("regex_fallback") is True
    if "grep:time_capped" in tags:
        assert first.get("time_capped") is True
    if "grep:scope_file" in tags:
        assert first.get("scope") == "docs/alpha.txt"
    if "grep:scope_missing" in tags:
        assert first.get("empty") is True and first.get("scanned_files") == 0
    if "glob:dir_marker" in tags:
        assert first.get("hits") and all(not hit.endswith("/") for hit in first["hits"])
    if "glob:excluded_dir" in tags:
        assert all("node_modules" not in hit for hit in first.get("hits", []))
    if "glob:truncated" in tags:
        assert first.get("truncated") is True and first.get("total_hits", 0) > 0
    if tags & {"tool:bad_json", "tool:unknown_name", "tool:extra_keys"}:
        assert first.get("wellformed") is False
    if tags & {"tool:root_escape_dotdot", "tool:root_escape_abs"}:
        assert first.get("wellformed") is False and first.get("grounded") is False
    if "tool:root_escape_symlink" in tags:
        assert first.get("grounded") is False and first.get("empty") is True
    for reason in (
        "passed",
        "abstain",
        "missing_source",
        "missing_quote",
        "source_not_fetched",
        "quote_not_verbatim",
    ):
        if f"gate:{reason}" in tags:
            assert gate.get("reason") == reason
    if "gate:quote_length_short" in tags:
        assert gate.get("quote_length_ok") is False
    if "gate:quote_multiline_escape" in tags:
        assert gate.get("reason") == "passed" and "\\n" in gate.get("quote", "")
    for reason in ("duplicate_request", "no_new_path_or_span", "single_document_type"):
        if f"stall:{reason}" in tags:
            assert reason in reasons
    if "stall:not_fired" in tags:
        assert any(row.get("fired") is False for row in result.get("stall_judgments", []))
    if "stall:continuation_read" in tags:
        assert len(results) >= 2 and results[1].get("start") == 20
    if "budget:round_cap" in tags:
        assert result.get("round_cap") is True and len(result.get("rounds", [])) == 6
    if "budget:length_overflow" in tags:
        assert result.get("finish_reason_length") is True


def _relative_path(raw: str) -> Path:
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe fixture path: {raw}")
    return Path(*candidate.parts)


def materialize_workdir(fixture: Mapping[str, Any], tmp_path: Path) -> Path:
    root = tmp_path / "snapshot"
    root.mkdir()
    workdir = fixture.get("workdir", {})
    files = workdir.get("files", {}) if isinstance(workdir, Mapping) else {}
    if not isinstance(files, Mapping):
        raise ValueError("workdir.files must be an object")
    for raw_path, content in files.items():
        target = root / _relative_path(str(raw_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
    symlinks = workdir.get("symlinks", {}) if isinstance(workdir, Mapping) else {}
    if not isinstance(symlinks, Mapping):
        raise ValueError("workdir.symlinks must be an object")
    for raw_path, content in symlinks.items():
        outside = tmp_path / ("outside-" + Path(str(raw_path)).name)
        outside.write_text(str(content), encoding="utf-8")
        link = root / _relative_path(str(raw_path))
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside)
    return root


class ScriptedTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = json.loads(
            json.dumps(copy.deepcopy(responses), ensure_ascii=False).replace(
                "$ABS_PATH", "/__fixture_outside__"
            )
        )
        self.index = 0
        self.request_sha256: list[str] = []
        self.payloads: list[dict[str, Any]] = []

    def __call__(
        self, url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        del url, headers, timeout
        self.request_sha256.append(payload_sha256(payload))
        self.payloads.append(copy.deepcopy(payload))
        if self.index >= len(self.responses):
            raise AssertionError("scripted transport response exhausted")
        item = self.responses[self.index]
        self.index += 1
        error = item.get("raise")
        if error == "TimeoutError":
            raise TimeoutError("synthetic timeout")
        if error == "ConnectionError":
            raise ConnectionError("synthetic connection failure")
        response = item.get("response", item)
        if not isinstance(response, dict):
            raise TypeError("scripted response must be an object")
        return response


class _ConstantClock:
    def __init__(self, value: float) -> None:
        self.value = value

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        del seconds


class _CappedClock(_ConstantClock):
    def __init__(self) -> None:
        super().__init__(0.0)
        self.calls = 0

    def monotonic(self) -> float:
        self.calls += 1
        return 0.0 if self.calls <= 2 else 11.0


def install_deterministic_clocks(
    monkeypatch: pytest.MonkeyPatch, fixture: Mapping[str, Any]
) -> None:
    from evidence_harness.instruments import usage
    from evidence_harness.profiles import explore
    from evidence_harness.tools import base, exclusions, v4

    mode = fixture.get("config", {}).get("clock")
    monkeypatch.setattr(explore, "time", _ConstantClock(100.0))
    monkeypatch.setattr(usage, "time", _ConstantClock(100.0))
    monkeypatch.setattr(base, "time", _ConstantClock(11.0 if mode == "time_capped" else 100.0))
    monkeypatch.setattr(
        exclusions, "time", _ConstantClock(11.0 if mode == "time_capped" else 100.0)
    )
    monkeypatch.setattr(
        v4, "time", _CappedClock() if mode == "time_capped" else _ConstantClock(100.0)
    )


@pytest.fixture(scope="session")
def explore_fixtures() -> list[dict[str, Any]]:
    return load_fixtures()

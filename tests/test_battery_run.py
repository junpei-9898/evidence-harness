from __future__ import annotations

import json
from pathlib import Path

import pytest

from battery import run as battery_run


def test_cli_appends_each_item_and_resume_skips_completed(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "results.jsonl"
    calls: list[str] = []

    def fake_lookup(question, root, **options):
        calls.append(question)
        return {"answer": None, "nonce": None, "rounds": []}

    monkeypatch.setattr(battery_run, "run_lookup", fake_lookup)
    arguments = [
        "--base-url",
        "http://model.invalid/v1",
        "--model",
        "synthetic-model",
        "--profile",
        "lookup-pc",
        "--set",
        "lookup",
        "--seed",
        "0",
        "--n",
        "2",
        "--out",
        str(output),
    ]

    assert battery_run.main(arguments) == 0
    first_lines = output.read_text(encoding="utf-8").splitlines()
    assert len(first_lines) == 2
    assert len(calls) == 2
    assert all("gold" not in json.loads(line) for line in first_lines)

    assert battery_run.main([*arguments, "--resume"]) == 0
    assert output.read_text(encoding="utf-8").splitlines() == first_lines
    assert len(calls) == 2


def test_supplied_cli_runs_a_then_b_before_saving(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "supplied.jsonl"
    observed: list[str] = []

    def fake_lookup(question, root, **options):
        content = (Path(root) / "evidence/authoritative.txt").read_text(encoding="utf-8")
        observed.append(content)
        return {"answer": None, "nonce": None, "rounds": []}

    monkeypatch.setattr(battery_run, "run_lookup_c", fake_lookup)

    status = battery_run.main([
        "--base-url", "http://model.invalid/v1",
        "--model", "synthetic-model",
        "--profile", "lookup-c",
        "--set", "supplied",
        "--n", "1",
        "--out", str(output),
    ])

    record = json.loads(output.read_text(encoding="utf-8"))
    assert status == 0
    assert len(observed) == 2
    assert observed[0] != observed[1]
    assert set(record["results"]) == {"A", "B"}


def test_cli_rejects_incompatible_profile_and_set(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        battery_run.main([
            "--base-url", "http://model.invalid/v1",
            "--model", "synthetic-model",
            "--profile", "lookup-pc",
            "--set", "explore",
            "--out", str(tmp_path / "results.jsonl"),
        ])

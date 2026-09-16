from __future__ import annotations

import json
from pathlib import Path

from evidence_harness import cli


def test_explore_command_dispatches_and_writes_result(
    tmp_path: Path, monkeypatch
) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
    output = tmp_path / "result.json"
    captured = {}

    def run(question, root, **options):
        captured.update(question=question, root=root, options=options)
        return {"ok": True, "final_content": "synthetic answer"}

    monkeypatch.setattr(cli, "run_explore", run)
    status = cli.main(
        [
            "explore",
            "--base-url",
            "http://model.invalid/v1",
            "--model",
            "synthetic-model",
            "--workdir",
            str(workdir),
            "--question",
            "synthetic question",
            "--max-tokens",
            "321",
            "--out",
            str(output),
        ]
    )

    assert status == 0
    assert captured == {
        "question": "synthetic question",
        "root": workdir,
        "options": {
            "model": "synthetic-model",
            "base_url": "http://model.invalid/v1",
            "max_tokens": 321,
        },
    }
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "ok": True,
        "final_content": "synthetic answer",
    }


def test_lookup_command_uses_yaml_defaults(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
    captured = {}

    def run(question, root, **options):
        captured.update(question=question, root=root, options=options)
        return {"answer": "42", "nonce": "nonce-synth", "rounds": []}

    monkeypatch.setattr(cli, "run_lookup", run)
    status = cli.main(
        [
            "lookup",
            "--base-url",
            "http://model.invalid/v1",
            "--model",
            "synthetic-model",
            "--workdir",
            str(workdir),
            "--question",
            "synthetic question",
        ]
    )

    assert status == 0
    assert captured == {
        "question": "synthetic question",
        "root": workdir,
        "options": {
            "model": "synthetic-model",
            "base_url": "http://model.invalid/v1",
            "max_rounds": 6,
            "max_tokens": 4096,
            "sampling": {"temperature": 0.7},
        },
    }


def test_lookup_c_rules_are_explicit_and_rewrite_shipped_answer(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
    captured = {}

    def run(question, root, **options):
        captured.update(question=question, root=root, options=options)
        return {
            "answer": "value=42",
            "nonce": "nonce-synth",
            "rounds": [],
        }

    monkeypatch.setattr(cli, "run_lookup_c", run)
    status = cli.main(
        [
            "lookup",
            "--base-url",
            "http://model.invalid/v1",
            "--model",
            "synthetic-model",
            "--workdir",
            str(workdir),
            "--question",
            "synthetic question",
            "--profile",
            "lookup-c",
            "--rules",
        ]
    )

    assert status == 0
    assert captured["options"] == {
        "model": "synthetic-model",
        "base_url": "http://model.invalid/v1",
        "max_rounds": 6,
        "max_tokens": 4096,
        "sampling": {"temperature": 0.7},
    }
    result = json.loads(capsys.readouterr().out)
    assert result["answer"] == "42"
    assert result["rules"]["extract_reason"] == "unique_digit_token"

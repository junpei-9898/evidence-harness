from __future__ import annotations

import json
from pathlib import Path

import pytest

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
            "citation_contract": "v1",
            "api_key": None,
        },
    }
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "ok": True,
        "final_content": "synthetic answer",
        "profile": {
            "profile": "explore-v4",
            "tools": "v4",
            "dir_marker": False,
            "max_rounds": 6,
            "max_tokens": 16384,
            "temperature": 0,
            "stall_check": "observe",
            "citation_gate": True,
            "citation_contract": "v1",
        },
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
            "chat_template_kwargs": {"enable_thinking": True},
            "api_key": None,
            "value_contract": "none",
            "selective_ra": False,
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
        "chat_template_kwargs": {"enable_thinking": True},
        "api_key": None,
        "value_contract": "none",
        "selective_ra": False,
    }
    result = json.loads(capsys.readouterr().out)
    assert result["answer"] == "42"
    assert result["rules"]["extract_reason"] == "unique_digit_token"


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            {
                "chat_template_kwargs": {"thinking_mode": "synthetic"},
                "enable_thinking": False,
            },
            {"thinking_mode": "synthetic"},
        ),
        ({"enable_thinking": False}, {"enable_thinking": False}),
        ({}, None),
    ],
)
def test_profile_chat_template_kwargs_maps_each_yaml_branch(config, expected) -> None:
    assert cli._profile_chat_template_kwargs(config) == expected


@pytest.mark.parametrize(
    ("argument", "expected"),
    [
        ('{"thinking_mode":"override"}', {"thinking_mode": "override"}),
        ("none", None),
    ],
)
def test_lookup_chat_template_cli_value_overrides_profile(
    tmp_path: Path, monkeypatch, argument: str, expected: object
) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
    captured = {}

    monkeypatch.setattr(
        cli,
        "_profile_config",
        lambda _name: {
            "max_rounds": 6,
            "max_tokens": 4096,
            "temperature": 0.7,
            "chat_template_kwargs": {"thinking_mode": "profile"},
        },
    )

    def run(_question, _root, **options):
        captured.update(options)
        return {"answer": None, "rounds": []}

    monkeypatch.setattr(cli, "run_lookup", run)
    cli.main(
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
            "--chat-template-kwargs",
            argument,
        ]
    )

    assert captured["chat_template_kwargs"] == expected


def test_commands_resolve_explicit_and_environment_api_keys(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
    captured = []

    def run(_question, _root, **options):
        captured.append(options["api_key"])
        return {"ok": True, "rounds": []}

    monkeypatch.setattr(cli, "run_explore", run)
    monkeypatch.setattr(cli, "run_lookup", run)
    monkeypatch.setenv("EVIDENCE_HARNESS_API_KEY", "environment-key")
    common = [
        "--base-url",
        "http://model.invalid/v1",
        "--model",
        "synthetic-model",
        "--workdir",
        str(workdir),
        "--question",
        "synthetic question",
    ]

    cli.main(["explore", *common])
    cli.main(["lookup", *common, "--api-key", "explicit-key"])

    assert captured == ["environment-key", "explicit-key"]


@pytest.mark.parametrize(
    ("command", "name", "expected"),
    [
        (
            "lookup",
            "qwen38-flash",
            {
                "profile": "qwen38-flash",
                "checkpoint_profile": "qwen38-flash",
                "base_profile": "lookup-c",
                "c_layer": True,
                "value_contract": "digits-only",
                "selective_ra": True,
                "citation_contract": "v2",
                "rules": False,
            },
        ),
        (
            "explore",
            "qwen38-flash",
            {
                "profile": "qwen38-flash",
                "checkpoint_profile": "qwen38-flash",
                "base_profile": "explore-v4",
                "value_contract": "digits-only",
                "selective_ra": True,
                "citation_contract": "v2",
                "rules": False,
            },
        ),
        (
            "lookup",
            "qwen36-base",
            {
                "profile": "qwen36-base",
                "checkpoint_profile": "qwen36-base",
                "base_profile": "lookup-pc",
                "c_layer": False,
                "value_contract": "none",
                "selective_ra": False,
                "citation_contract": "v1",
                "rules": False,
            },
        ),
        (
            "lookup",
            "qwen36-mercor",
            {
                "profile": "qwen36-mercor",
                "checkpoint_profile": "qwen36-mercor",
                "base_profile": "lookup-pc",
                "c_layer": False,
                "value_contract": "none",
                "selective_ra": False,
                "citation_contract": "v1",
                "rules": False,
            },
        ),
    ],
)
def test_resolve_profile_checkpoint_profiles(
    command: str, name: str, expected: dict
) -> None:
    resolved = cli.resolve_profile(command, name)
    for key, value in expected.items():
        assert resolved[key] == value


def test_resolve_profile_rejects_wrong_subcommand() -> None:
    with pytest.raises(ValueError):
        cli.resolve_profile("lookup", "explore-v4")
    with pytest.raises(ValueError):
        cli.resolve_profile("explore", "lookup-pc")


def test_lookup_command_rejects_explore_profile(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
    monkeypatch.setattr(cli, "run_lookup", lambda *a, **k: {"answer": None, "rounds": []})

    with pytest.raises(SystemExit):
        cli.main(
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
                "explore-v4",
            ]
        )


def test_lookup_override_flags_take_precedence_over_checkpoint_profile(
    tmp_path: Path, monkeypatch
) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
    captured = {}

    def run(question, root, **options):
        captured.update(options)
        return {"answer": None, "rounds": []}

    monkeypatch.setattr(cli, "run_lookup_c", run)
    cli.main(
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
            "qwen38-flash",
            "--no-selective-ra",
            "--value-contract",
            "none",
        ]
    )

    assert captured["selective_ra"] is False
    assert captured["value_contract"] == "none"


def test_lookup_dry_run_prints_resolved_profile_and_system(
    tmp_path: Path, capsys
) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
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
            "qwen38-flash",
            "--dry-run",
        ]
    )

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"]["profile"] == "qwen38-flash"
    assert payload["profile"]["value_contract"] == "digits-only"
    assert payload["profile"]["selective_ra"] is True
    assert "system" in payload and payload["system"]


def test_explore_dry_run_prints_resolved_profile_and_system(
    tmp_path: Path, capsys
) -> None:
    workdir = tmp_path / "snapshot"
    workdir.mkdir()
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
            "--profile",
            "qwen38-flash",
            "--dry-run",
        ]
    )

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"]["profile"] == "qwen38-flash"
    assert payload["profile"]["citation_contract"] == "v2"
    assert "system" in payload and payload["system"]

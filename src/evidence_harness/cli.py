"""Command-line interface for evidence-harness profiles."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from evidence_harness.profiles.explore import run_explore
from evidence_harness.profiles.lookup import run_lookup
from evidence_harness.profiles.lookup_c import run_lookup_c
from evidence_harness.rules.deterministic import complete

PROFILE_ROOTS = (
    Path(__file__).resolve().parents[2] / "profiles",
    Path(__file__).resolve().parents[1] / "profiles",
)


def _profile_config(name: str) -> dict[str, Any]:
    path = next(
        (root / f"{name}.yaml" for root in PROFILE_ROOTS if (root / f"{name}.yaml").is_file()),
        None,
    )
    if path is None:
        raise FileNotFoundError("profile directory is unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"profile must be a mapping: {name}")
    parent = value.get("extends")
    if not isinstance(parent, str):
        return value
    return {**_profile_config(parent), **value}


def _pack_paths(rounds: Sequence[Mapping[str, Any]]) -> list[str]:
    paths: list[str] = []
    for record in rounds:
        for execution in record.get("executions") or []:
            if not isinstance(execution, Mapping) or execution.get("name") != "read_file":
                continue
            result = execution.get("result")
            path = result.get("path") if isinstance(result, Mapping) else None
            if isinstance(path, str):
                paths.append(path)
    return paths


def _parse_chat_template_kwargs(value: str) -> Mapping[str, Any] | None:
    if value.lower() == "none":
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError("must be a JSON object or none") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("must be a JSON object or none")
    return parsed


def _profile_chat_template_kwargs(config: Mapping[str, Any]) -> Mapping[str, Any] | None:
    configured = config.get("chat_template_kwargs")
    if isinstance(configured, Mapping):
        return dict(configured)
    enabled = config.get("enable_thinking")
    if isinstance(enabled, bool):
        return {"enable_thinking": enabled}
    return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    explore = subparsers.add_parser("explore", help="run the explore-v4 profile")
    explore.add_argument("--base-url", required=True)
    explore.add_argument("--model", required=True)
    explore.add_argument("--workdir", type=Path, required=True)
    explore.add_argument("--question", required=True)
    explore.add_argument("--max-tokens", type=int, default=16_384)
    explore.add_argument("--api-key")
    explore.add_argument("--out", type=Path)
    lookup = subparsers.add_parser("lookup", help="run a lookup profile")
    lookup.add_argument("--base-url", required=True)
    lookup.add_argument("--model", required=True)
    lookup.add_argument("--workdir", type=Path, required=True)
    lookup.add_argument("--question", required=True)
    lookup.add_argument("--profile", choices=("lookup-pc", "lookup-c"), default="lookup-pc")
    lookup.add_argument("--rules", action="store_true")
    lookup.add_argument("--api-key")
    lookup.add_argument(
        "--chat-template-kwargs",
        type=_parse_chat_template_kwargs,
        default=argparse.SUPPRESS,
    )
    lookup.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    api_key = args.api_key or os.environ.get("EVIDENCE_HARNESS_API_KEY")
    if args.command == "explore":
        result = run_explore(
            args.question,
            args.workdir,
            model=args.model,
            base_url=args.base_url,
            max_tokens=args.max_tokens,
            api_key=api_key,
        )
    elif args.command == "lookup":
        config = _profile_config(args.profile)
        runner = run_lookup_c if args.profile == "lookup-c" else run_lookup
        chat_template_kwargs = getattr(
            args,
            "chat_template_kwargs",
            _profile_chat_template_kwargs(config),
        )
        result = runner(
            args.question,
            args.workdir,
            model=args.model,
            base_url=args.base_url,
            max_rounds=int(config["max_rounds"]),
            max_tokens=int(config["max_tokens"]),
            sampling={"temperature": config["temperature"]},
            chat_template_kwargs=chat_template_kwargs,
            api_key=api_key,
        )
        if args.rules:
            rule_result = complete(
                result.get("answer"),
                result.get("rounds") or [],
                _pack_paths(result.get("rounds") or []),
            )
            result["rules"] = rule_result
            result["answer"] = rule_result["answer"]
    else:
        raise AssertionError(f"unsupported command: {args.command}")
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out is not None:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

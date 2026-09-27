"""Command-line interface for evidence-harness profiles."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from evidence_harness.profiles import explore as explore_profile
from evidence_harness.profiles.explore import run_explore
from evidence_harness.profiles.lookup import _value_contract_system, run_lookup
from evidence_harness.profiles.lookup_c import run_lookup_c
from evidence_harness.rules.deterministic import complete

PROFILE_ROOTS = (
    Path(__file__).resolve().parents[2] / "profiles",
    Path(__file__).resolve().parents[1] / "profiles",
)

# Keys a checkpoint profile may use to override the base profile it resolves to.
_CHECKPOINT_OVERRIDE_KEYS = (
    "value_contract",
    "selective_ra",
    "citation_contract",
    "c_layer",
    "rules",
)


def _profile_path(name: str) -> Path:
    path = next(
        (root / f"{name}.yaml" for root in PROFILE_ROOTS if (root / f"{name}.yaml").is_file()),
        None,
    )
    if path is None:
        raise FileNotFoundError("profile directory is unavailable")
    return path


def _available_profile_names() -> list[str]:
    names: set[str] = set()
    for root in PROFILE_ROOTS:
        if root.is_dir():
            names.update(path.stem for path in root.glob("*.yaml"))
    return sorted(names)


def _raw_profile_yaml(name: str) -> dict[str, Any]:
    value = yaml.safe_load(_profile_path(name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"profile must be a mapping: {name}")
    return value


def _profile_config(name: str) -> dict[str, Any]:
    value = _raw_profile_yaml(name)
    parent = value.get("extends")
    if not isinstance(parent, str):
        return value
    return {**_profile_config(parent), **value}


def _is_checkpoint_profile(raw: Mapping[str, Any]) -> bool:
    return "lookup" in raw or "explore" in raw


def resolve_profile(command: str, name: str) -> dict[str, Any]:
    """Resolve ``name`` for ``command`` ("lookup" or "explore").

    Base profiles (whose own ``profile:`` field starts with the command name)
    resolve through the existing ``extends`` chain. Checkpoint profiles instead
    declare a ``lookup``/``explore`` base profile name per subcommand plus a
    small set of override keys, which take precedence over the resolved base
    profile's values.
    """
    raw = _raw_profile_yaml(name)
    if _is_checkpoint_profile(raw):
        base_name = raw.get(command)
        if not isinstance(base_name, str):
            raise ValueError(f"checkpoint profile {name!r} has no {command!r} base profile")
        resolved = dict(_profile_config(base_name))
        for key in _CHECKPOINT_OVERRIDE_KEYS:
            if key in raw:
                resolved[key] = raw[key]
        resolved["profile"] = name
        resolved["checkpoint_profile"] = name
        resolved["base_profile"] = base_name
        return resolved

    expected_prefix = "lookup" if command == "lookup" else "explore"
    profile_field = raw.get("profile")
    if not isinstance(profile_field, str) or not profile_field.startswith(expected_prefix):
        raise ValueError(f"profile {name!r} is not valid for the {command!r} command")
    return _profile_config(name)


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


def _dry_run_payload(command: str, resolved: Mapping[str, Any]) -> dict[str, Any]:
    if command == "lookup":
        system = _value_contract_system(str(resolved.get("value_contract", "none")))
    else:
        system = explore_profile.SYSTEM + "\n" + explore_profile.ANSWER_FORMAT
    return {"profile": resolved, "system": system}


def _parser() -> argparse.ArgumentParser:
    profile_choices = _available_profile_names()
    parser = argparse.ArgumentParser(prog="evidence-harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    explore = subparsers.add_parser("explore", help="run the explore-v4 profile")
    explore.add_argument("--base-url", required=True)
    explore.add_argument("--model", required=True)
    explore.add_argument("--workdir", type=Path, required=True)
    explore.add_argument("--question", required=True)
    explore.add_argument("--max-tokens", type=int, default=16_384)
    explore.add_argument("--profile", choices=profile_choices, default="explore-v4")
    explore.add_argument(
        "--citation-contract", choices=("v1", "v2"), default=argparse.SUPPRESS
    )
    explore.add_argument("--api-key")
    explore.add_argument("--dry-run", action="store_true")
    explore.add_argument("--out", type=Path)

    lookup = subparsers.add_parser("lookup", help="run a lookup profile")
    lookup.add_argument("--base-url", required=True)
    lookup.add_argument("--model", required=True)
    lookup.add_argument("--workdir", type=Path, required=True)
    lookup.add_argument("--question", required=True)
    lookup.add_argument("--profile", choices=profile_choices, default="lookup-pc")
    lookup.add_argument("--rules", action="store_true")
    lookup.add_argument(
        "--value-contract", choices=("none", "digits-only"), default=argparse.SUPPRESS
    )
    lookup.add_argument(
        "--selective-ra",
        action=argparse.BooleanOptionalAction,
        default=argparse.SUPPRESS,
    )
    lookup.add_argument("--api-key")
    lookup.add_argument(
        "--chat-template-kwargs",
        type=_parse_chat_template_kwargs,
        default=argparse.SUPPRESS,
    )
    lookup.add_argument("--dry-run", action="store_true")
    lookup.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    api_key = args.api_key or os.environ.get("EVIDENCE_HARNESS_API_KEY")

    try:
        resolved = resolve_profile(args.command, args.profile)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    if args.command == "explore":
        citation_contract = getattr(
            args, "citation_contract", resolved.get("citation_contract", "v1")
        )
        if args.dry_run:
            payload = _dry_run_payload("explore", resolved)
            print(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", end="")
            return 0
        result = run_explore(
            args.question,
            args.workdir,
            model=args.model,
            base_url=args.base_url,
            max_tokens=args.max_tokens,
            citation_contract=citation_contract,
            api_key=api_key,
        )
        result["profile"] = resolved
    elif args.command == "lookup":
        value_contract = getattr(
            args, "value_contract", resolved.get("value_contract", "none")
        )
        selective_ra = getattr(
            args, "selective_ra", bool(resolved.get("selective_ra", False))
        )
        rules = True if args.rules else bool(resolved.get("rules", False))
        chat_template_kwargs = getattr(
            args, "chat_template_kwargs", _profile_chat_template_kwargs(resolved)
        )
        if args.dry_run:
            payload = _dry_run_payload("lookup", resolved)
            print(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", end="")
            return 0
        runner = run_lookup_c if resolved.get("c_layer") else run_lookup
        result = runner(
            args.question,
            args.workdir,
            model=args.model,
            base_url=args.base_url,
            max_rounds=int(resolved["max_rounds"]),
            max_tokens=int(resolved["max_tokens"]),
            sampling={"temperature": resolved["temperature"]},
            chat_template_kwargs=chat_template_kwargs,
            value_contract=value_contract,
            selective_ra=selective_ra,
            api_key=api_key,
        )
        if rules:
            rule_result = complete(
                result.get("answer"),
                result.get("rounds") or [],
                _pack_paths(result.get("rounds") or []),
            )
            result["rules"] = rule_result
            result["answer"] = rule_result["answer"]
        result["profile"] = resolved
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

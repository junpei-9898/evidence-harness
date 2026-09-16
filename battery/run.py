"""Sequential command-line runner for the public diagnostic battery."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from evidence_harness.profiles.explore import run_explore
from evidence_harness.profiles.lookup import run_lookup
from evidence_harness.profiles.lookup_c import run_lookup_c

from . import controls, explore_repo, lookup_families, supplied_evidence
from .score import score_control, score_explore, score_lookup, score_supplied

LookupRunner = Callable[..., dict[str, Any]]


def _non_negative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m battery.run")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--profile", choices=("lookup-pc", "lookup-c", "explore-v4"), required=True
    )
    parser.add_argument(
        "--set",
        dest="set_name",
        choices=("lookup", "explore", "controls", "supplied"),
        required=True,
    )
    parser.add_argument("--seed", type=_non_negative, default=0)
    parser.add_argument("--n", type=_non_negative, default=8)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    return parser


def _validate_pairing(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.set_name == "explore" and args.profile != "explore-v4":
        parser.error("the explore set requires --profile explore-v4")
    if args.set_name != "explore" and args.profile == "explore-v4":
        parser.error("explore-v4 can only run the explore set")


def _items(set_name: str, seed: int, n: int) -> list[dict[str, Any]]:
    generators = {
        "lookup": lookup_families.generate_items,
        "explore": explore_repo.generate_items,
        "controls": controls.generate_items,
        "supplied": supplied_evidence.generate_items,
    }
    return generators[set_name](seed=seed, n=n)


def _completed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at line {line_number}") from error
        item_id = record.get("id") if isinstance(record, Mapping) else None
        if not isinstance(item_id, str):
            raise ValueError(f"result line {line_number} has no item id")
        completed.add(item_id)
    return completed


def _lookup_runner(profile: str) -> LookupRunner:
    return run_lookup_c if profile == "lookup-c" else run_lookup


def _run_lookup_item(
    item: Mapping[str, Any], *, runner: LookupRunner, base_url: str, model: str
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="evidence-battery-") as directory:
        root = lookup_families.materialize(item, directory)
        return runner(item["question"], root, model=model, base_url=base_url)


def _run_supplied_item(
    item: Mapping[str, Any], *, runner: LookupRunner, base_url: str, model: str
) -> dict[str, dict[str, Any]]:
    variants = item.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("supplied-evidence item has no variants")
    results: dict[str, dict[str, Any]] = {}
    for label in ("A", "B"):
        variant = variants.get(label)
        if not isinstance(variant, Mapping):
            raise ValueError(f"supplied-evidence item has no variant {label}")
        with tempfile.TemporaryDirectory(prefix="evidence-battery-") as directory:
            root = lookup_families.materialize(variant, directory)
            results[label] = runner(
                item["question"], root, model=model, base_url=base_url
            )
    return results


def _run_one(item: Mapping[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    metadata = {
        "id": item["id"],
        "set": args.set_name,
        "family": item["family"],
        "seed": item["seed"],
        "profile": args.profile,
    }
    if args.set_name == "explore":
        with tempfile.TemporaryDirectory(prefix="evidence-battery-") as directory:
            root = lookup_families.materialize(item, directory)
            result = run_explore(
                item["question"], root, model=args.model, base_url=args.base_url
            )
        return {**metadata, "result": result, "score": score_explore(item, result)}

    runner = _lookup_runner(args.profile)
    if args.set_name == "supplied":
        results = _run_supplied_item(
            item, runner=runner, base_url=args.base_url, model=args.model
        )
        return {**metadata, "results": results, "score": score_supplied(item, results)}

    result = _run_lookup_item(
        item, runner=runner, base_url=args.base_url, model=args.model
    )
    scorer = score_control if args.set_name == "controls" else score_lookup
    return {**metadata, "result": result, "score": scorer(item, result)}


def _append(path: Path, record: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _validate_pairing(parser, args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    completed = _completed_ids(args.out) if args.resume else set()
    if not args.resume:
        args.out.write_text("", encoding="utf-8")
    for item in _items(args.set_name, args.seed, args.n):
        if item["id"] in completed:
            continue
        _append(args.out, _run_one(item, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Public adapters for six deterministic lookup lineage families."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from ._lookup_item import base as _base
from ._lookup_item import evidence as _evidence
from ._lookup_item import finish as _finish
from ._lookup_item import token as _token

FAMILIES = (
    "alias_resolution",
    "priority_chain",
    "index_routing",
    "filtered_sum",
    "single_lookup",
    "two_file_join",
)


def _alias_resolution(seed: int) -> dict[str, Any]:
    rng, lineage_id, nonce, slot = _base("alias_resolution", seed)
    alias = _token(rng, "alias", 4)
    files = {
        "routing/aliases.txt": _evidence(f"public={alias}", lineage_id, 1),
        f"routing/targets/{alias}.txt": _evidence(
            f"ceiling={slot}\nnonce={nonce}", lineage_id, 2
        ),
        "routing/targets/deprecated.txt": "ceiling=333\n",
    }
    return _finish(
        "alias_resolution",
        seed,
        lineage_id,
        nonce,
        slot,
        "Resolve the public alias and report the target ceiling.",
        files,
    )


def _priority_chain(seed: int) -> dict[str, Any]:
    _, lineage_id, nonce, slot = _base("priority_chain", seed)
    files = {
        "policy/order.md": _evidence(
            "Priority order: emergency, region, global. Choose the first present value.",
            lineage_id,
            1,
        ),
        "values/region.ini": _evidence(f"limit={slot}\nnonce={nonce}", lineage_id, 2),
        "values/global.ini": "limit=20\n",
    }
    return _finish(
        "priority_chain",
        seed,
        lineage_id,
        nonce,
        slot,
        "Apply the declared priority order when emergency is absent.",
        files,
    )


def _index_routing(seed: int) -> dict[str, Any]:
    rng, lineage_id, nonce, slot = _base("index_routing", seed)
    shard = _token(rng, "shard", 4)
    files = {
        "index/routes.json": _evidence(f'{{"selected": "{shard}"}}', lineage_id, 1),
        f"shards/{shard}/record.txt": _evidence(
            f"score={slot}\nnonce={nonce}", lineage_id, 2
        ),
        "shards/demo/record.txt": "score=404\n",
    }
    return _finish(
        "index_routing",
        seed,
        lineage_id,
        nonce,
        slot,
        "Route through the selected index shard and report its score.",
        files,
    )


def _filtered_sum(seed: int) -> dict[str, Any]:
    _, lineage_id, nonce, _ = _base("filtered_sum", seed)
    values = [seed % 17 + 10, seed % 13 + 20, seed % 11 + 30]
    answer = str(sum(values))
    rows = [*(f"include,{value}" for value in values), "test,500", "revoked,700"]
    files = {
        "ledger/rule.txt": _evidence(
            "Sum rows tagged include; exclude test and revoked rows.", lineage_id, 1
        ),
        "ledger/rows.csv": _evidence(
            "\n".join([*rows, f"nonce,{nonce}"]), lineage_id, 2
        ),
    }
    return _finish(
        "filtered_sum",
        seed,
        lineage_id,
        nonce,
        answer,
        "Use the ledger rule to compute the included total.",
        files,
    )


def _single_lookup(seed: int) -> dict[str, Any]:
    rng, lineage_id, nonce, slot = _base("single_lookup", seed)
    files = {
        f"records/{_token(rng, 'target', 5)}.txt": _evidence(
            f"active allocation={slot}\nverification nonce={nonce}", lineage_id, 1
        ),
        "records/archive.txt": "retired allocation=777\n",
    }
    return _finish(
        "single_lookup",
        seed,
        lineage_id,
        nonce,
        slot,
        "Find the active allocation in records.",
        files,
    )


def _two_file_join(seed: int) -> dict[str, Any]:
    rng, lineage_id, nonce, slot = _base("two_file_join", seed)
    key = _token(rng, "svc", 5)
    files = {
        "catalog/services.csv": _evidence(f"blue,{key}\ngreen,other", lineage_id, 1),
        "config/allocations.ini": _evidence(
            f"{key}={slot}\nother=555\nnonce={nonce}", lineage_id, 2
        ),
        "notes/example.ini": "example=999\n",
    }
    return _finish(
        "two_file_join",
        seed,
        lineage_id,
        nonce,
        slot,
        "Resolve blue through the service catalog and allocation config.",
        files,
    )


_GENERATORS: dict[str, Callable[[int], dict[str, Any]]] = {
    "alias_resolution": _alias_resolution,
    "priority_chain": _priority_chain,
    "index_routing": _index_routing,
    "filtered_sum": _filtered_sum,
    "single_lookup": _single_lookup,
    "two_file_join": _two_file_join,
}


def generate_lineage(family: str, seed: int) -> dict[str, Any]:
    """Generate one public lookup item without clock or filesystem state."""
    if family not in _GENERATORS:
        raise ValueError(f"unknown family: {family}")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    return _GENERATORS[family](seed)


def generate_items(seed: int = 0, n: int = 8) -> list[dict[str, Any]]:
    if seed < 0 or n < 0:
        raise ValueError("seed and n must be non-negative")
    return [
        generate_lineage(FAMILIES[index % len(FAMILIES)], seed + index // len(FAMILIES))
        for index in range(n)
    ]


def materialize(item: Mapping[str, Any], workdir: Path | str) -> Path:
    """Write only an item's declared files, never its gold metadata."""
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    files = item.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("item files must be a mapping")
    for raw_path, content in files.items():
        path = PurePosixPath(str(raw_path))
        if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
            raise ValueError(f"unsafe item path: {raw_path}")
        if not isinstance(content, str):
            raise ValueError(f"item content must be text: {raw_path}")
        destination = root.joinpath(*path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return root

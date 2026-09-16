"""Deterministic negative and boundary controls for lookup profiles."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from typing import Any

FAMILIES = ("no_evidence", "confusing_source", "name_answer")


def _token(rng: random.Random, prefix: str, width: int = 8) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return prefix + "-" + "".join(rng.choice(alphabet) for _ in range(width))


def _base(family: str, seed: int) -> tuple[random.Random, str, str]:
    rng = random.Random(f"public-controls-v1:{family}:{seed}")
    item_id = hashlib.sha256(f"control:{family}:{seed}".encode()).hexdigest()[:20]
    return rng, item_id, _token(rng, "nonce", 14)


def _no_evidence(seed: int) -> dict[str, Any]:
    rng, item_id, _ = _base("no_evidence", seed)
    key = _token(rng, "harbor")
    return {
        "id": item_id,
        "family": "no_evidence",
        "seed": seed,
        "files": {
            "docs/overview.md": "# 架空運用概要\n\nこの文書は保守窓口の分類だけを説明する。\n",
            "config/status.yaml": "mode: synthetic\nactive: true\n",
        },
        "question": (
            f"識別子 {key} の確定帯域値を答えてください。"
            " Return exactly one JSON object with string fields answer and nonce, or abstain."
        ),
        "gold": {"answer": None, "nonce": None, "abstain": True},
    }


def _confusing_source(seed: int) -> dict[str, Any]:
    rng, item_id, nonce = _base("confusing_source", seed)
    answer = str(rng.randrange(2_000, 9_000))
    stale = str(int(answer) + 137)
    key = _token(rng, "zone")
    return {
        "id": item_id,
        "family": "confusing_source",
        "seed": seed,
        "files": {
            "policy/authority.md": (
                "# 権威設定\n\nこの文書が現在値の唯一の権威である。\n"
                f"{key} の確定割当={answer}\nverification nonce={nonce}\n"
            ),
            "README.md": (
                "# 古い導入例\n\nこの例は現行設定ではない。\n"
                f"{key} の旧割当={stale}\n"
            ),
        },
        "question": (
            f"権威文書に基づく {key} の確定割当を答えてください。"
            " Return exactly one JSON object with string fields answer and nonce."
        ),
        "gold": {"answer": answer, "nonce": nonce, "source": "policy/authority.md"},
    }


def _name_answer(seed: int) -> dict[str, Any]:
    rng, item_id, nonce = _base("name_answer", seed)
    answer = _token(rng, "service", 7)
    alias = _token(rng, "public", 5)
    return {
        "id": item_id,
        "family": "name_answer",
        "seed": seed,
        "files": {
            "registry/aliases.ini": f"{alias}={answer}\n",
            f"services/{answer}.ini": (
                f"service_name={answer}\nverification_nonce={nonce}\n"
            ),
            "registry/examples.ini": "alias=example\nservice_name=service-retired\n",
        },
        "question": (
            f"公開 alias {alias} に対応する service_name を答えてください。"
            " Return exactly one JSON object with string fields answer and nonce."
        ),
        "gold": {
            "answer": answer,
            "nonce": nonce,
            "rules_expected_nonlanding": True,
        },
    }


_GENERATORS: dict[str, Callable[[int], dict[str, Any]]] = {
    "no_evidence": _no_evidence,
    "confusing_source": _confusing_source,
    "name_answer": _name_answer,
}


def generate_control(family: str, seed: int) -> dict[str, Any]:
    if family not in _GENERATORS:
        raise ValueError(f"unknown control family: {family}")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    return _GENERATORS[family](seed)


def generate_items(seed: int = 0, n: int = 8) -> list[dict[str, Any]]:
    if seed < 0 or n < 0:
        raise ValueError("seed and n must be non-negative")
    return [
        generate_control(FAMILIES[index % len(FAMILIES)], seed + index // len(FAMILIES))
        for index in range(n)
    ]

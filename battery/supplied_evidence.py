"""Fresh A/B supplied-evidence diagnostics built only from public type descriptions."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from typing import Any

FAMILIES = ("counter_default", "fictional")
_FICTIONAL_NOUNS = ("velnora", "quendril", "sorvane", "talmyra", "wexorin")
_FICTIONAL_TRAITS = ("amber", "cobalt", "lilac", "silver", "verdant")


def _token(rng: random.Random, prefix: str, width: int = 12) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return prefix + "-" + "".join(rng.choice(alphabet) for _ in range(width))


def _item(
    family: str,
    seed: int,
    question: str,
    nonce: str,
    answers: tuple[str, str],
    contents: tuple[str, str],
    prior: str | None,
) -> dict[str, Any]:
    item_id = hashlib.sha256(f"supplied:{family}:{seed}".encode()).hexdigest()[:20]
    labels = ("A", "B")
    return {
        "id": item_id,
        "family": family,
        "seed": seed,
        "question": question,
        "variants": {
            label: {"files": {"evidence/authoritative.txt": content}}
            for label, content in zip(labels, contents, strict=True)
        },
        "gold": {
            label: {"answer": answer, "nonce": nonce}
            for label, answer in zip(labels, answers, strict=True)
        }
        | {"prior": prior},
    }


def _counter_default(seed: int) -> dict[str, Any]:
    rng = random.Random(f"public-supplied-v1:counter-default:{seed}")
    nonce = _token(rng, "nonce", 14)
    first = str(rng.randrange(20_000, 40_000))
    second = str(rng.randrange(40_001, 60_000))
    prior = "8080"
    contents = (
        f"The common example uses port {prior}, but it is not authoritative.\n"
        f"For this snapshot, the authoritative intake port is {first}.\nnonce={nonce}\n",
        f"The common example uses port {prior}, but it is not authoritative.\n"
        f"For this snapshot, the authoritative intake port is {second}.\nnonce={nonce}\n",
    )
    question = (
        "What is the authoritative intake port in the supplied evidence? "
        "Return exactly one JSON object with string fields answer and nonce."
    )
    return _item(
        "counter_default", seed, question, nonce, (first, second), contents, prior
    )


def _fictional(seed: int) -> dict[str, Any]:
    rng = random.Random(f"public-supplied-v1:fictional:{seed}")
    nonce = _token(rng, "nonce", 14)
    noun = _FICTIONAL_NOUNS[rng.randrange(len(_FICTIONAL_NOUNS))]
    first_index = rng.randrange(len(_FICTIONAL_TRAITS))
    second_index = (first_index + rng.randrange(1, len(_FICTIONAL_TRAITS))) % len(
        _FICTIONAL_TRAITS
    )
    first, second = _FICTIONAL_TRAITS[first_index], _FICTIONAL_TRAITS[second_index]
    contents = (
        f"The fictional {noun} has the authoritative phase trait {first}.\nnonce={nonce}\n",
        f"The fictional {noun} has the authoritative phase trait {second}.\nnonce={nonce}\n",
    )
    question = (
        f"What phase trait does the fictional {noun} have in the supplied evidence? "
        "Return exactly one JSON object with string fields answer and nonce."
    )
    return _item("fictional", seed, question, nonce, (first, second), contents, None)


_GENERATORS: dict[str, Callable[[int], dict[str, Any]]] = {
    "counter_default": _counter_default,
    "fictional": _fictional,
}


def generate_item(family: str, seed: int) -> dict[str, Any]:
    if family not in _GENERATORS:
        raise ValueError(f"unknown supplied-evidence family: {family}")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    return _GENERATORS[family](seed)


def generate_items(seed: int = 0, n: int = 8) -> list[dict[str, Any]]:
    if seed < 0 or n < 0:
        raise ValueError("seed and n must be non-negative")
    return [generate_item(FAMILIES[index % len(FAMILIES)], seed + index) for index in range(n)]

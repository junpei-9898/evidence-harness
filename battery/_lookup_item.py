"""Frozen lookup lineage primitives and public-item adaptation."""

from __future__ import annotations

import hashlib
import random
from typing import Any


def token(rng: random.Random, prefix: str, width: int = 10) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return prefix + "-" + "".join(rng.choice(alphabet) for _ in range(width))


def base(family: str, seed: int) -> tuple[random.Random, str, str, str]:
    rng = random.Random(f"landing-factory-v1:{family}:{seed}")
    lineage_id = hashlib.sha256(f"{family}:{seed}".encode()).hexdigest()[:20]
    nonce = token(rng, "nonce", 14)
    slot = str(rng.randrange(1200, 980000))
    return rng, lineage_id, nonce, slot


def evidence(content: str, lineage_id: str, *indexes: int) -> str:
    markers = "\n".join(f"[FACT:fact:{lineage_id}:{index}]" for index in indexes)
    return f"{content}\n{markers}\n"


def finish(
    family: str,
    seed: int,
    lineage_id: str,
    nonce: str,
    answer: str,
    question: str,
    files: dict[str, str],
) -> dict[str, Any]:
    return {
        "id": lineage_id,
        "family": family,
        "seed": seed,
        "files": files,
        "question": question
        + " Return exactly one JSON object with string fields answer and nonce.",
        "gold": {"answer": answer, "nonce": nonce},
    }

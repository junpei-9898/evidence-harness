"""Deterministic synthetic repository generator for explore-v4 diagnostics."""

from __future__ import annotations

import hashlib
import random
from typing import Any

_STEMS = (
    "avelune",
    "brinovar",
    "cyrenth",
    "dovaris",
    "eluneth",
    "fendral",
    "glysora",
    "halvune",
)
_EXTENSIONS = ("md", "py", "yaml")


def _token(rng: random.Random, prefix: str, width: int = 7) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return prefix + "-" + "".join(rng.choice(alphabet) for _ in range(width))


def _filler(seed: int) -> str:
    lines: list[str] = []
    length = 0
    index = 0
    while length <= 8_300:
        line = (
            f"設計メモ {index:04d}: 架空構成 {seed:04d} の境界条件を記録するが、"
            "受入値はここでは定義しない。\n"
        )
        lines.append(line)
        length += len(line)
        index += 1
    return "".join(lines)


def _support_file(stem: str, index: int, extension: str) -> tuple[str, str]:
    if extension == "md":
        path = f"notes/{stem}-{index:02d}.md"
        content = (
            f"# {stem} 検討記録\n\n"
            f"この文書は架空モジュール {index:02d} の背景だけを説明する。\n"
        )
    elif extension == "py":
        path = f"src/{stem}_{index:02d}.py"
        content = (
            f'"""Synthetic module {stem} {index:02d}."""\n\n'
            f'MODULE_TAG = "{stem}-{index:02d}"\n'
        )
    else:
        path = f"config/{stem}-{index:02d}.yaml"
        content = f"module: {stem}-{index:02d}\nenabled: true\n"
    return path, content


def generate_item(seed: int, *, deep: bool) -> dict[str, Any]:
    """Generate one repository with a single authoritative sentence and a distractor."""
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    rng = random.Random(f"public-explore-v1:{seed}:{int(deep)}")
    stem = _STEMS[rng.randrange(len(_STEMS))]
    key = _token(rng, "route")
    accept = _token(rng, "accept", 8)
    distractor = _token(rng, "accept", 8)
    while distractor == accept:
        distractor = _token(rng, "accept", 8)
    sentence = f"権威ある受入仕様では、航路キー {key} の確定受入値は {accept} と定める。"
    target_path = f"requirements/{stem}-acceptance.md"
    target_prefix = _filler(seed) if deep else "# 権威ある受入仕様\n\n"
    target_content = target_prefix + sentence + "\n"
    files = {
        target_path: target_content,
        f"README-{stem}.md": (
            f"# {stem} の旧案\n\n航路キー {key} の参考受入値は {distractor} だった。\n"
        ),
    }
    file_count = rng.randint(10, 40)
    index = 0
    while len(files) < file_count:
        support_stem = _STEMS[(rng.randrange(len(_STEMS)) + index) % len(_STEMS)]
        path, content = _support_file(support_stem, index, _EXTENSIONS[index % 3])
        files.setdefault(path, content)
        index += 1
    item_id = hashlib.sha256(f"explore:{seed}:{int(deep)}".encode()).hexdigest()[:20]
    position = target_content.index(sentence)
    return {
        "id": item_id,
        "family": "deep" if deep else "shallow",
        "seed": seed,
        "files": files,
        "question": f"航路キー {key} について、権威ある受入仕様が定める確定受入値は何ですか。",
        "gold": {
            "answer": accept,
            "sentence": sentence,
            "path": target_path,
            "position": position,
        },
    }


def generate_items(seed: int = 0, n: int = 8) -> list[dict[str, Any]]:
    if seed < 0 or n < 0:
        raise ValueError("seed and n must be non-negative")
    return [generate_item(seed + index, deep=index % 2 == 0) for index in range(n)]

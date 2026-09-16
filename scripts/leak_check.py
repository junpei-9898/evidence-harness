"""Fail-closed leak check: private suite names, absolute paths, e-mails, research-private dirs.

Run from the repository root. Exit 1 on any hit. The identifiers that must never appear are
stored only as sha256 digests of their lowercase form so the denylist itself leaks nothing.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

PLAINTEXT_PATTERNS = (
    re.compile(r"/Users/[A-Za-z0-9_.-]+"),
    re.compile(r"/home/[A-Za-z0-9_.-]+"),
    re.compile(r"\.exocortex\b"),
    re.compile(r"\bWI-\d{3}\b"),
    re.compile(r"\bwi\d{3}_[a-z]"),
    re.compile(r"\bresearch/[a-z_]+/[a-z_0-9]+\.py"),
    re.compile("X-" + "Exo" + "cortex"),
    re.compile("Exo" + "cortex\\b"),
    re.compile(r"\bwi\d{3}_private\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)
# sha256(token.lower()) for identifiers that must never appear (private repositories, clients).
DENYLIST_DIGESTS = frozenset(
    line.strip()
    for line in (Path(__file__).with_name("leak_denylist.sha256")).read_text().splitlines()
    if line.strip() and not line.startswith("#")
)
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")
TEXT_SUFFIXES = {
    ".py", ".md", ".yaml", ".yml", ".json", ".jsonl", ".toml", ".txt", ".cfg", ".ini", ".sh",
}
SELF = Path(__file__).resolve()


def tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True, text=True,
    ).stdout
    return [Path(line) for line in output.splitlines() if line]


def digest(token: str) -> str:
    return hashlib.sha256(token.lower().encode("utf-8")).hexdigest()


def scan(path: Path) -> list[str]:
    if path.suffix not in TEXT_SUFFIXES or path.resolve() == SELF:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in PLAINTEXT_PATTERNS:
            if pattern.search(line):
                hits.append(f"{path}:{number}: plaintext pattern {pattern.pattern!r}")
        for token in TOKEN.findall(line):
            if digest(token) in DENYLIST_DIGESTS:
                hits.append(f"{path}:{number}: denylisted identifier")
    return hits


def main() -> int:
    hits = [hit for path in tracked_files() for hit in scan(path)]
    for hit in hits:
        print(hit)
    print(f"leak_check: {len(hits)} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())

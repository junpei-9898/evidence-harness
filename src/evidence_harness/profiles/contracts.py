"""Value-format contract sentence shared by the lookup profiles.

The contract sentence is appended verbatim to the lookup SYSTEM prompt when a
profile opts into ``value_contract="digits-only"``. The rescue finalizer and
the C-layer reset finalizer reuse the same (already contract-bearing) system
message because they read it from the shared ``state["prefix_messages"]``
rather than rebuilding it, so the contract text only needs to be produced in
one place.
"""

from __future__ import annotations

import hashlib

CONTRACT_VERSION = "value-format-contract-1.0"
CONTRACT_SENTENCE = (
    "The answer field must be a string consisting of ASCII digits only: "
    "no explanation, no units, and no other values. The nonce field contract is unchanged."
)


def contract_sha256() -> str:
    """Return the digest of the frozen contract sentence."""
    return hashlib.sha256(CONTRACT_SENTENCE.encode("utf-8")).hexdigest()


def apply_value_contract(system: str) -> str:
    """Return ``system`` with the contract sentence appended.

    A single space separates the (right-stripped) original text from the sentence.
    """
    return system.rstrip() + " " + CONTRACT_SENTENCE

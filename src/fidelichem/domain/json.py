"""Deterministic JSON encoding used by provenance and audit records."""

from __future__ import annotations

import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Encode *value* with stable ordering and no non-finite numbers."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Encode *value* as canonical UTF-8 JSON bytes."""

    return canonical_json(value).encode("utf-8")


def canonicalize_json_text(value: str) -> str:
    """Parse JSON text and return its canonical representation."""

    def reject_constant(constant: str) -> Any:
        raise ValueError(f"non-finite JSON constant is not allowed: {constant}")

    parsed = json.loads(value, parse_constant=reject_constant)
    return canonical_json(parsed)

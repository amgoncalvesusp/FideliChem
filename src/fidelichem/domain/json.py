"""Deterministic JSON encoding used by provenance and audit records."""

from __future__ import annotations

import json
from typing import Any

from .errors import InvalidJsonError


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
        raise InvalidJsonError(
            f"non-finite JSON constant is not allowed: {constant}"
        )

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise InvalidJsonError(f"duplicate JSON object key: {key}")
            result[key] = item
        return result

    try:
        parsed = json.loads(
            value,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except InvalidJsonError:
        raise
    except (TypeError, ValueError) as exc:
        raise InvalidJsonError("invalid JSON text") from exc
    return canonical_json(parsed)

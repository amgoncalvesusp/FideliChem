import math

import pytest

from fidelichem.domain.errors import InvalidJsonError
from fidelichem.domain.ids import new_id, validate_id
from fidelichem.domain.json import (
    canonical_json,
    canonical_json_bytes,
    canonicalize_json_text,
)


def test_canonical_json_sorts_keys_and_uses_compact_separators() -> None:
    value = {"b": [2, 3], "a": 1}

    assert canonical_json(value) == '{"a":1,"b":[2,3]}'
    assert canonical_json_bytes(value) == b'{"a":1,"b":[2,3]}'


def test_canonical_json_preserves_null_zero_false_and_empty_text() -> None:
    assert canonical_json(
        {"none": None, "zero": 0, "false": False, "empty": ""}
    ) == '{"empty":"","false":false,"none":null,"zero":0}'


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="Out of range float values"):
        canonical_json({"value": value})


def test_canonical_json_rejects_unsupported_values() -> None:
    with pytest.raises(TypeError):
        canonical_json({"value": {1, 2}})


@pytest.mark.parametrize(
    "value",
    [
        '{"key":1,"key":2}',
        '{"outer":{"key":1,"key":2}}',
        '{"outer":{"left":{"key":1,"key":2}}}',
    ],
)
def test_canonicalize_json_text_rejects_duplicate_object_keys(value: str) -> None:
    with pytest.raises(InvalidJsonError, match="duplicate JSON object key"):
        canonicalize_json_text(value)


def test_uuid_factory_returns_distinct_opaque_uuid4_strings() -> None:
    first = new_id()
    second = new_id()

    assert first != second
    assert len(first) == 36
    assert first.count("-") == 4


@pytest.mark.parametrize(
    "value",
    [
        "550E8400-E29B-41D4-A716-446655440000",
        "550e8400e29b41d4a716446655440000",
        "{550e8400-e29b-41d4-a716-446655440000}",
        "urn:uuid:550e8400-e29b-41d4-a716-446655440000",
    ],
)
def test_validate_id_rejects_noncanonical_uuid4_strings(value: str) -> None:
    with pytest.raises(ValueError):
        validate_id(value)

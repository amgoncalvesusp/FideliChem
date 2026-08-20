import math

import pytest

from fidelichem.domain.ids import new_id
from fidelichem.domain.json import canonical_json, canonical_json_bytes


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


def test_uuid_factory_returns_distinct_opaque_uuid4_strings() -> None:
    first = new_id()
    second = new_id()

    assert first != second
    assert len(first) == 36
    assert first.count("-") == 4

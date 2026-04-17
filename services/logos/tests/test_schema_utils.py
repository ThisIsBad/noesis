"""Tests for shared schema validation helpers (Issue #40)."""

from __future__ import annotations

import pytest

from logos.schema_utils import (
    load_json_object,
    require_bool,
    require_dict,
    require_int,
    require_list,
    require_list_of_str,
    require_optional_str,
    require_str,
)


def test_load_json_object_valid_payload() -> None:
    payload = load_json_object('{"a": 1}', "invalid", "object required")
    assert payload == {"a": 1}


def test_load_json_object_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="invalid"):
        load_json_object("{bad json", "invalid", "object required")


def test_load_json_object_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="object required"):
        load_json_object("[]", "invalid", "object required")


def test_required_scalar_helpers_validate_types() -> None:
    assert require_str("x", "err") == "x"
    assert require_optional_str(None, "err") is None
    assert require_optional_str("x", "err") == "x"
    assert require_int(1, "err") == 1
    assert require_bool(True, "err") is True

    with pytest.raises(ValueError, match="err"):
        require_str(1, "err")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="err"):
        require_optional_str(1, "err")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="err"):
        require_int("1", "err")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="err"):
        require_bool("true", "err")  # type: ignore[arg-type]


def test_required_collection_helpers_validate_types() -> None:
    assert require_list([1], "err") == [1]
    assert require_list_of_str(["a", "b"], "err") == ["a", "b"]
    assert require_dict({"a": 1}, "err") == {"a": 1}

    with pytest.raises(ValueError, match="err"):
        require_list("x", "err")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="err"):
        require_list_of_str(["a", 1], "err")  # type: ignore[list-item]
    with pytest.raises(ValueError, match="err"):
        require_dict("x", "err")  # type: ignore[arg-type]

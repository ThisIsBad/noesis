"""Shared schema and JSON validation helpers."""

from __future__ import annotations

import json
from typing import Any


def load_json_object(raw_json: str, invalid_error: str, object_error: str) -> dict[str, object]:
    """Load JSON and require top-level object."""
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(invalid_error) from exc

    if not isinstance(parsed, dict):
        raise ValueError(object_error)

    return {str(key): value for key, value in parsed.items()}


def require_str(value: object, error_message: str) -> str:
    """Require string value and return it."""
    if not isinstance(value, str):
        raise ValueError(error_message)
    return value


def require_optional_str(value: object, error_message: str) -> str | None:
    """Require string-or-null value and return it."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(error_message)
    return value


def require_int(value: object, error_message: str) -> int:
    """Require integer value and return it."""
    if not isinstance(value, int):
        raise ValueError(error_message)
    return value


def require_bool(value: object, error_message: str) -> bool:
    """Require bool value and return it."""
    if not isinstance(value, bool):
        raise ValueError(error_message)
    return value


def require_list(value: object, error_message: str) -> list[Any]:
    """Require list value and return it."""
    if not isinstance(value, list):
        raise ValueError(error_message)
    return value


def require_list_of_str(value: object, error_message: str) -> list[str]:
    """Require list[str] value and return it."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(error_message)
    return value


def require_dict(value: object, error_message: str) -> dict[str, object]:
    """Require dict value and return it with normalized string keys."""
    if not isinstance(value, dict):
        raise ValueError(error_message)
    return {str(key): item for key, item in value.items()}

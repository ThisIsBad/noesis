"""Contract tests for MCP tool schema shape.

These pin the server's declared MCP tool surface so accidental renames,
added/removed parameters, or type-annotation regressions fail a test
rather than shipping to production.

The critical invariant (from PR #49): any parameter whose name ends in
``_json`` must be typed as plain ``str`` (JSON Schema
``{"type": "string"}``), not ``str | None``. FastMCP's
``pre_parse_json`` auto-decodes JSON-looking strings whenever the
declared annotation is not *exactly* ``str``, which silently turns a
serialised ``ProofCertificate`` into a ``dict`` before Pydantic
validation and rejects it as "Input should be a valid string".
"""

from __future__ import annotations

import mneme.mcp_server_http as server

EXPECTED_TOOLS: dict[str, set[str]] = {
    "store_memory": {
        "content",
        "memory_type",
        "confidence",
        "tags",
        "source",
        "certificate_json",
    },
    "retrieve_memory": {"query", "k", "min_confidence"},
    "forget_memory": {"memory_id", "reason"},
    "list_proven_beliefs": set(),
    "consolidate_memories": {"similarity_threshold"},
    "certify_memory": {"memory_id"},
}

JSON_STRING_PARAMS: set[tuple[str, str]] = {
    ("store_memory", "certificate_json"),
}


def _tools() -> dict[str, object]:
    return server.mcp._tool_manager._tools


def test_all_expected_tools_registered() -> None:
    assert set(_tools().keys()) == set(EXPECTED_TOOLS.keys())


def test_each_tool_has_expected_parameters() -> None:
    for name, expected_params in EXPECTED_TOOLS.items():
        tool = _tools()[name]
        actual = set(tool.parameters.get("properties", {}).keys())  # type: ignore[attr-defined]
        assert actual == expected_params, (
            f"{name} parameters drifted: {actual} != {expected_params}"
        )


def test_json_string_params_are_plain_strings() -> None:
    for tool_name, param_name in JSON_STRING_PARAMS:
        tool = _tools()[tool_name]
        schema = tool.parameters["properties"][param_name]  # type: ignore[attr-defined]
        assert schema.get("type") == "string", (
            f"{tool_name}.{param_name} schema={schema}; must be plain "
            f"string to avoid FastMCP pre_parse_json auto-decode (PR #49)."
        )
        assert "anyOf" not in schema, (
            f"{tool_name}.{param_name} uses anyOf — str | None leaks "
            f"through and triggers pre_parse_json."
        )


def test_every_tool_has_a_description() -> None:
    for name, tool in _tools().items():
        assert tool.description, f"{name} has no description/docstring"  # type: ignore[attr-defined]

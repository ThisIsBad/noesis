"""Tests for MCP server wiring (Issue #57)."""

from __future__ import annotations

import subprocess
import sys
from textwrap import dedent
from typing import cast
from pathlib import Path

import anyio
import mcp.types as mcp_types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logos.mcp_server import create_server

ROOT = Path(__file__).resolve().parents[1]
_SRC_CANDIDATE = ROOT / "src"
PKG_ROOT = _SRC_CANDIDATE if (_SRC_CANDIDATE / "logos").is_dir() else ROOT


def test_create_server_registers_expected_tools() -> None:
    server = create_server()

    async def run() -> list[str]:
        result = await server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest())
        tools_result = cast(mcp_types.ListToolsResult, result.root)
        return [tool.name for tool in tools_result.tools]

    assert anyio.run(run) == [
        "verify_argument",
        "certify_claim",
        "certificate_store",
        "check_assumptions",
        "check_beliefs",
        "counterfactual_branch",
        "z3_check",
        "check_contract",
        "check_policy",
        "z3_session",
        "orchestrate_proof",
        "proof_carrying_action",
    ]


def test_module_import_fails_cleanly_without_mcp_dependency() -> None:
    command = dedent(
        f"""
        import builtins
        import runpy

        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "mcp" or name.startswith("mcp."):
                raise ImportError("blocked for test")
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = fake_import
        runpy.run_path(r"{PKG_ROOT / 'logos' / 'mcp_server.py'}", run_name="logos.mcp_server")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )

    assert result.returncode != 0
    assert "Install with: pip install logic-brain[mcp]" in result.stderr


def test_stdio_server_lists_tools_and_handles_calls() -> None:
    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "logos.mcp_server"],
            cwd=ROOT,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == [
                    "verify_argument",
                    "certify_claim",
                    "certificate_store",
                    "check_assumptions",
                    "check_beliefs",
                    "counterfactual_branch",
                    "z3_check",
                    "check_contract",
                    "check_policy",
                    "z3_session",
                    "orchestrate_proof",
                    "proof_carrying_action",
                ]

                certify_result = await session.call_tool(
                    "certify_claim",
                    {"argument": "P -> Q, P |- Q"},
                )
                structured_certify = cast(dict[str, object], certify_result.structuredContent)
                assert structured_certify["verified"] is True

                store_result = await session.call_tool(
                    "certificate_store",
                    {"action": "stats"},
                )
                structured_store = cast(dict[str, object], store_result.structuredContent)
                assert structured_store["total"] == 0

                verify_result = await session.call_tool(
                    "verify_argument",
                    {"argument": "P -> Q, P |- Q"},
                )
                assert verify_result.isError is False
                structured_verify = cast(dict[str, object], verify_result.structuredContent)
                assert structured_verify["valid"] is True
                assert structured_verify["rule"] == "Modus Ponens"
                assert isinstance(structured_verify["certificate_id"], str)
                assert structured_verify["explanation"]

                error_result = await session.call_tool("z3_check", {"variables": {}, "constraints": ["x > 0"]})
                assert error_result.isError is False
                structured_error = cast(dict[str, object], error_result.structuredContent)
                assert structured_error["error"] == "Invalid input"

                create_result = await session.call_tool(
                    "z3_session",
                    {"action": "create", "session_id": "server-test"},
                )
                assert cast(dict[str, object], create_result.structuredContent)["session_id"] == "server-test"

                await session.call_tool(
                    "z3_session",
                    {
                        "action": "declare",
                        "session_id": "server-test",
                        "variables": {"x": "Int"},
                    },
                )
                await session.call_tool(
                    "z3_session",
                    {
                        "action": "assert",
                        "session_id": "server-test",
                        "constraints": ["x > 0", "x < 10"],
                    },
                )
                check_result = await session.call_tool(
                    "z3_session",
                    {"action": "check", "session_id": "server-test"},
                )
                structured_check = cast(dict[str, object], check_result.structuredContent)
                assert structured_check["satisfiable"] is True
                assert isinstance(structured_check["model"], dict)

                destroy_result = await session.call_tool(
                    "z3_session",
                    {"action": "destroy", "session_id": "server-test"},
                )
                assert cast(dict[str, object], destroy_result.structuredContent)["destroyed"] is True

                orchestration_result = await session.call_tool(
                    "orchestrate_proof",
                    {
                        "action": "create_root",
                        "session_id": "proof-test",
                        "claim_id": "root",
                        "description": "Main claim",
                    },
                )
                structured_orchestration = cast(
                    dict[str, object], orchestration_result.structuredContent
                )
                assert structured_orchestration["status"] == "created"

                bus_result = await session.call_tool(
                    "proof_carrying_action",
                    {
                        "intent": "certify a downstream claim",
                        "action": "certify_claim",
                        "payload": {"argument": "P -> Q, P |- Q"},
                        "expected_postconditions": [{"path": "verified", "equals": True}],
                    },
                )
                structured_bus = cast(dict[str, object], bus_result.structuredContent)
                assert structured_bus["status"] == "completed"

    anyio.run(run)

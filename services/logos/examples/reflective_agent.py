"""Reflective Stage 3 workflow example built from MCP tools.

Direct Python path:
    python examples/reflective_agent.py

MCP stdio path:
    1. Start the server with `python -m logos.mcp_server`
    2. Send the tool payloads returned by `build_stdio_requests()` over the
       stdio JSON-RPC transport used by your MCP client.

The direct run below uses the same payload shapes as the MCP tool surface;
it just calls the handlers from `logos.mcp_tools` directly so the demo
works without a running MCP server.
"""

from __future__ import annotations

import json
from typing import cast

from logos import certify
from logos.mcp_tools import (
    check_assumptions,
    check_contract,
    proof_carrying_action,
    verify_argument,
)


def build_stdio_requests() -> list[dict[str, object]]:
    """Return MCP stdio tool calls equivalent to the direct workflow."""
    return [
        {
            "tool": "verify_argument",
            "arguments": {"argument": "P -> Q, P |- Q"},
        },
        {
            "tool": "check_assumptions",
            "arguments": {
                "assumptions": [
                    {"id": "budget_ok", "statement": "budget <= 100", "kind": "fact"},
                    {"id": "budget_overrun", "statement": "budget > 120", "kind": "hypothesis"},
                ],
                "variables": {"budget": "Int"},
            },
        },
        {
            "tool": "check_contract",
            "arguments": {
                "contract": {
                    "contract_id": "deploy_change",
                    "preconditions": ["budget <= 100", "risk <= 2"],
                },
                "state_constraints": ["budget == 140", "risk == 1"],
                "variables": {"budget": "Int", "risk": "Int"},
            },
        },
        {
            "tool": "proof_carrying_action",
            "arguments": {
                "intent": "publish verified deployment note",
                "action": "certify_claim",
                "payload": {"argument": "P -> Q, P |- Q"},
                "preconditions": ["root-cert"],
                "cert_refs": {"root-cert": certify("P |- P").to_json()},
                "expected_postconditions": [
                    {"path": "verified", "equals": True},
                    {"path": "status", "equals": "certified"},
                ],
                "metadata": {"workflow": "reflective_agent_demo"},
            },
        },
    ]


def run_reflective_demo() -> dict[str, object]:
    """Execute the reflective workflow and return a machine-readable summary."""
    summary: dict[str, object] = {}

    # Stage 3 §4.3 multi-step planning: the agent sequences verification,
    # assumption checks, contract checks, and only then executes an action.
    argument_result = verify_argument({"argument": "P -> Q, P |- Q"})
    summary["verify_argument"] = argument_result

    # Stage 3 §4.3 error self-detection: the agent catches a contradiction in
    # its working assumptions before acting.
    inconsistent_assumptions = {
        "assumptions": [
            {"id": "budget_ok", "statement": "budget <= 100", "kind": "fact"},
            {"id": "budget_overrun", "statement": "budget > 120", "kind": "hypothesis"},
        ],
        "variables": {"budget": "Int"},
    }
    failed_assumption_check = check_assumptions(inconsistent_assumptions)
    summary["failed_assumption_check"] = failed_assumption_check

    # Stage 3 §4.3 replanning after failure: the agent removes the offending
    # hypothesis and retries with a repaired assumption set.
    repaired_assumptions = {
        "assumptions": [
            {"id": "budget_ok", "statement": "budget <= 100", "kind": "fact"},
            {"id": "risk_ok", "statement": "risk <= 2", "kind": "assumption"},
        ],
        "variables": {"budget": "Int", "risk": "Int"},
    }
    repaired_assumption_check = check_assumptions(repaired_assumptions)
    summary["repaired_assumption_check"] = repaired_assumption_check

    # Stage 3 §4.3 error self-detection: the contract gate blocks an unsafe
    # plan before execution and returns diagnostic evidence.
    blocked_contract = check_contract(
        {
            "contract": {
                "contract_id": "deploy_change",
                "preconditions": ["budget <= 100", "risk <= 2"],
            },
            "state_constraints": ["budget == 140", "risk == 1"],
            "variables": {"budget": "Int", "risk": "Int"},
        }
    )
    summary["blocked_contract"] = blocked_contract

    # Stage 3 §4.3 replanning after failure: after diagnosis, the agent picks
    # a lower-cost plan and reruns the contract check.
    active_contract = check_contract(
        {
            "contract": {
                "contract_id": "deploy_change",
                "preconditions": ["budget <= 100", "risk <= 2"],
            },
            "state_constraints": ["budget == 90", "risk == 1"],
            "variables": {"budget": "Int", "risk": "Int"},
        }
    )
    summary["active_contract"] = active_contract

    # Stage 3 §4.3 verification loop: the final action carries a verified
    # certificate and checks postconditions before accepting success.
    action_result = proof_carrying_action(
        {
            "intent": "publish verified deployment note",
            "action": "certify_claim",
            "payload": {"argument": "P -> Q, P |- Q"},
            "preconditions": ["root-cert"],
            "cert_refs": {"root-cert": certify("P |- P").to_json()},
            "expected_postconditions": [
                {"path": "verified", "equals": True},
                {"path": "status", "equals": "certified"},
            ],
            "metadata": {"workflow": "reflective_agent_demo"},
        }
    )
    summary["proof_carrying_action"] = action_result
    return summary


def main() -> None:
    """Run the reflective workflow and print a compact trace."""
    summary = run_reflective_demo()
    verify_step = cast(dict[str, object], summary["verify_argument"])
    failed_assumptions = cast(dict[str, object], summary["failed_assumption_check"])
    repaired_assumptions = cast(dict[str, object], summary["repaired_assumption_check"])
    blocked_contract = cast(dict[str, object], summary["blocked_contract"])
    active_contract = cast(dict[str, object], summary["active_contract"])
    action_step = cast(dict[str, object], summary["proof_carrying_action"])

    print("=" * 60)
    print("LogicBrain Reflective Agent Demo")
    print("=" * 60)

    print("\n-- Step 1: verify_argument --")
    print(f"  valid={verify_step['valid']}")
    print(f"  rule={verify_step['rule']}")

    print("\n-- Step 2: check_assumptions --")
    print(f"  first_pass_consistent={failed_assumptions['consistent']}")
    print(f"  conflict_ids={failed_assumptions['conflict_ids']}")
    print("  diagnosis=remove the contradictory budget hypothesis and retry")
    print(f"  repaired_consistent={repaired_assumptions['consistent']}")

    print("\n-- Step 3: check_contract --")
    print(f"  blocked_status={blocked_contract['status']}")
    print(f"  blocked_unsat_core={blocked_contract['unsat_core']}")
    print("  replanning=lower the proposed budget from 140 to 90")
    print(f"  replanned_status={active_contract['status']}")

    print("\n-- Step 4: proof_carrying_action --")
    print(f"  action_status={action_step['status']}")
    print(f"  accepted={action_step['accepted']}")
    print(f"  proof_bundle_present={action_step['proof_bundle_json'] is not None}")

    print("\n-- MCP stdio parity --")
    print("  Start server: python -m logos.mcp_server")
    print("  Send these tool payloads over stdio JSON-RPC:")
    print(json.dumps(build_stdio_requests(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

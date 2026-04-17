# MCP Setup

This guide explains how to run LogicBrain as an MCP server for AI coding
agents. LogicBrain supports any MCP-compatible client via stdio transport.

Tested clients:

| Client | Version | Config file |
|---|---|---|
| Claude Code | 2.1.42 | `.mcp.json` (project root) |
| OpenCode | 0.0.55 | `.opencode.json` (project root) |
| AntiGravity | 1.107.0 | `~/.gemini/antigravity/mcp_config.json` (user-level) |

## Prerequisites

- Python 3.10+
- LogicBrain checked out locally
- MCP extra installed: `pip install -e ".[mcp]"`

## Quick Start

### 1. Install the MCP extra

```bash
pip install -e ".[mcp]"
```

### 2. Register the server for your client

Pick your client below. All three use stdio transport to communicate with the
same `python -m logic_brain.mcp_server` command.

#### Claude Code

```bash
claude mcp add --scope project -t stdio logic-brain -- python -m logic_brain.mcp_server
```

This writes `.mcp.json` in the project root. Verify with:

```bash
claude mcp list
# Expected: logic-brain: python -m logic_brain.mcp_server - Connected
```

> **Note:** Claude Code reads `.mcp.json`, NOT `.claude/mcp.json`.

#### OpenCode

OpenCode reads the `mcpServers` section from `.opencode.json` in the project
root. This file is already checked in:

```json
{
  "mcpServers": {
    "logic-brain": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "logic_brain.mcp_server"],
      "env": []
    }
  }
}
```

No extra registration step is needed — just start OpenCode in this directory.

#### AntiGravity

AntiGravity stores MCP configuration at the user level, not per-project.

**Option A — CLI:**

```bash
antigravity --add-mcp "{\"name\":\"logic-brain\",\"command\":\"python\",\"args\":[\"-m\",\"logic_brain.mcp_server\"]}"
```

**Option B — manual edit:**

Edit `~/.gemini/antigravity/mcp_config.json` and add the `logic-brain` entry:

```json
{
  "mcpServers": {
    "logic-brain": {
      "command": "python",
      "args": ["-m", "logic_brain.mcp_server"]
    }
  }
}
```

On Windows the full path is:

```
C:\Users\<username>\.gemini\antigravity\mcp_config.json
```

> **Note:** AntiGravity uses a global config, not a project-level file.
> If you have multiple projects, the server will be available in all of them.
> You may need to set the working directory or use an absolute path to the
> Python executable if AntiGravity does not launch the server from the
> project root.

### 3. Restart your client

All three clients discover MCP servers at session startup. After changing
config you must restart the client (or start a new session).

## Configuration Summary

| | Claude Code | OpenCode | AntiGravity |
|---|---|---|---|
| Config file | `.mcp.json` | `.opencode.json` | `~/.gemini/antigravity/mcp_config.json` |
| Scope | project | project | user (global) |
| Checked in | yes | yes | no (user-specific) |
| Registration | `claude mcp add` | automatic | `antigravity --add-mcp` or manual edit |
| `type` field | `"stdio"` | `"stdio"` | not required (stdio is default) |
| `env` field | `{}` (object) | `[]` (array) | `{}` (object) or omit |
| Transport | stdio (newline-delimited JSON-RPC) | stdio | stdio |

## Available Tools

All clients see the same 11 tools once connected:

| Tool | Description |
|---|---|
| `verify_argument` | Verify a propositional logic argument via Z3 |
| `certify_claim` | Create a serializable proof certificate for a claim |
| `check_assumptions` | Check if assumptions are jointly satisfiable |
| `check_beliefs` | Detect contradictions in a belief set |
| `counterfactual_branch` | Evaluate named branches against shared constraints |
| `z3_check` | Run a direct Z3 satisfiability check |
| `check_contract` | Verify goal-contract preconditions against state constraints |
| `check_policy` | Evaluate an action against policy rules |
| `z3_session` | Manage a stateful Z3 session across multiple calls |
| `orchestrate_proof` | Manage a compositional proof tree across MCP calls |
| `proof_carrying_action` | Execute an action envelope with certified preconditions and checked postconditions |

## Tool Reference

### `verify_argument`

- Input:

  ```json
  {"argument": "P -> Q, P |- Q"}
  ```

- Output:

  ```json
  {
    "valid": true,
    "rule": "Modus Ponens",
    "certificate_id": "<stable-id>",
    "explanation": "The conclusion follows from the premises."
  }
  ```

### `certify_claim`

- Input:

  ```json
  {"argument": "P -> Q, P |- Q"}
  ```

- Output:

  ```json
  {
    "verified": true,
    "certificate_json": "{...}",
    "schema_version": "1.0"
  }
  ```

### `check_assumptions`

- Input:

  ```json
  {
    "assumptions": [
      {"id": "a1", "statement": "x > 0", "kind": "assumption"},
      {"id": "a2", "statement": "x < 10", "kind": "fact"}
    ],
    "variables": {"x": "Int"}
  }
  ```

- Output:

  ```json
  {
    "consistent": true,
    "conflict_ids": [],
    "explanation": "All 2 active assumptions are jointly satisfiable."
  }
  ```

### `check_beliefs`

- Input:

  ```json
  {
    "beliefs": [
      {"id": "b1", "statement": "x > 0"},
      {"id": "b2", "statement": "x < 0"}
    ],
    "variables": {"x": "Int"}
  }
  ```

- Output:

  ```json
  {
    "consistent": false,
    "contradiction_ids": ["b1", "b2"]
  }
  ```

### `counterfactual_branch`

- Input:

  ```json
  {
    "variables": {"x": "Int"},
    "base_constraints": ["x > 0"],
    "branches": {
      "safe": ["x < 10"],
      "impossible": ["x < 0"]
    }
  }
  ```

- Output:

  ```json
  {
    "branches": {
      "impossible": {"satisfiable": false, "status": "unsat", "model": null},
      "safe": {"satisfiable": true, "status": "sat", "model": {"x": 1}}
    }
  }
  ```

### `z3_check`

- Input:

  ```json
  {
    "variables": {"x": "Int"},
    "constraints": ["x > 0", "x < 10"]
  }
  ```

- Output:

  ```json
  {
    "satisfiable": true,
    "model": {"x": 1},
    "unsat_core": null
  }
  ```

### `check_contract`

- Input:

  ```json
  {
    "contract": {"contract_id": "ship", "preconditions": ["x > 0"]},
    "state_constraints": ["x == 5"],
    "variables": {"x": "Int"}
  }
  ```

- Output:

  ```json
  {
    "satisfied": true,
    "violations": []
  }
  ```

### `check_policy`

- Input:

  ```json
  {
    "rules": [
      {
        "name": "needs_tests",
        "severity": "error",
        "message": "Add tests before merging",
        "when_true": ["public_api"],
        "when_false": ["has_tests"]
      }
    ],
    "action": {"public_api": true, "has_tests": false}
  }
  ```

- Output:

  ```json
  {
    "decision": "BLOCK",
    "violations": [
      {
        "policy_name": "needs_tests",
        "severity": "error",
        "message": "Add tests before merging",
        "triggered_fields": ["public_api", "has_tests"]
      }
    ],
    "remediation_hints": ["Resolve policy 'needs_tests': Add tests before merging"]
  }
  ```

### `z3_session`

- Create:

  ```json
  {"action": "create", "session_id": "demo"}
  ```

- Declare variables:

  ```json
  {"action": "declare", "session_id": "demo", "variables": {"x": "Int"}}
  ```

- Assert constraints:

  ```json
  {"action": "assert", "session_id": "demo", "constraints": ["x > 0", "x < 10"]}
  ```

- Check satisfiability:

  ```json
  {"action": "check", "session_id": "demo"}
  ```

- Push/pop scope:

  ```json
  {"action": "push", "session_id": "demo"}
  {"action": "pop", "session_id": "demo"}
  ```

- Destroy:

  ```json
  {"action": "destroy", "session_id": "demo"}
  ```

### `orchestrate_proof`

- Create a root claim:

  ```json
  {
    "action": "create_root",
    "session_id": "demo",
    "claim_id": "root",
    "description": "Main claim"
  }
  ```

- Add a sub-claim and composition rule:

  ```json
  {
    "action": "add_sub_claim",
    "session_id": "demo",
    "claim_id": "leaf",
    "parent_id": "root",
    "description": "Leaf claim",
    "composition_rule": "leaf"
  }
  ```

- Verify a leaf or inspect status:

  ```json
  {"action": "verify_leaf", "session_id": "demo", "claim_id": "leaf", "expression": "P |- P"}
  {"action": "status", "session_id": "demo"}
  ```

### `proof_carrying_action`

- Execute an action only if its precondition certificates independently verify:

  ```json
  {
    "intent": "certify a downstream claim",
    "action": "certify_claim",
    "payload": {"argument": "P -> Q, P |- Q"},
    "preconditions": ["root-cert"],
    "cert_refs": {"root-cert": "{...certificate json...}"},
    "expected_postconditions": [{"path": "verified", "equals": true}]
  }
  ```

- Output:

  ```json
  {
    "status": "completed",
    "accepted": true,
    "diagnostics": [],
    "trace": {"intent": "certify a downstream claim", "action": "certify_claim"},
    "proof_bundle_json": "{...}"
  }
  ```

## Error Format

All tools return structured validation/runtime errors instead of uncaught
exceptions:

```json
{
  "error": "Invalid input",
  "details": "Field 'argument' must be a non-empty string"
}
```

## Verifying the Server

### Import check

```bash
python -c "import logic_brain.mcp_server"
```

### Direct start

```bash
python -m logic_brain.mcp_server
```

The server communicates via newline-delimited JSON-RPC over stdio. It will
appear to hang — that is normal (it is waiting for input on stdin).

### Manual stdio test

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | python -m logic_brain.mcp_server
```

You should see a JSON response with `serverInfo.name: "logic-brain"`.

## Troubleshooting

### Server will not start

- Install the optional dependency: `pip install -e ".[mcp]"`
- Verify import: `python -c "import logic_brain.mcp_server"`

### Tools do not show up

| Client | Check |
|---|---|
| Claude Code | Run `claude mcp list`. If empty, run the `claude mcp add` command above. |
| OpenCode | Ensure `.opencode.json` is in the directory where you run `opencode`. |
| AntiGravity | Check `~/.gemini/antigravity/mcp_config.json` contains the server entry. |

Common issues:
- **Wrong config file location:** Each client reads from a different path (see table above)
- **Session restart needed:** MCP servers are discovered at session startup, not hot-reloaded
- **Python not in PATH:** Use an absolute path to the Python executable if needed
- **MCP SDK not installed:** Run `pip install -e ".[mcp]"` and verify with the import check

### Tool call fails with validation error

- Compare your payload to the examples above
- Make sure all required fields are present and spelled exactly
- Check the `error` and `details` fields in the response

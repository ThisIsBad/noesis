# Implementation Brief: v0.7 Proof Orchestrator + MCP Stage 3

**Für:** GPT-5.4 (OpenCode) — Umsetzung
**Von:** Antigravity (Gemini) — Konzeption
**Datum:** 2026-03-20
**Abhängigkeit:** v0.2.0 (aktueller Stand), alle Module aus v0.3–v0.6 sind implementiert

---

## Überblick

Dieses Brief spezifiziert zwei zusammenhängende Erweiterungen:

1. **v0.7 — Proof Orchestrator** (`logic_brain/orchestrator.py`)
   Zerlege komplexe Behauptungen in Sub-Claims, verifiziere unabhängig, komponiere Ergebnisse.

2. **MCP Stage 3 — Neue MCP-Tools**
   Exponiere `certify_claim`, `check_beliefs`, `check_contract` und `orchestrate_proof` als MCP-Endpoints.

---

## Teil 1: Proof Orchestrator

### 1.1 Zweck

Ein Agent, der beweisen will „dieses Refactoring ist korrekt", muss diese Behauptung in Teile zerlegen:
- (A) „Typen bleiben erhalten"
- (B) „Verhalten auf bekannten Inputs bleibt gleich"
- (C) „Keine neuen Exceptions möglich"

Der `ProofOrchestrator` verwaltet diesen Beweisbaum: welche Sub-Claims sind verifiziert, welche offen, welche gescheitert. Wenn der Zerlegung gültig ist UND alle Sub-Claims bewiesen sind, bekommt der Top-Level-Claim ein zusammengesetztes Zertifikat.

### 1.2 Datei

`logic_brain/orchestrator.py`

### 1.3 Datenstrukturen

```python
"""Compositional proof orchestrator for multi-part claims."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from logic_brain.certificate import ProofCertificate, certify, verify_certificate

SCHEMA_VERSION = "1.0"

JSONValue = Any


class ClaimStatus(Enum):
    """Verification status of a claim node."""
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    PARTIAL = "partial"  # some sub-claims verified, some pending


@dataclass
class Claim:
    """A single claim node in the proof tree."""
    claim_id: str
    description: str
    parent_id: str | None = None
    sub_claim_ids: list[str] = field(default_factory=list)
    certificate: ProofCertificate | None = None
    status: ClaimStatus = ClaimStatus.PENDING

    # The logical expression to verify (optional — leaf claims only)
    expression: str | None = None

    # Composition rule: how sub-claims compose into this claim
    # Must be a boolean expression over sub-claim IDs, e.g. "A AND B AND C"
    composition_rule: str | None = None


@dataclass(frozen=True)
class OrchestrationStatus:
    """Overall proof tree status snapshot."""
    total_claims: int
    verified: int
    failed: int
    pending: int
    is_complete: bool  # True iff root is VERIFIED
    root_certificate: ProofCertificate | None
```

### 1.4 Klasse: `ProofOrchestrator`

```python
class ProofOrchestrator:
    """Manage compositional proof trees."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._root_id: str | None = None

    def claim(self, claim_id: str, description: str) -> Claim:
        """Create the root claim. Must be called first, exactly once."""
        ...

    def sub_claim(
        self,
        claim_id: str,
        parent_id: str,
        description: str,
    ) -> Claim:
        """Add a sub-claim under an existing parent claim."""
        ...

    def set_composition(self, claim_id: str, rule: str) -> None:
        """Set how sub-claims compose for a parent claim.

        Rule is a boolean AND/OR expression over sub-claim IDs.
        Example: "types_ok AND behavior_ok AND no_exceptions"
        """
        ...

    def verify_leaf(self, claim_id: str, expression: str) -> ProofCertificate:
        """Verify a leaf claim using LogicBrain's certify().

        Parameters
        ----------
        claim_id : str
            Must be an existing leaf claim (no sub-claims).
        expression : str
            A propositional logic expression to verify via certify().

        Returns
        -------
        ProofCertificate
            The resulting certificate (also stored on the Claim).

        Raises
        ------
        ValueError
            If claim_id is unknown or has sub-claims.
        """
        ...

    def attach_certificate(
        self, claim_id: str, certificate: ProofCertificate
    ) -> None:
        """Attach an externally-produced certificate to a leaf claim.

        Use this when the agent verifies a claim through a method
        other than certify() (e.g. Z3Session, LeanSession) and
        already has a ProofCertificate.
        """
        ...

    def mark_failed(self, claim_id: str, reason: str = "") -> None:
        """Explicitly mark a claim as failed."""
        ...

    def propagate(self) -> None:
        """Re-evaluate all parent claims based on sub-claim states.

        Bottom-up traversal: for each parent, evaluate the
        composition_rule against sub-claim statuses.

        - If all sub-claims referenced in the rule are VERIFIED and
          the composition rule evaluates to True → parent is VERIFIED
        - If any sub-claim is FAILED and the rule cannot be satisfied
          → parent is FAILED
        - Otherwise → parent is PARTIAL
        """
        ...

    def status(self) -> OrchestrationStatus:
        """Return current proof tree status."""
        ...

    def get_claim(self, claim_id: str) -> Claim:
        """Get claim by ID. Raises ValueError if not found."""
        ...

    def pending_claims(self) -> tuple[Claim, ...]:
        """Return all claims that are still PENDING."""
        ...

    def to_dict(self) -> dict[str, JSONValue]:
        """Serialize full proof tree to dictionary."""
        ...

    def to_json(self) -> str:
        """Serialize full proof tree to JSON."""
        ...

    @classmethod
    def from_dict(cls, data: dict[str, JSONValue]) -> "ProofOrchestrator":
        """Deserialize proof tree from dictionary."""
        ...

    @classmethod
    def from_json(cls, raw_json: str) -> "ProofOrchestrator":
        """Deserialize proof tree from JSON string."""
        ...
```

### 1.5 Semantik der Kompositionsregel

Die `composition_rule` ist ein einfacher boolescher Ausdruck über Sub-Claim-IDs:

- `"A AND B AND C"` — alle müssen verifiziert sein
- `"A AND (B OR C)"` — A muss verifiziert sein, plus mindestens B oder C
- Keine Negation (NOT) erlaubt — ein Beweis kann nicht auf dem Scheitern eines Sub-Beweises basieren

**Implementierungshinweis:** Für die Auswertung den bestehenden `logic_brain.parser` NICHT verwenden (der ist für logische Formeln, nicht für Claim-IDs). Stattdessen einen einfachen rekursiven Descent-Parser für `AND`/`OR`/Klammern über Identifier schreiben oder Pythons `ast` Modul für sichere Auswertung nutzen.

### 1.6 Komposition von Zertifikaten

Wenn ein Parent-Claim den Status `VERIFIED` erreicht, wird ein zusammengesetztes Zertifikat erstellt:

```python
# Composed certificate structure
ProofCertificate(
    claim_type="composed",
    claim={
        "root_claim_id": "refactoring_correct",
        "composition_rule": "types_ok AND behavior_ok AND no_exceptions",
        "sub_certificates": [
            sub1.certificate.to_dict(),
            sub2.certificate.to_dict(),
            sub3.certificate.to_dict(),
        ]
    },
    method="composition",
    verified=True,
    timestamp=...,
    verification_artifact={
        "composition_rule": "types_ok AND behavior_ok AND no_exceptions",
        "sub_claim_count": 3,
        "all_sub_verified": True,
    },
)
```

### 1.7 Verifizierung von zusammengesetzten Zertifikaten

`verify_certificate()` in `certificate.py` muss erweitert werden, um den neuen `claim_type="composed"` zu unterstützen:

```python
# In certificate.py, add to verify_certificate():
if certificate.claim_type == "composed":
    if not isinstance(certificate.claim, dict):
        raise ValueError("Composed claim must be an object")
    sub_certs_data = certificate.claim.get("sub_certificates")
    if not isinstance(sub_certs_data, list):
        raise ValueError("Composed claim requires 'sub_certificates' list")
    all_valid = all(
        verify_certificate(ProofCertificate.from_dict(sub))
        for sub in sub_certs_data
        if isinstance(sub, dict)
    )
    return all_valid == certificate.verified
```

### 1.8 Export

In `__init__.py` hinzufügen:

```python
from .orchestrator import (
    Claim,
    ClaimStatus,
    OrchestrationStatus,
    ProofOrchestrator,
)
```

Und in `__all__`:
```python
    # Proof orchestration (Tier 2 / Provisional)
    "ClaimStatus",
    "Claim",
    "OrchestrationStatus",
    "ProofOrchestrator",
```

---

## Teil 2: MCP Stage 3 Tools

### 2.1 Bestehende MCP-Architektur (Referenz)

Pattern in `mcp_server.py`:
- Jedes Tool ist eine `ToolSpec(name, description, input_schema, handler)`
- Handler-Funktion in `mcp_tools.py`: nimmt `Mapping[str, object]` → gibt `ToolResult` zurück
- `ToolResult` = `dict[str, object]` mit mindestens `{"status": str, ...}`
- Registration: Tool wird zum `_TOOLS`-Tupel in `mcp_server.py` hinzugefügt

### 2.2 Neue Tools

#### Tool 1: `certify_claim`

**Zweck:** Agent kann eine logische Behauptung zertifizieren und das Zertifikat erhalten.

**Handler:** `mcp_tools.py` → `def certify_claim(payload: Mapping[str, object]) -> ToolResult`

**Input-Schema:**
```json
{
    "argument": "string — propositional argument string (e.g. 'P -> Q, P |- Q')"
}
```

**Handler-Logik:**
```python
def certify_claim(payload: Mapping[str, object]) -> ToolResult:
    data = _require_payload(payload)
    argument = _require_non_empty_str(data, "argument")
    cert = certify(argument)
    return {
        "status": "certified" if cert.verified else "refuted",
        "verified": cert.verified,
        "method": cert.method,
        "certificate_json": cert.to_json(),
        "certificate_id": _certificate_id(cert.to_json()),
    }
```

**MCP-Registration in `mcp_server.py`:**
```python
_tool(
    "certify_claim",
    "Verify a logical argument and return a serializable proof certificate. "
    "Example: {'argument': 'P -> Q, P |- Q'}",
    {"argument": {"type": "string", "description": "Argument to certify."}},
    ["argument"],
    certify_claim,
),
```

---

#### Tool 2: `check_beliefs`

**Zweck:** Agent kann einen Satz von Beliefs auf Z3-Konsistenz prüfen und Widersprüche identifizieren.

**Handler:** `mcp_tools.py` → `def check_beliefs(payload: Mapping[str, object]) -> ToolResult`

**Input-Schema:**
```json
{
    "beliefs": [
        {"id": "string", "statement": "string"}
    ],
    "variables": {"name": "sort"}  // optional
}
```

**Handler-Logik:**
```python
def check_beliefs(payload: Mapping[str, object]) -> ToolResult:
    data = _require_payload(payload)
    beliefs_raw = _require_list(data, "beliefs")
    variables = _optional_variables(data.get("variables"))

    graph = BeliefGraph()
    for belief_data in beliefs_raw:
        if not isinstance(belief_data, dict):
            raise ValueError("Each belief must be an object")
        belief_id = belief_data.get("id")
        statement = belief_data.get("statement")
        if not isinstance(belief_id, str) or not isinstance(statement, str):
            raise ValueError("Belief requires string fields 'id' and 'statement'")
        graph.add_belief(belief_id=belief_id, statement=statement)

    var_dict: dict[str, str] | None = None
    if variables is not None:
        var_dict = {str(k): str(v) for k, v in variables.items()}

    contradictions = graph.detect_contradictions_z3(variables=var_dict)

    explanations = []
    for left_id, right_id in contradictions:
        expl = graph.explain_contradiction(left_id, right_id)
        explanations.append({
            "left_id": expl.left_id,
            "right_id": expl.right_id,
            "left_support_path": list(expl.left_support_path),
            "right_support_path": list(expl.right_support_path),
        })

    return {
        "status": "consistent" if not contradictions else "contradictions_found",
        "belief_count": len(beliefs_raw),
        "contradiction_count": len(contradictions),
        "contradictions": [
            {"left": l, "right": r} for l, r in contradictions
        ],
        "explanations": explanations,
    }
```

**MCP-Registration:**
```python
_BELIEF_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "statement": {"type": "string"},
    },
    "required": ["id", "statement"],
    "additionalProperties": False,
}

_tool(
    "check_beliefs",
    "Check a set of beliefs for Z3 consistency and identify contradictions. "
    "Example: {'beliefs': [{'id': 'b1', 'statement': 'x > 0'}, "
    "{'id': 'b2', 'statement': 'x < -5'}], 'variables': {'x': 'Int'}}",
    {
        "beliefs": {
            "type": "array",
            "description": "Beliefs to check for consistency.",
            "items": _BELIEF_SCHEMA,
        },
        "variables": {
            "type": "object",
            "description": "Optional Z3 sorts keyed by variable name.",
            "additionalProperties": {"type": "string"},
        },
    },
    ["beliefs"],
    check_beliefs,
),
```

---

#### Tool 3: `check_contract`

**Zweck:** Agent kann einen GoalContract gegen Z3-State-Constraints prüfen.

**Handler:** `mcp_tools.py` → `def check_contract(payload: Mapping[str, object]) -> ToolResult`

**Input-Schema:**
```json
{
    "contract": {
        "contract_id": "string",
        "preconditions": ["string"],
        "invariants": ["string"],
        "completion_criteria": ["string"]
    },
    "state_constraints": ["string"],
    "variables": {"name": "sort"}  // optional
}
```

**Handler-Logik:**
```python
def check_contract(payload: Mapping[str, object]) -> ToolResult:
    data = _require_payload(payload)
    contract_raw = _require_dict(data, "contract")
    state_constraints = _require_str_list(data, "state_constraints")
    variables = _optional_variables(data.get("variables"))

    contract = GoalContract.from_dict(contract_raw)

    var_dict: dict[str, str] | None = None
    if variables is not None:
        var_dict = {str(k): str(v) for k, v in variables.items()}

    result = verify_contract_preconditions_z3(
        contract, state_constraints, variables=var_dict
    )

    return {
        "status": result.status.value,
        "diagnostics": [
            {"code": d.code, "message": d.message}
            for d in result.diagnostics
        ],
    }
```

**MCP-Registration:**
```python
_tool(
    "check_contract",
    "Verify goal contract preconditions against Z3 state constraints. "
    "Example: {'contract': {'contract_id': 'c1', 'preconditions': ['x > 0']}, "
    "'state_constraints': ['x == 5'], 'variables': {'x': 'Int'}}",
    {
        "contract": {
            "type": "object",
            "description": "Goal contract with preconditions, invariants, etc.",
            "properties": {
                "contract_id": {"type": "string"},
                "preconditions": {"type": "array", "items": {"type": "string"}},
                "invariants": {"type": "array", "items": {"type": "string"}},
                "completion_criteria": {"type": "array", "items": {"type": "string"}},
                "abort_criteria": {"type": "array", "items": {"type": "string"}},
                "permitted_strategies": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["contract_id"],
        },
        "state_constraints": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Z3-parseable state constraints.",
        },
        "variables": {
            "type": "object",
            "description": "Optional Z3 sorts keyed by variable name.",
            "additionalProperties": {"type": "string"},
        },
    },
    ["contract", "state_constraints"],
    check_contract,
),
```

---

#### Tool 4: `orchestrate_proof`

**Zweck:** Agent kann einen Beweisbaum verwalten — Claims anlegen, verifizieren, Status abfragen.

**Handler:** `mcp_tools.py` → `def orchestrate_proof(payload: Mapping[str, object]) -> ToolResult`

**Input-Schema:**
```json
{
    "action": "create_root | add_sub_claim | verify_leaf | attach_certificate | mark_failed | propagate | status | get_tree",
    "session_id": "string — stable orchestrator identifier",
    "claim_id": "string",
    "parent_id": "string",
    "description": "string",
    "expression": "string — for verify_leaf action",
    "composition_rule": "string — for set_composition on parent",
    "certificate_json": "string — for attach_certificate action",
    "reason": "string — for mark_failed action"
}
```

**Stateful Pattern:** Benutze dasselbe Session-Store-Pattern wie `z3_session`:

```python
# In mcp_session_store.py, add:
_orchestrator_store: dict[str, ProofOrchestrator] = {}
```

**Handler-Logik (Skelett):**
```python
def orchestrate_proof(payload: Mapping[str, object]) -> ToolResult:
    data = _require_payload(payload)
    action = _require_non_empty_str(data, "action")
    session_id = _require_non_empty_str(data, "session_id")

    if action == "create_root":
        claim_id = _require_non_empty_str(data, "claim_id")
        description = _require_non_empty_str(data, "description")
        orch = ProofOrchestrator()
        orch.claim(claim_id, description)
        _orchestrator_store[session_id] = orch
        return {"status": "created", "session_id": session_id, "root_claim_id": claim_id}

    orch = _orchestrator_store.get(session_id)
    if orch is None:
        raise ValueError(f"Unknown orchestrator session '{session_id}'")

    if action == "add_sub_claim":
        claim_id = _require_non_empty_str(data, "claim_id")
        parent_id = _require_non_empty_str(data, "parent_id")
        description = _require_non_empty_str(data, "description")
        composition_rule = data.get("composition_rule")
        orch.sub_claim(claim_id, parent_id, description)
        if isinstance(composition_rule, str) and composition_rule:
            orch.set_composition(parent_id, composition_rule)
        return {"status": "added", "claim_id": claim_id, "parent_id": parent_id}

    if action == "verify_leaf":
        claim_id = _require_non_empty_str(data, "claim_id")
        expression = _require_non_empty_str(data, "expression")
        cert = orch.verify_leaf(claim_id, expression)
        return {
            "status": "verified" if cert.verified else "refuted",
            "claim_id": claim_id,
            "verified": cert.verified,
            "certificate_id": _certificate_id(cert.to_json()),
        }

    if action == "attach_certificate":
        claim_id = _require_non_empty_str(data, "claim_id")
        cert_json = _require_non_empty_str(data, "certificate_json")
        cert = ProofCertificate.from_json(cert_json)
        orch.attach_certificate(claim_id, cert)
        return {"status": "attached", "claim_id": claim_id}

    if action == "mark_failed":
        claim_id = _require_non_empty_str(data, "claim_id")
        reason = str(data.get("reason", ""))
        orch.mark_failed(claim_id, reason)
        return {"status": "marked_failed", "claim_id": claim_id}

    if action == "propagate":
        orch.propagate()
        s = orch.status()
        return {
            "status": "propagated",
            "total": s.total_claims,
            "verified": s.verified,
            "failed": s.failed,
            "pending": s.pending,
            "is_complete": s.is_complete,
        }

    if action == "status":
        s = orch.status()
        return {
            "status": "ok",
            "total": s.total_claims,
            "verified": s.verified,
            "failed": s.failed,
            "pending": s.pending,
            "is_complete": s.is_complete,
        }

    if action == "get_tree":
        return {"status": "ok", "tree": orch.to_dict()}

    raise ValueError(f"Unknown orchestrate_proof action '{action}'")
```

**MCP-Registration:**
```python
_ORCHESTRATOR_ACTION_SCHEMA: dict[str, object] = {
    "type": "string",
    "enum": [
        "create_root", "add_sub_claim", "verify_leaf",
        "attach_certificate", "mark_failed", "propagate",
        "status", "get_tree",
    ],
}

_tool(
    "orchestrate_proof",
    "Manage a compositional proof tree. Create claims, verify sub-claims, "
    "propagate results. Example: {'action': 'create_root', "
    "'session_id': 'demo', 'claim_id': 'main', 'description': 'Main claim'}",
    {
        "action": _ORCHESTRATOR_ACTION_SCHEMA,
        "session_id": {"type": "string", "description": "Stable orchestrator session ID."},
        "claim_id": {"type": "string", "description": "Claim identifier."},
        "parent_id": {"type": "string", "description": "Parent claim ID for sub-claims."},
        "description": {"type": "string", "description": "Human-readable claim description."},
        "expression": {"type": "string", "description": "Logical expression to verify (for verify_leaf)."},
        "composition_rule": {"type": "string", "description": "Boolean rule over sub-claim IDs."},
        "certificate_json": {"type": "string", "description": "Serialized ProofCertificate JSON."},
        "reason": {"type": "string", "description": "Failure reason (for mark_failed)."},
    },
    ["action", "session_id"],
    orchestrate_proof,
),
```

---

## Teil 3: Tests

### 3.1 Test-Datei: `tests/test_orchestrator.py`

Mindestens **20 Tests**, aufgeteilt in:

| Kategorie | Tests | Was |
|-----------|-------|-----|
| **Grundoperationen** | 5 | Claim anlegen, Sub-Claims, Duplikate ablehnen, leere IDs ablehnen, Get-Claim |
| **Verifizierung** | 4 | verify_leaf mit gültigem/ungültigem Argument, attach_certificate, mark_failed |
| **Propagation** | 4 | AND-Regel (alle verified → parent verified), OR-Regel, FAILED-Propagation, PARTIAL-Status |
| **Serialisierung** | 3 | to_json/from_json Roundtrip, to_dict/from_dict, leerer Baum |
| **Metamorphic** | 2 | (MR1) Verifizieren eines Sub-Claims invalidiert nie Geschwister; (MR2) Hinzufügen eines verifizierten Sub-Claims ändert nie den Status eines anderen Sub-Claims von VERIFIED zu etwas anderem |
| **Edge Cases** | 2 | Verify_leaf auf Parent-Claim (soll fehlschlagen), Propagation ohne Composition-Rule |

### 3.2 Test-Datei: `tests/test_mcp_certify.py`

Mindestens **5 Tests** für `certify_claim`:

| Test | Was |
|------|-----|
| Gültiges Argument | `certify_claim({"argument": "P -> Q, P \|- Q"})` → verified=True |
| Ungültiges Argument | `certify_claim({"argument": "P -> Q, Q \|- P"})` → verified=False |
| Leeres Argument | → ValueError |
| Zertifikat-Roundtrip | certificate_json ist gültiges JSON, from_json funktioniert |
| certificate_id ist stabil | Gleicher Input → gleiche ID |

### 3.3 Test-Datei: `tests/test_mcp_beliefs.py`

Mindestens **5 Tests** für `check_beliefs`:

| Test | Was |
|------|-----|
| Konsistente Beliefs | `x > 0` und `x < 10` → consistent |
| Widersprüchliche Beliefs | `x > 0` und `x < -5` → contradictions_found |
| Leere Belief-Liste | → consistent, belief_count=0 |
| Ohne Variablen-Deklaration | Auto-Detect greift |
| Erklärung | explanations enthalten korrekte IDs |

### 3.4 Test-Datei: `tests/test_mcp_contract.py`

Mindestens **5 Tests** für `check_contract`:

| Test | Was |
|------|-----|
| Erfüllte Precondition | state=`x == 5`, precondition=`x > 0` → active |
| Nicht-erfüllte Precondition | state=`x == -1`, precondition=`x > 0` → blocked |
| Leere Preconditions | → active |
| Fehlende contract_id | → ValueError |
| Diagnostics enthalten Code | diagnostics-Array hat `code` und `message` Felder |

### 3.5 Test-Datei: `tests/test_mcp_orchestrate.py`

Mindestens **8 Tests** für `orchestrate_proof`:

| Test | Was |
|------|-----|
| create_root + status | Status zeigt 1 total, 0 verified, 1 pending |
| add_sub_claim | Sub-Claim ist pending |
| verify_leaf | Leaf-Status wird verified |
| propagate (alle verified) | Parent wird verified |
| propagate (one failed) | Parent wird failed |
| mark_failed | Claim wird failed |
| get_tree | Gibt serialisierten Baum zurück |
| Unbekannte Session | → ValueError |

### 3.6 Metamorphic Tests (Ledger-Einträge)

In `tests/test_metamorphic.py` (oder dem bestehenden metamorphic-Testfile) hinzufügen:

```python
@pytest.mark.metamorphic
def test_mr_verify_subclaim_does_not_invalidate_siblings():
    """MR: Verifying a sub-claim never changes the status of sibling claims."""
    ...

@pytest.mark.metamorphic
def test_mr_removing_policy_never_adds_violations():
    """MR: Certification of a valid argument always produces verified=True."""
    ...
```

---

## Teil 4: Zusammenfassung der zu erstellenden/ändernden Dateien

| Datei | Aktion | Beschreibung |
|-------|--------|-------------|
| `logic_brain/orchestrator.py` | **NEU** | ProofOrchestrator, Claim, ClaimStatus, OrchestrationStatus |
| `logic_brain/certificate.py` | **ÄNDERN** | `verify_certificate()` um `claim_type="composed"` erweitern |
| `logic_brain/mcp_tools.py` | **ÄNDERN** | 4 neue Handler: certify_claim, check_beliefs, check_contract, orchestrate_proof |
| `logic_brain/mcp_server.py` | **ÄNDERN** | 4 neue ToolSpecs + Schemas in `_TOOLS` |
| `logic_brain/mcp_session_store.py` | **ÄNDERN** | `_orchestrator_store` hinzufügen |
| `logic_brain/__init__.py` | **ÄNDERN** | Exports für orchestrator-Klassen |
| `tests/test_orchestrator.py` | **NEU** | ≥20 Tests |
| `tests/test_mcp_certify.py` | **NEU** | ≥5 Tests |
| `tests/test_mcp_beliefs.py` | **NEU** | ≥5 Tests |
| `tests/test_mcp_contract.py` | **NEU** | ≥5 Tests |
| `tests/test_mcp_orchestrate.py` | **NEU** | ≥8 Tests |
| `docs/metamorphic_ledger.md` | **ÄNDERN** | 2 neue MR-Einträge |

---

## Teil 5: Preflight Gates

Vor dem Commit müssen alle Gates grün sein:

```bash
python -m pytest -q
python -m ruff check logic_brain/ tests/ tools/
python -m mypy --strict logic_brain
python -m pytest --cov=logic_brain --cov-report=term-missing --cov-fail-under=85
python -m pytest -q -m metamorphic
```

---

## Teil 6: Commit

```
git add . && git commit -m "Add ProofOrchestrator and MCP Stage 3 tools (v0.7)

- logic_brain/orchestrator.py: compositional proof tree with claim
  decomposition, verification, propagation, and certificate composition
- certificate.py: verify_certificate() supports composed certificates
- mcp_tools.py: 4 new MCP tools (certify_claim, check_beliefs,
  check_contract, orchestrate_proof)
- mcp_server.py: tool registrations and schemas
- 43+ new tests across 5 test files
- Metamorphic tests for orchestrator invariants" && git push
```

---

## Teil 7: Akzeptanzkriterien

- [ ] `ProofOrchestrator` unterstützt Claim-Bäume mit beliebiger Tiefe
- [ ] AND/OR-Komposition funktioniert korrekt
- [ ] Zusammengesetzte Zertifikate überleben JSON-Roundtrip und Re-Verification
- [ ] Alle 4 MCP-Tools sind über `mcp_server.py` registriert und aufrufbar
- [ ] `certify_claim` gibt ein re-verifizierbares ProofCertificate zurück
- [ ] `check_beliefs` findet Z3-Widersprüche und liefert Erklärungen
- [ ] `check_contract` prüft Preconditions via Z3 Proof-by-Refutation
- [ ] `orchestrate_proof` ist stateful (Session-Store) und unterstützt alle 8 Actions
- [ ] ≥43 neue Tests, alle grün
- [ ] Coverage ≥85%
- [ ] mypy strict clean
- [ ] ruff clean
- [ ] Metamorphic Tests in Ledger registriert

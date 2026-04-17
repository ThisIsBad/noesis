# Logos ↔ Mneme Integration Contract

This document defines how services in the Noesis stack interact with the
Logos verification service. It exists because Mneme (and other
consumers) must agree with Logos on wire formats for
`ProofCertificate` and confidence vocabulary.

## Source of truth

- **`services/logos/src/logos/certificate.py`** owns the canonical
  `ProofCertificate` dataclass and its JSON serialization
  (`to_dict()` / `from_dict()`).
- **`schemas/src/noesis_schemas/certificates.py`** mirrors that shape
  as a Pydantic model. It is a validator, not a producer.
- **`schemas/src/noesis_schemas/confidence.py`** holds the shared
  vocabulary (`ConfidenceLevel`, `RiskLevel`, `EscalationDecision`,
  `ConfidenceRecord`). Logos still keeps its own dataclass versions in
  `uncertainty.py`; both agree on enum values by convention.

A round-trip test in `schemas/tests/test_schemas.py` (`test_logos_certificate_round_trip`)
enforces that `ProofCertificate.model_validate(logos_cert.to_dict())`
succeeds for a real Logos-issued certificate.

## ProofCertificate wire format

```json
{
  "schema_version": "1.0",
  "claim_type": "propositional | fol | z3_session | composed",
  "claim": "<string | object, depending on claim_type>",
  "method": "z3_propositional | z3_fol | z3_session | ...",
  "verified": true,
  "timestamp": "<ISO 8601 UTC>",
  "verification_artifact": { "...": "method-specific payload" }
}
```

- `verified` is the boolean verdict from Z3/Lean. Consumers MUST NOT
  treat `verified=true` as a confidence score — see next section.
- `verification_artifact` contents depend on `method`. It is opaque to
  consumers except Logos itself (which uses it for re-verification).

## Confidence and risk

Mneme uses a float `confidence ∈ [0, 1]` per memory for retrieval
ranking. When interacting with Logos (e.g., calling
`check_policy` or emitting a `ConfidenceRecord`), the float is mapped
to the discrete `ConfidenceLevel` via
`noesis_schemas.confidence.confidence_from_float`:

| `confidence` | `ConfidenceLevel` |
|--------------|-------------------|
| `>= 0.95`    | `CERTAIN`         |
| `>= 0.70`    | `SUPPORTED`       |
| `>  0.30`    | `WEAK`            |
| `else`       | `UNKNOWN`         |

The boundaries are a v1 choice and will move once Episteme provides
real calibration data.

## Belief graduation (Mneme)

The original design doc proposed two ChromaDB collections (verified vs.
probabilistic). After absorbing Logos, Logos itself already provides a
verified belief store via `certificate_store` (`query_ranked` etc.).
This means Mneme has two viable paths:

1. **Flag on a single collection** (`proven: bool`, `certificate_ref`).
   Mneme stores memories; if a `ProofCertificate` is attached,
   `proven=True` is set. Retrieval can filter by `proven` or not.
2. **Mneme delegates to Logos** for verified beliefs — Mneme stores
   only the unverified side, and reads verified beliefs via a
   Logos-client.

The current Mneme code uses option 1 (see `services/mneme/src/mneme/core.py`).
We stay with that for v1 — option 2 becomes interesting once Logos's
`query_ranked` outperforms Mneme's ChromaDB retrieval, which requires
measurement.

## Context-aware verification

The original design proposal described "context-aware verification" as
something Logos should learn. After absorption, it is clear that Logos
already implements the mechanism (not learned, but rule-based):

- `UncertaintyCalibrator.enforce(record, risk_level)` returns
  `PROCEED | REVIEW_REQUIRED | BLOCKED`.
- The rules in `UncertaintyPolicy` can be made configurable per
  caller.

For v1, callers pass `RiskLevel` explicitly. For v2 (after Episteme
provides calibration signal), the policy thresholds become data-driven.

## Feedback loop (future)

Real self-calibration requires:

- **Episteme** logging predicted-vs-actual outcomes per certificate.
- **Telos** monitoring whether decisions based on weak-confidence
  memories drift goals.
- **Praxis** executing actions so we see real consequences.

None of this exists yet. The v1 integration is intentionally
stub-compatible: certificates flow, confidence is recorded, but no
automatic recalibration happens.

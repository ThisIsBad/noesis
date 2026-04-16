# Noesis — Architecture

## Grundprinzip

Noesis ist kein einzelner Service. Es ist ein **Ökosystem unabhängiger MCP-Services**,
die gemeinsam die kognitiven Lücken zwischen LLMs und AGI schließen.

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude (Orchestrator)                   │
└──┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬────────┘
   │      │      │      │      │      │      │      │
   ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼
Logos  Mneme  Praxis Episteme Kosmos Empiria Techne Telos
  │      │      │      │      │      │      │      │
  └──────┴──────┴──────┴──────┴──────┴──────┴──────┘
                        │
               (optional: Logos als
               Verifikations-Backend)
```

## Deployment-Modell

Jeder Service ist ein **eigenständiges Repository** mit:
- Eigenem Railway-Deployment (HTTP, Port 8000)
- Eigenem MCP-Endpoint (`/mcp`)
- Eigenem CI/CD, Changelog, Versioning

**Kein direktes Service-zu-Service-Calling.** Claude ist der einzige Orchestrator.

## Logos als Verifikations-Backend

Logos ist der einzige Service, der von anderen Services direkt aufgerufen
werden darf — aber nur für **read-only, idempotente** Verifikations-Calls.

**Default-Pfad (state-mutating, Claude-orchestriert):**
```
Mneme will eine Belief speichern
  → Claude ruft Logos.certify_claim() auf
  → Claude übergibt ProofCertificate an Mneme.store_memory(proven=True)
```

**Sidecar-Pfad (read-only Verifikation):**
```
Praxis evaluiert 50 Plan-Branches
  → Praxis ruft Logos.z3_check() direkt
  → Verifikations-Ergebnis wird in Praxis-Response an Claude gemeldet
```

**Erlaubte Direct-Calls:** `certify_claim`, `z3_check`, `check_policy`,
`verify_argument`, `check_assumptions`, `check_beliefs`, `check_contract`.

**Verboten direct:** Jede Logos-Operation, die State mutiert
(`assume`, `register_goal`, `counterfactual_branch` mit persistentem
Branch-State). State-Mutationen bleiben Claude-orchestriert.

**Bedingungen:** Authenticated via Railway-internal mTLS oder API-Key,
Trace-ID propagiert (Kairos), Audit-Log mandatory.

## Repository-Struktur

```
ThisIsBad/noesis          ← dieser Hub: Docs, Roadmap, Service-Registry
ThisIsBad/noesis-schemas  ← geteilte Verträge (JSON Schema → Pydantic/Serde) [Prio 0]
ThisIsBad/noesis-eval     ← reproduzierbares Benchmark-Harness [Prio 0]
ThisIsBad/logos           ← Verifikation (Z3/Lean 4) [deployed ✅]
ThisIsBad/mneme           ← Gedächtnis [geplant]
ThisIsBad/praxis          ← Planning [geplant, Rust-Kandidat]
ThisIsBad/telos           ← Ziel-Stabilität [vorgezogen, Rust-Kandidat]
ThisIsBad/episteme        ← Kalibrierung [geplant]
ThisIsBad/kairos          ← Observability/Tracing [geplant]
ThisIsBad/kosmos          ← Kausalität [geplant]
ThisIsBad/empiria         ← Erfahrung [geplant]
ThisIsBad/techne          ← Skills [geplant]
```

**Querschnitts-Komponenten** (`noesis-schemas`, `noesis-eval`, `kairos`)
entstehen parallel zu Phase 1, nicht nachgelagert.

## Service-Template (Python — Default)

Jeder Service folgt demselben Layout:

```
<service>/
├── src/<service>/
│   ├── __init__.py
│   ├── core.py            ← Kern-Logik
│   └── mcp_server_http.py ← FastAPI + MCP endpoint
├── tests/
│   └── test_core.py
├── Dockerfile
├── Procfile               ← web: python -m <service>.mcp_server_http
├── railway.toml
├── pyproject.toml
└── README.md
```

## Polyglot-Option (Rust)

Default ist Python. Rust ist erlaubt für Services, in denen Latenz oder
CPU-bound Algorithmik dominieren — aktuell **Praxis**, **Telos** und ein
möglicher **Logos-Hot-Path-Microservice** (siehe ROADMAP.md → Polyglot).

Bedingung: Service muss `noesis-schemas` konsumieren (Pydantic in Python,
`serde`-generierte Structs in Rust), damit Verträge sprach-übergreifend
identisch bleiben.

```
<service>/
├── src/                   ← Rust source
│   ├── main.rs            ← axum + rmcp
│   └── core.rs
├── tests/
├── Dockerfile             ← multi-stage (cargo build --release → distroless)
├── railway.toml
└── Cargo.toml
```

**Regel:** Sprachwahl folgt gemessenem Bedarf, nicht Vorlieben. Migration
nur bei dokumentiertem Bottleneck.

## Kommunikations-Protokoll

- **Transport:** MCP over HTTP (Streamable HTTP, nicht SSE)
- **Endpoint:** `POST /mcp`
- **Auth:** Railway-interne URLs + optional API-Key Header
- **Format:** JSON-RPC über MCP-Protokoll

## Preflight Gates

**Python-Services:**
```bash
python -m pytest -q
python -m ruff check src/ tests/
python -m mypy --strict src/
python -m pytest --cov=src/<service> --cov-fail-under=85
```

**Rust-Services:**
```bash
cargo test
cargo clippy -- -D warnings
cargo fmt -- --check
cargo llvm-cov --fail-under-lines 85
```

## Cross-Service Integration Gates

Pro Phase mindestens ein End-to-End-Szenario im `noesis-eval` Repo, das
≥ 3 Services touched. Beispiel Phase 1:

```
register_goal (Telos)
  → decompose_goal (Praxis)
  → verify_plan (Logos via Sidecar)
  → commit_step + store_memory (Mneme)
```

Acceptance: alle Service-Latencies innerhalb p99-SLO, Trace lückenlos
in Kairos sichtbar.

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

Logos ist der einzige Service, der von anderen Services optional aufgerufen
werden darf — nicht direkt, sondern via Claude als Vermittler:

```
Mneme will eine Belief speichern
  → Claude ruft Logos.certify_claim() auf
  → Claude übergibt ProofCertificate an Mneme.store_memory(proven=True)
```

## Repository-Struktur

```
ThisIsBad/noesis     ← dieser Hub: Docs, Roadmap, Service-Registry
ThisIsBad/logos      ← Verifikation (Z3/Lean 4) [deployed ✅]
ThisIsBad/mneme      ← Gedächtnis [geplant]
ThisIsBad/praxis     ← Planning [geplant]
ThisIsBad/episteme   ← Kalibrierung [geplant]
ThisIsBad/kosmos     ← Kausalität [geplant]
ThisIsBad/empiria    ← Erfahrung [geplant]
ThisIsBad/techne     ← Skills [geplant]
ThisIsBad/telos      ← Ziel-Stabilität [geplant]
```

## Service-Template

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

## Kommunikations-Protokoll

- **Transport:** MCP over HTTP (Streamable HTTP, nicht SSE)
- **Endpoint:** `POST /mcp`
- **Auth:** Railway-interne URLs + optional API-Key Header
- **Format:** JSON-RPC über MCP-Protokoll

## Preflight Gates (alle Services)

```bash
python -m pytest -q
python -m ruff check src/ tests/
python -m mypy --strict src/
python -m pytest --cov=src/<service> --cov-fail-under=85
```

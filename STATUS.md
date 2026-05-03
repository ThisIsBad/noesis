# Noesis — Component Status

> **Auto-generated** by `tools/generate_status.py`. Do not edit by hand.
> Regenerated on every push to master by `.github/workflows/status.yml`.

This report is filesystem-derived: presence of a Dockerfile, `railway.toml`, an MCP server, a CI workflow, and line-count shape. It does NOT speak to live Railway deploy health or CI pass/fail — those require auth. For authoritative status see the `Deployments` tab on Railway and the `Actions` tab on GitHub.

See [`docs/architect-review-2026-04-23.md`](docs/architect-review-2026-04-23.md) for the most recent architectural read.

## Services

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **hegemonikon** | Interactive recorded chat surface for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/hegemonikon.yml) | 1,214 | 601 | 3 | 2026-05-02 |
| **empiria** | Experience accumulation and lesson extraction for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/empiria.yml) | 241 | 246 | 4 | 2026-05-02 |
| **episteme** | Metacognition and uncertainty calibration for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/episteme.yml) | 341 | 428 | 5 | 2026-05-02 |
| **kosmos** | Causal world model with Do-calculus for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/kosmos.yml) | 206 | 240 | 4 | 2026-05-02 |
| **logos** | LLM x Deterministic Logic Verifier — exploiting the P!=NP asymmetry | ✓ | ✓ | ✓ | [✓](.github/workflows/logos.yml) | 11,756 | 9,978 | 74 | 2026-05-02 |
| **mneme** | Persistent episodic and semantic memory for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/mneme.yml) | 611 | 867 | 6 | 2026-05-02 |
| **praxis** | Hierarchical planning and Tree-of-Thoughts search for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/praxis.yml) | 694 | 860 | 6 | 2026-05-02 |
| **techne** | Verified skill library and strategy reuse for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/techne.yml) | 407 | 407 | 4 | 2026-05-02 |
| **telos** | Goal stability monitoring and drift detection for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/telos.yml) | 395 | 516 | 5 | 2026-05-02 |

## Cross-cutting packages

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **clients** | Shared Python clients for cross-service calls in the Noesis stack | — | — | — | [✓](.github/workflows/clients.yml) | 713 | 749 | 4 | 2026-05-02 |
| **eval** | Reproducible benchmark harness for the Noesis AGI stack | — | — | — | [✓](.github/workflows/eval.yml) | 3,104 | 5,299 | 16 | 2026-05-02 |
| **kairos** | Cross-service observability and tracing for the Noesis AGI stack | — | — | ✓ | [✓](.github/workflows/kairos.yml) | 373 | 474 | 3 | 2026-05-02 |
| **schemas** | Shared data contracts for the Noesis AGI stack | — | — | — | [✓](.github/workflows/schemas.yml) | 340 | 168 | 1 | 2026-05-02 |

## UI clients

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **hegemonikon-ui** | — | — | — | — | — | — | — | — | 2026-05-02 |
| **theoria** | Decision-logic visualization UI for the Noesis ecosystem | ✓ | ✓ | — | [✓](.github/workflows/theoria.yml) | 4,161 | 2,672 | 14 | 2026-05-02 |

## Legend

- **Docker / Railway / pyproject / MCP / CI** — checkmark means the file or workflow exists on disk. Missing markers are real gaps.
- **src LOC / test LOC / tests** — raw line counts (excluding `__pycache__`) and count of `test_*.py` files. Fast health signal, not a substitute for actually running the suite.
- **Last commit** — `git log -1` on the component's directory.

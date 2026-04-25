# Noesis — Component Status

> **Auto-generated** by `tools/generate_status.py`. Do not edit by hand.
> Regenerated on every push to master by `.github/workflows/status.yml`.

This report is filesystem-derived: presence of a Dockerfile, `railway.toml`, an MCP server, a CI workflow, and line-count shape. It does NOT speak to live Railway deploy health or CI pass/fail — those require auth. For authoritative status see the `Deployments` tab on Railway and the `Actions` tab on GitHub.

See [`docs/architect-review-2026-04-23.md`](docs/architect-review-2026-04-23.md) for the most recent architectural read.

## Services

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **empiria** | Experience accumulation and lesson extraction for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/empiria.yml) | 384 | 374 | 4 | 2026-04-25 |
| **episteme** | Metacognition and uncertainty calibration for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/episteme.yml) | 345 | 424 | 5 | 2026-04-24 |
| **kosmos** | Causal world model with Do-calculus for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/kosmos.yml) | 205 | 241 | 4 | 2026-04-24 |
| **logos** | LLM x Deterministic Logic Verifier — exploiting the P!=NP asymmetry | ✓ | ✓ | ✓ | [✓](.github/workflows/logos.yml) | 11,894 | 10,012 | 74 | 2026-04-21 |
| **mneme** | Persistent episodic and semantic memory for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/mneme.yml) | 592 | 809 | 6 | 2026-04-24 |
| **praxis** | Hierarchical planning and Tree-of-Thoughts search for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/praxis.yml) | 683 | 830 | 6 | 2026-04-24 |
| **techne** | Verified skill library and strategy reuse for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/techne.yml) | 406 | 403 | 4 | 2026-04-24 |
| **telos** | Goal stability monitoring and drift detection for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/telos.yml) | 340 | 517 | 5 | 2026-04-24 |

## Cross-cutting packages

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **clients** | Shared Python clients for cross-service calls in the Noesis stack | — | — | — | [✓](.github/workflows/clients.yml) | 724 | 737 | 4 | 2026-04-24 |
| **eval** | Reproducible benchmark harness for the Noesis AGI stack | — | — | — | [✓](.github/workflows/eval.yml) | 3,077 | 4,699 | 15 | 2026-04-24 |
| **kairos** | Cross-service observability and tracing for the Noesis AGI stack | — | — | ✓ | [✓](.github/workflows/kairos.yml) | 374 | 451 | 3 | 2026-04-24 |
| **schemas** | Shared data contracts for the Noesis AGI stack | — | — | — | [✓](.github/workflows/schemas.yml) | 332 | 158 | 1 | 2026-04-24 |

## UI clients

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **theoria** | Decision-logic visualization UI for the Noesis ecosystem | ✓ | ✓ | — | [✓](.github/workflows/theoria.yml) | 4,123 | 2,549 | 14 | 2026-04-24 |

## Legend

- **Docker / Railway / pyproject / MCP / CI** — checkmark means the file or workflow exists on disk. Missing markers are real gaps.
- **src LOC / test LOC / tests** — raw line counts (excluding `__pycache__`) and count of `test_*.py` files. Fast health signal, not a substitute for actually running the suite.
- **Last commit** — `git log -1` on the component's directory.

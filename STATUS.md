# Noesis — Component Status

> **Auto-generated** by `tools/generate_status.py`. Do not edit by hand.
> Last regenerated: 2026-04-23 19:25 UTC

This report is filesystem-derived: presence of a Dockerfile, `railway.toml`, an MCP server, a CI workflow, and line-count shape. It does NOT speak to live Railway deploy health or CI pass/fail — those require auth. For authoritative status see the `Deployments` tab on Railway and the `Actions` tab on GitHub.

See [`docs/architect-review-2026-04-23.md`](docs/architect-review-2026-04-23.md) for the most recent architectural read.

## Services

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **empiria** | Experience accumulation and lesson extraction for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/empiria.yml) | 265 | 221 | 4 | 2026-04-21 260d502 |
| **episteme** | Metacognition and uncertainty calibration for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/episteme.yml) | 368 | 400 | 5 | 2026-04-21 260d502 |
| **kosmos** | Causal world model with Do-calculus for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/kosmos.yml) | 228 | 220 | 4 | 2026-04-21 260d502 |
| **logos** | LLM x Deterministic Logic Verifier — exploiting the P!=NP asymmetry | ✓ | ✓ | ✓ | [✓](.github/workflows/logos.yml) | 11,894 | 10,012 | 74 | 2026-04-21 f82aac1 |
| **mneme** | Persistent episodic and semantic memory for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/mneme.yml) | 592 | 809 | 6 | 2026-04-22 3ece7ce |
| **praxis** | Hierarchical planning and Tree-of-Thoughts search for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/praxis.yml) | 706 | 809 | 6 | 2026-04-23 dfecfe7 |
| **techne** | Verified skill library and strategy reuse for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/techne.yml) | 272 | 259 | 4 | 2026-04-21 260d502 |
| **telos** | Goal stability monitoring and drift detection for the Noesis AGI stack | ✓ | ✓ | ✓ | [✓](.github/workflows/telos.yml) | 363 | 480 | 5 | 2026-04-21 c20f049 |

## Cross-cutting packages

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **clients** | Shared Python clients for cross-service calls in the Noesis stack | — | — | — | [✓](.github/workflows/clients.yml) | 435 | 405 | 2 | 2026-04-23 dfecfe7 |
| **eval** | Reproducible benchmark harness for the Noesis AGI stack | — | — | — | [✓](.github/workflows/eval.yml) | 3,077 | 4,699 | 15 | 2026-04-23 abef2ea |
| **kairos** | Cross-service observability and tracing for the Noesis AGI stack | — | — | ✓ | [✓](.github/workflows/kairos.yml) | 374 | 451 | 3 | 2026-04-21 6c5948e |
| **schemas** | Shared data contracts for the Noesis AGI stack | — | — | — | [✓](.github/workflows/schemas.yml) | 332 | 158 | 1 | 2026-04-23 dfecfe7 |

## UI clients

| Name | Description | Docker | Railway | MCP | CI | src LOC | test LOC | tests | Last commit |
|------|-------------|:------:|:-------:|:---:|:--:|--------:|---------:|------:|-------------|
| **theoria** | Decision-logic visualization UI for the Noesis ecosystem | ✓ | ✓ | — | [✓](.github/workflows/theoria.yml) | 4,123 | 2,549 | 14 | 2026-04-23 2da8746 |

## Legend

- **Docker / Railway / pyproject / MCP / CI** — checkmark means the file or workflow exists on disk. Missing markers are real gaps.
- **src LOC / test LOC / tests** — raw line counts (excluding `__pycache__`) and count of `test_*.py` files. Fast health signal, not a substitute for actually running the suite.
- **Last commit** — `git log -1` on the component's directory.

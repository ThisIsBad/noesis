# Sandbox dev loop

Three nested loops, each cheaper and faster than the next one out.

## Inner loop — single test

```bash
cd <pkg>           # e.g. services/console
pytest -q -k <name>
```

Used while debugging a single failure. Sub-second. Done.

## Outer loop — full local check

```bash
bash scripts/check-local.sh           # full gate
bash scripts/check-local.sh --fast    # skip mypy + cov
bash scripts/check-local.sh --component console
```

Iterates the 14 packages (`schemas`, `kairos`, `clients`, 8 services,
`eval`, `ui/theoria`) running `ruff check`, `ruff format --check`,
`mypy src/`, `pytest+cov`, plus the `STATUS.md` drift check at the end.

This is the **gate before every push**. It mirrors what GH Actions
runs per workflow, but in this Linux sandbox in <60s. If `check-local`
is green and you push, CI on GH should be green too — `check-local`
catches everything CI catches except the platform-specific GH-runner
edge cases.

## Push loop — live-stack end-to-end

```bash
bash scripts/sandbox-smoke.sh
```

Boots the 8-service stack + Console + drives the full HTTP/SSE flow
with a canned prompt, validates the resulting `DecisionTrace` end-to-
end, then tears everything down. Self-contained: no leftover processes,
no leftover ports.

By default runs in **fake-query mode** (`CONSOLE_FAKE_QUERY=1`) — Console
returns the canned scripted iterator from `console._fake_query`,
matching the canonical sequence the in-process test
`eval/tests/test_console_inprocess.py` uses. That keeps the smoke
deterministic and runnable with no Anthropic dependency.

To drive Claude for real (occasional regression check, requires
logged-in `claude` CLI on PATH):

```bash
CONSOLE_USE_REAL_CLAUDE=1 bash scripts/sandbox-smoke.sh
```

## What runs where

| Surface | Where | Frequency |
|---|---|---|
| Inner loop (`pytest -k`) | sandbox | every edit |
| `check-local` | sandbox | every push |
| `sandbox-smoke` (fake) | sandbox | every push |
| `sandbox-smoke` (real) | sandbox or any env with claude CLI | per milestone |
| GH Actions on push | GitHub | automatic, async |
| Browser UI smoke | local browser | when UI changes |

The sandbox is the primary dev surface; GH Actions provide the
asynchronous safety net (catches anything that depends on a clean
runner state). The local browser is only needed when Theoria's
visualization itself changes — the chat surface and the trace JSON
are fully covered by the sandbox loop.

## When the dev loop fails

| Symptom | Likely cause | Fix |
|---|---|---|
| `check-local` red on `mypy` only | new strict-mode error | fix the type, or add a narrow `[[tool.mypy.overrides]]` in that pkg's `pyproject.toml` |
| `check-local` red on `STATUS.md drift` | added/removed file | `python tools/generate_status.py` to regenerate |
| `sandbox-smoke` red at step 2/4 | a service crashed at boot | `tail .run/logs/<svc>.log`; usually missing dep — `bash scripts/bootstrap.sh` |
| `sandbox-smoke` red at step 4/4 with `session.error` | TraceBuilder regression or fake-query mismatch | run `pytest eval/tests/test_console_inprocess.py -x` first; if green, the regression is in HTTP/SSE wiring |
| GH CI red but `check-local` green | runner-specific (often `chromadb` wheel mismatch) | check the failed-step log on GH; usually a version-pin update fixes it |

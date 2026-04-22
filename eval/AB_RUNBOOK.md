# Running the canonical A/B

This is the experiment that answers "does Noesis actually help an
agent solve more tasks per dollar?". It runs the same Claude policy
in two configurations on the same task suite and diffs the results:

* **treatment** — Claude with the Noesis MCP servers (Mneme, Praxis,
  Telos, …) wired in as tools.
* **baseline** — same Claude config (model, prompt, max_turns), no
  Noesis servers attached.

Any signed delta between the two is attributable to the Noesis tool
surface, not to Claude itself. That's what makes this measurement the
unit of "are we building something of value".

## Prerequisites

1. **Claude CLI on PATH.** `claude-agent-sdk` spawns it as a
   subprocess; if `which claude` returns nothing the treatment side
   will fail at the first turn. Authenticate it with whatever Claude
   account you want the experiment billed to (Max OAuth, API key,
   etc.) — the SDK inherits its session.
2. **`eval/.env.e2e` populated.** Copy `eval/.env.e2e.example` to
   `eval/.env.e2e` and fill in `NOESIS_<SERVICE>_URL` /
   `NOESIS_<SERVICE>_SECRET` for each Noesis service that should
   appear in treatment. Services with an unset URL are silently
   skipped (so a `NOESIS_LOGOS_URL=` line will exclude Logos from the
   treatment surface). The file is gitignored.
3. **Eval package installed.** From the repo root:

   ```bash
   pip install -e schemas/ kairos/ services/praxis/ eval/
   ```

## One command to run the whole thing

The wrapper runs both sides and writes the verdict to
`ab-runs/delta.json` plus the two episode JSONLs:

```bash
set -a; source eval/.env.e2e; set +a   # export the NOESIS_* vars
cd eval
python -m noesis_eval.ab ab \
    --treatment mcp-treatment \
    --baseline  mcp-baseline \
    --suite     stage3 \
    --samples   3 \
    --out-dir   ab-runs/$(date -u +%Y-%m-%dT%H-%M-%SZ)
```

* `--samples 3` replays each task three times per side — enough to
  shrink the per-task confidence interval without 10× cost. Use 5+
  once you want narrower CIs.
* `--suite stage3` is the 50-task suite. Use `--suite default` (5
  tasks) for a smoke run.
* `--out-dir` defaults to `ab-runs/`. Stamping it with a UTC
  timestamp keeps successive runs from overwriting each other.

The wrapper streams the JSONLs as it goes — if the run dies halfway
through, the partial files are still on disk and you can `ab diff`
them by hand to see what was completed.

## Reading the output

The on-stdout summary prints the headline numbers:

```
treatment (mcp-treatment) vs baseline (mcp-baseline)
  shared tasks:      50  (treatment=150 episodes, baseline=150)
  treatment success: 0.620
  baseline success:  0.500
  delta:             +0.120  (95% CI [+0.041, +0.199])
  p-value:           0.0021 *
  wins:   18
  losses: 7
  cost (tokens/episode): treatment=4280.5, baseline=2110.0 (ratio 2.03×)
  wall time (s/episode): treatment=18.412, baseline=9.221
```

* **delta** — unweighted mean of per-task `(treatment - baseline)`
  success rates. Signed fraction in [-1, 1].
* **95% CI** — Normal-approximation half-width on that mean. If the
  interval doesn't contain 0, the effect is real at 95% confidence.
* **p-value** — exact two-sided binomial sign test on win/loss
  counts; the trailing `*` flag means it's below 0.05 (the
  conventional bar).
* **wins / losses** — tasks where one side strictly beat the other.
  Tied tasks (both pass, both fail, or both at the same fractional
  rate) carry no signal and stay out of the count.
* **cost / wall time** — per-episode means. The `tokens_ratio` is
  treatment-divided-by-baseline; `inf` means the baseline used no
  tokens (Oracle / Null cases).

`delta.json` has the same fields as machine-readable JSON for
dashboards or regression gates.

## Self-A/B (variance estimate)

Running the same agent against itself measures intrinsic noise:

```bash
python -m noesis_eval.ab ab --treatment mcp-treatment --baseline mcp-treatment \
    --samples 5 --out-dir ab-runs/self-noise
```

The wrapper warns to stderr when both sides match. The resulting
delta is the noise floor — anything smaller than that on a real A/B
is not signal.

## Re-diffing past runs

JSONL files are concatenable across machines. To merge two runs of
the same agent and re-diff:

```bash
cat ab-runs/run1/mcp-treatment.jsonl ab-runs/run2/mcp-treatment.jsonl > /tmp/t.jsonl
cat ab-runs/run1/mcp-baseline.jsonl  ab-runs/run2/mcp-baseline.jsonl  > /tmp/b.jsonl
python -m noesis_eval.ab diff /tmp/t.jsonl /tmp/b.jsonl
```

This is how you accumulate samples across overnight runs to tighten
the CI without paying for a single very-long run.

## What to do with the answer

* **`delta` ≥ 0 with `p < 0.05` and `tokens_ratio` ≤ ~3×** — Noesis
  is helping at acceptable cost. Ship the change.
* **`delta` ≥ 0 with `p > 0.05`** — under-powered. Run more samples
  before concluding either way; tiny suites can't reject the null
  even when the effect is real.
* **`delta < 0`** — Noesis hurt. Inspect `wins`/`losses` and
  `per_task` to find which tasks regressed; usually it's a small
  number of tasks where the extra tool surface confused the model.
* **`tokens_ratio` ≫ 1× with small `delta`** — economically a loss
  even if statistically positive. Not worth keeping.

The point of this harness is to make those four answers the actual
output of every Noesis change worth measuring.

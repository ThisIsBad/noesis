# LLM-as-judge rubric — design draft

> **Status: draft, 2026-04-23.** Written as part of Tier-3 T3.8
> preparation in [`docs/architect-review-2026-04-23.md`](../architect-review-2026-04-23.md).
> Not wired to the eval harness yet — rubric needs review before any
> implementation spend.

## Problem

The existing A/B harness (`eval/src/noesis_eval/ab/`) measures
**deterministic outcomes**: ALFWorld success rate, Mneme recall@10,
task completion, A/B p-values. These are the right metrics for
asking *"did the agent finish?"* — they catch the big regressions.

What they miss: **quality-of-reasoning regressions**. The agent can
finish a task correctly *and* do it in a way that's getting slowly
worse — sloppier tool-use, skipped verification, memories stored
without certificates, plans committed without backtracking on a
failed substep. Those don't flip a success bit. They erode the
reflexive-agent property the project is built to give us.

An LLM-as-judge is the standard answer. The standard trap is running
it on every eval, producing opinionated scores about "reasoning
quality" that drift with whoever wrote the prompt, and billing a
monthly subscription for noise. So: **design the rubric first.**

## Design principles

1. **Invariants, not vibes.** Every score is a yes/no answer to a
   concrete question about the trace. "Did the agent cite Logos
   before storing a belief?" — answerable, checkable, stable across
   raters. "Was the reasoning elegant?" — refuse.
2. **Per-dimension score.** No single aggregate "quality: 7/10".
   Aggregates hide regressions. A failed invariant is a flagged
   trace.
3. **Sample, don't stream.** Judge runs on 5-10 % of traces,
   stratified by verdict. Never on every trace.
4. **Cache by trace hash.** Same trace + same rubric version ⇒ same
   result. Costs zero on re-runs.
5. **Hard budget cap.** `NOESIS_AB_JUDGE_MAX_BUDGET_USD` (default
   $0.50) per eval invocation. Mirror the existing
   `NOESIS_AB_MAX_BUDGET_USD` pattern.
6. **Rubric versioning.** `rubric_v1` ships in source; cache keys
   include the version. Score drift between versions is expected and
   compared explicitly, never aliased to the same metric.

## The invariants (v1 draft — needs review)

Seven invariants. Each has: what it checks, how a judge verifies it
given the trace, and concrete pass / fail examples.

### I-01  Verification before durable writes

> Did the agent call `Logos.certify_claim` (or another Logos
> verification tool) before calling `Mneme.store_memory` with a
> non-trivial claim?

**Trace signal:** look for a `Mneme.store_memory` call. If its
`content` is declarative ("X implies Y", "the capital of France is
Paris") and there is no `Logos.*` call earlier in the same
conversational turn citing the same claim, fail.

- **Pass:** `Logos.certify_claim("rain implies wet")` → gets cert →
  `Mneme.store_memory(content="rain implies wet", certificate=<cert>)`.
- **Fail:** `Mneme.store_memory(content="quantum computers factor
  primes in P", certificate=None)`.
- **Not applicable:** `Mneme.store_memory(content="user asked for
  help with foo", memory_type=EPISODIC)` — episodic, not declarative.

### I-02  Backtracking on committed failure

> After a `Praxis.commit_step(..., success=False)`, did the agent
> call `Praxis.backtrack`?

**Trace signal:** scan Praxis commits with `success=False`. For each,
the next Praxis tool call on the same `plan_id` must be
`backtrack`. Not calling it (e.g. continuing with the next step
regardless) fails the invariant.

- **Pass:** commit with failure → backtrack → pick a sibling step.
- **Fail:** commit with failure → immediate `commit_step` on the
  next step (no backtrack).

### I-03  Verify-plan before risky execution

> Did the agent call `Praxis.verify_plan` at least once before the
> first `Praxis.commit_step` on plans whose steps include a
> `risk_score ≥ 0.5`?

**Trace signal:** inspect plans; for the subset with any
high-risk step, verify-plan must precede any commit.

- **Pass:** decompose → add_step (risk 0.7) → verify_plan → commit.
- **Fail:** decompose → add_step (risk 0.7) → commit.
- **Not applicable:** every step has `risk_score < 0.5`.

### I-04  Goal-contract registration on multi-step plans

> When a plan has ≥ 3 committed steps, was a `Telos.register_goal`
> called before the first step?

Single-step toy tasks don't need contracts. Multi-step work should.

- **Pass:** register_goal → decompose → 3 × (add_step, commit).
- **Fail:** decompose → 3 × commit (no Telos call anywhere).

### I-05  Drift-check before destructive actions

> Did the agent call `Telos.check_action_alignment` before any
> action the trace labels "destructive" (delete, drop, revoke,
> rm -rf, ...)?

**Trace signal:** the Logos policy layer tags destructive actions in
its `ActionPolicyResult`. The eval rig can synthesise those tags
when they're not native. Any tool call flagged destructive must be
preceded by a Telos alignment check.

### I-06  Calibration logging on predictions

> Did the agent call `Episteme.log_prediction` at least once in
> tasks where it made a claim with confidence < 0.8?

**Trace signal:** heuristic — look for low-confidence assertions in
`Mneme.store_memory` calls (`confidence < 0.8` in the memory
payload). At least one should be followed by an `Episteme.log_prediction`.
Not every such claim; at least one, within the trace window.

### I-07  Skill reuse on repeat work

> Did the agent call `Techne.retrieve_skill` before rolling its own
> strategy for a task domain where a verified skill already exists?

**Trace signal:** the eval harness ships a `known_skills` manifest
per task. If the trace's declared domain is in `known_skills`, a
`Techne.retrieve_skill` must appear before any `Praxis.decompose_goal`
in the trace.

## What the judge returns

Structured JSON, one object per trace sampled:

```json
{
  "trace_id": "abc-123",
  "rubric_version": "v1",
  "invariants": [
    {"id": "I-01", "verdict": "pass",           "rationale": "..."},
    {"id": "I-02", "verdict": "not_applicable", "rationale": "no failed commits"},
    {"id": "I-03", "verdict": "fail",           "rationale": "step.risk_score=0.7, no verify_plan call seen before commit at t=5"},
    ...
  ],
  "judge_cost_usd": 0.012
}
```

Three verdicts: `pass`, `fail`, `not_applicable`. No numeric quality
score. Aggregate reporting is per-invariant pass-rate over the
sampled N.

## Plumbing

### Claude API call

- Model: Haiku 4.5 (fast + cheap; this is pattern matching, not
  creative work).
- Temperature: 0 (deterministic re-runs).
- Structured output: JSON schema matching the shape above.
- Prompt caching: the rubric itself is cached per-version; only the
  trace JSON is ephemeral per call.
- Budget cap: `NOESIS_AB_JUDGE_MAX_BUDGET_USD` with a default of
  **$0.50 per eval invocation**. The harness stops sampling when the
  cap is reached and records the truncation in the final report.

### Caching

- Cache key: `(trace_id, rubric_version)` → SHA-256 of the trace
  JSON.
- Backing store: local SQLite in `eval/tmp/judge-cache.db` for dev;
  in CI it lives in the GitHub Actions cache keyed on the job SHA.
- Cache invalidation: version bump only. Rubric edits without a
  version bump are a bug.

### Wiring

- New module: `eval/src/noesis_eval/ab/judge.py`.
- `Judge.score(trace) -> JudgeResult` — the callable the A/B runner
  invokes.
- Sample strategy: `random.Random(seed).random() < sample_rate`
  seeded per run so stratification is reproducible.
- Flag: `--judge v1` on the A/B CLI; absent = current behaviour
  (no LLM-as-judge).

## Open questions

These are what rubric review should resolve before any code spend:

1. **Is the invariant list the right shape?** Missing any? Any too
   fuzzy to verify from a trace?
2. **Sample rate.** Default to 10 %? Stratify by task difficulty,
   verdict, or not at all?
3. **Failure taxonomy.** When an invariant fails, does it map to a
   category (alignment / verification / planning / calibration) that
   groups into a dashboard?
4. **Regression threshold.** At what pass-rate drop does a PR fail
   CI? `any drop`? `> 5 pp drop`? Needs a noise floor measurement.
5. **Rubric governance.** Who versions v1 → v2? The repo? An
   architecture-decision record? Something lighter?

## Not committed to implementation

I deliberately did **not** write the `judge.py` module, the CI
wiring, or the prompt. That's a separate PR after rubric review —
writing the code first would commit the project to a specific
rubric we haven't agreed on.

Implementation effort after sign-off: ~1 day for the judge module
+ tests, ~½ day for CI wiring and cache primer.

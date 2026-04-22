"""CLI for the A/B harness.

Four subcommands:

    python -m noesis_eval.ab run <agent> [--suite default|stage3] --output run.jsonl
    python -m noesis_eval.ab diff <treatment.jsonl> <baseline.jsonl>
    python -m noesis_eval.ab ab --treatment <agent> --baseline <agent> \\
        [--samples N] [--out-dir DIR]
    python -m noesis_eval.ab history <ab-runs-dir>

``history`` walks a directory of past ``ab`` invocations (each a
subdir containing a treatment + baseline JSONL and optionally a
``delta.json``), prints the per-run headline numbers, then pools
every episode across every run and prints a single ``SuiteDelta`` on
the pooled data — which is how you tighten the CI without paying
for another run.

``run`` drives one agent across a task suite and writes one JSON object
per episode to stdout or ``--output``. ``diff`` loads two JSONL files,
pairs episodes by ``task_id``, and prints a summary plus per-task flip
table. ``ab`` is the canonical-experiment wrapper: runs both sides,
writes both JSONLs into a single output directory, then prints the
``SuiteDelta`` so the user gets the answer in one invocation. JSONL is
the record format so multiple independent runs can be concatenated and
re-diffed across machines.

Kept deliberately argparse-only (no Click / Typer) so the eval package
doesn't grow dependencies for one CLI.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import IO, Callable, Iterable, Iterator

from noesis_eval.alfworld_bench import (
    Task,
    build_default_suite,
    build_memory_suite,
    build_stage3_suite,
)
from noesis_eval.alfworld_bench.env import MockAlfworldEnv

from .agent import Agent, NullAgent, OracleAgent
from .mcp_agent import build_baseline_agent, build_treatment_agent
from .results import EpisodeResult, SuiteDelta, SuiteResults
from .runner import run_episode

SUITES = {
    "default": build_default_suite,
    "stage3": build_stage3_suite,
    "memory": build_memory_suite,
}


def _build_oracle(suite: list[Task]) -> OracleAgent:
    plans = {t.goal: list(t.canonical_plan) for t in suite}
    recovery = {
        t.goal: [t.recovery_actions[0]]
        for t in suite
        if t.recovery_actions
    }
    return OracleAgent(plans=plans, recovery=recovery)


AGENT_FACTORIES: dict[str, Callable[[list[Task]], Agent]] = {
    "null": lambda _suite: NullAgent(action="wait"),
    "oracle": _build_oracle,
    "mcp-treatment": lambda _suite: build_treatment_agent(),
    "mcp-baseline": lambda _suite: build_baseline_agent(),
}


def _run(
    agent: Agent, suite: Iterable[Task], sink: IO[str], samples: int = 1
) -> SuiteResults:
    """Stream episode results as JSONL while aggregating into SuiteResults.

    With ``samples > 1`` each task is replayed that many times and each
    replay gets a distinct ``seed`` (0…samples-1). This matters for
    LLM-driven agents where every roll differs; deterministic agents
    (Oracle, Null) will emit identical records, which is still useful
    for smoke-testing the multi-sample path.
    """
    if samples < 1:
        raise SystemExit(f"--samples must be >= 1, got {samples}")
    results = SuiteResults(agent=agent.name)
    task_list = list(suite)
    for seed in range(samples):
        for task in task_list:
            ep = run_episode(MockAlfworldEnv(task), agent)
            if seed != 0:
                # ``run_episode`` doesn't know about sampling; stamp
                # the seed post-hoc so the JSONL record still reflects
                # which replay this is.
                ep = replace(ep, seed=seed)
            results.record(ep)
            sink.write(json.dumps(ep.to_dict()) + "\n")
            sink.flush()
    return results


def _iter_jsonl(path: Path) -> Iterator[EpisodeResult]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"{path}:{line_no}: invalid JSON — {exc.msg}"
                ) from exc
            yield EpisodeResult(**raw)


def _load_suite_results(path: Path) -> SuiteResults:
    episodes = list(_iter_jsonl(path))
    if not episodes:
        raise SystemExit(f"{path}: no episodes recorded")
    agent_names = {e.agent for e in episodes}
    if len(agent_names) != 1:
        raise SystemExit(
            f"{path}: episodes come from multiple agents {sorted(agent_names)}; "
            "split the file or re-run"
        )
    results = SuiteResults(agent=episodes[0].agent)
    for ep in episodes:
        results.record(ep)
    return results


def _format_delta(delta: SuiteDelta) -> str:
    sig_marker = " *" if delta.significant_at_05 else ""
    ratio = delta.tokens_ratio
    ratio_str = "inf" if ratio == float("inf") else f"{ratio:.2f}×"
    lines = [
        f"treatment ({delta.treatment}) vs baseline ({delta.baseline})",
        f"  shared tasks:      {delta.shared_tasks}"
        f"  (treatment={delta.n_treatment_episodes} episodes, "
        f"baseline={delta.n_baseline_episodes})",
        f"  treatment success: {delta.treatment_success_rate:.3f}",
        f"  baseline success:  {delta.baseline_success_rate:.3f}",
        f"  delta:             {delta.delta:+.3f}"
        f"  (95% CI [{delta.ci95_low:+.3f}, {delta.ci95_high:+.3f}])",
        f"  p-value:           {delta.p_value:.4f}{sig_marker}",
        f"  wins:   {delta.wins}",
        f"  losses: {delta.losses}",
        f"  cost (tokens/episode): "
        f"treatment={delta.treatment_tokens_per_episode:.1f}, "
        f"baseline={delta.baseline_tokens_per_episode:.1f} "
        f"(ratio {ratio_str})",
        f"  wall time (s/episode): "
        f"treatment={delta.treatment_wall_time_per_episode:.3f}, "
        f"baseline={delta.baseline_wall_time_per_episode:.3f}",
    ]
    if delta.only_treatment:
        lines.append(
            f"  only in treatment ({len(delta.only_treatment)}): "
            + ", ".join(delta.only_treatment[:5])
            + ("…" if len(delta.only_treatment) > 5 else "")
        )
    if delta.only_baseline:
        lines.append(
            f"  only in baseline ({len(delta.only_baseline)}): "
            + ", ".join(delta.only_baseline[:5])
            + ("…" if len(delta.only_baseline) > 5 else "")
        )
    return "\n".join(lines)


def _cmd_run(args: argparse.Namespace) -> int:
    suite = SUITES[args.suite]()
    if args.agent not in AGENT_FACTORIES:
        raise SystemExit(
            f"unknown agent {args.agent!r}; choose from "
            f"{sorted(AGENT_FACTORIES)}"
        )
    agent = AGENT_FACTORIES[args.agent](suite)

    samples: int = args.samples
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            results = _run(agent, suite, f, samples=samples)
    else:
        results = _run(agent, suite, sys.stdout, samples=samples)

    summary = results.summary()
    print(
        f"\n{summary['agent']}: {summary['success_rate']:.1%} success "
        f"on {summary['episodes']} episodes "
        f"(recovery {summary['recovery_rate']:.1%})",
        file=sys.stderr,
    )
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    treatment = _load_suite_results(args.treatment)
    baseline = _load_suite_results(args.baseline)
    delta = treatment.diff(baseline)
    print(_format_delta(delta))
    return 0


def _build_agent_or_die(name: str, suite: list[Task]) -> Agent:
    if name not in AGENT_FACTORIES:
        raise SystemExit(
            f"unknown agent {name!r}; choose from "
            f"{sorted(AGENT_FACTORIES)}"
        )
    return AGENT_FACTORIES[name](suite)


def _cmd_ab(args: argparse.Namespace) -> int:
    """Canonical A/B in one shot: build both agents, run them across
    the same suite, write JSONLs, print the ``SuiteDelta``.

    The treatment/baseline names refer to entries in ``AGENT_FACTORIES``
    so the wrapper inherits whatever agents the rest of the CLI knows
    about — e.g. ``mcp-treatment`` / ``mcp-baseline`` once the SDK
    factories are wired in. No special-cased "this is the canonical
    experiment" flag: the experiment IS picking those names.
    """
    if args.samples < 1:
        raise SystemExit(f"--samples must be >= 1, got {args.samples}")
    if args.treatment == args.baseline:
        # Two runs of the same agent measure noise, not a delta. The
        # harness doesn't refuse, but it's almost always a typo, so
        # warn loudly to stderr instead of silently producing a near-
        # zero "result".
        print(
            f"warning: --treatment and --baseline are both "
            f"{args.treatment!r}; you'll be measuring run-to-run "
            f"noise, not a treatment effect.",
            file=sys.stderr,
        )

    suite = SUITES[args.suite]()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    treatment_path = out_dir / f"{args.treatment}.jsonl"
    baseline_path = out_dir / f"{args.baseline}.jsonl"
    delta_path = out_dir / "delta.json"

    # Build both agents up front so a typo in --baseline fails before
    # we burn budget on the treatment run.
    treatment_agent = _build_agent_or_die(args.treatment, suite)
    baseline_agent = _build_agent_or_die(args.baseline, suite)

    print(
        f"running treatment {args.treatment!r} on suite "
        f"{args.suite!r} ({args.samples} sample(s) per task) "
        f"→ {treatment_path}",
        file=sys.stderr,
    )
    with treatment_path.open("w", encoding="utf-8") as f:
        treatment_results = _run(
            treatment_agent, suite, f, samples=args.samples
        )

    print(
        f"running baseline  {args.baseline!r} on suite "
        f"{args.suite!r} ({args.samples} sample(s) per task) "
        f"→ {baseline_path}",
        file=sys.stderr,
    )
    with baseline_path.open("w", encoding="utf-8") as f:
        baseline_results = _run(
            baseline_agent, suite, f, samples=args.samples
        )

    delta = treatment_results.diff(baseline_results)
    delta_path.write_text(
        json.dumps(delta.summary(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(_format_delta(delta))
    print(f"\nwrote {delta_path}", file=sys.stderr)
    return 0


def _discover_ab_runs(root: Path) -> list[tuple[Path, Path, Path]]:
    """Find every valid ``ab`` run directory under ``root``.

    An ``ab`` run directory contains exactly one ``*.jsonl`` per
    agent side. A run is "valid" for history-pooling purposes if
    it holds **exactly two** JSONL files — one treatment, one
    baseline. Subdirs with other file counts are silently skipped
    (e.g. in-progress runs that only got treatment through, or a
    leftover delta.json folder); ``history`` prints a warning so
    the caller sees what was excluded.

    Returns tuples of ``(run_dir, first_jsonl, second_jsonl)`` where
    the first/second order is alphabetical for stability — the
    pairing into treatment vs baseline happens later based on the
    ``agent`` field inside the records, not filename.
    """
    runs: list[tuple[Path, Path, Path]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        jsonls = sorted(entry.glob("*.jsonl"))
        if len(jsonls) != 2:
            print(
                f"history: skipping {entry.name} — expected 2 JSONL "
                f"files, found {len(jsonls)}",
                file=sys.stderr,
            )
            continue
        runs.append((entry, jsonls[0], jsonls[1]))
    return runs


def _cmd_history(args: argparse.Namespace) -> int:
    """Walk a directory of past ``ab`` runs, print per-run + pooled deltas.

    Per-run output is a compact one-line-per-run table — just the
    headline numbers so weekly trends are visible at a glance. The
    pooled row at the bottom is the single most informative piece
    of output: concatenate every matching treatment + baseline
    episode across every run, diff once, get a CI that's as tight
    as the total sample count allows.

    Pooling is safe because A/B record files are additive JSONL —
    the whole harness was designed around this from the start.
    """
    root: Path = args.dir
    if not root.is_dir():
        raise SystemExit(f"{root}: not a directory")

    runs = _discover_ab_runs(root)
    if not runs:
        raise SystemExit(f"{root}: no valid ab run subdirs found")

    # Accumulator maps agent name → flat list of episodes drawn
    # from every run, used to compute the pooled delta at the end.
    pooled: dict[str, list[EpisodeResult]] = {}
    # Tally of which agent played the treatment role in each run,
    # so the pooled summary follows the majority rather than a
    # brittle alphabetical default that can flip the sign.
    treatment_role: dict[str, int] = {}

    # Per-run table header — fixed-width so copy-paste into docs /
    # GitHub comments renders as a clean code block.
    print(
        f"{'run':<30}  {'t':<12}  {'b':<12}  "
        f"{'delta':>8}  {'ci95':>12}  {'p':>7}"
    )
    print("-" * 90)

    for run_dir, a_path, b_path in runs:
        side_a = _load_suite_results(a_path)
        side_b = _load_suite_results(b_path)
        # Decide which side is treatment vs baseline by consulting
        # the matching delta.json if it's there; fall back to
        # alphabetical otherwise. This matters when weekly dirs
        # have the same agents in both positions and pooling across
        # swaps would cancel signal.
        delta_path = run_dir / "delta.json"
        treatment_agent: str | None = None
        if delta_path.exists():
            try:
                delta_summary = json.loads(delta_path.read_text(encoding="utf-8"))
                treatment_agent = delta_summary.get("treatment")
            except (json.JSONDecodeError, OSError):
                treatment_agent = None
        if treatment_agent is None or treatment_agent not in (
            side_a.agent, side_b.agent,
        ):
            treatment, baseline = side_a, side_b
        elif treatment_agent == side_a.agent:
            treatment, baseline = side_a, side_b
        else:
            treatment, baseline = side_b, side_a

        delta = treatment.diff(baseline)

        # Row.
        ci_str = f"[{delta.ci95_low:+.3f},{delta.ci95_high:+.3f}]"
        sig = "*" if delta.significant_at_05 else " "
        print(
            f"{run_dir.name:<30}  {treatment.agent[:12]:<12}  "
            f"{baseline.agent[:12]:<12}  "
            f"{delta.delta:>+8.3f}  {ci_str:>12}  "
            f"{delta.p_value:>6.4f}{sig}"
        )

        # Pool.
        for ep in treatment.episodes:
            pooled.setdefault(treatment.agent, []).append(ep)
        for ep in baseline.episodes:
            pooled.setdefault(baseline.agent, []).append(ep)
        treatment_role[treatment.agent] = (
            treatment_role.get(treatment.agent, 0) + 1
        )

    # Pool requires exactly two agent names across every run. If
    # weekly runs swap agents around (e.g. a week of mcp-treatment
    # vs mcp-baseline and then a week of mcp-treatment vs null),
    # pooling straight across would be meaningless. Flag and
    # refuse rather than quietly averaging noise.
    if len(pooled) != 2:
        print()
        print(
            f"history: found {len(pooled)} distinct agent names "
            f"across runs ({sorted(pooled)}); skipping pooled delta.",
            file=sys.stderr,
        )
        return 0

    agent_names = sorted(pooled)
    # "Treatment" role for pooling = whichever agent played
    # treatment most often across the runs. Alphabetical as
    # tiebreaker so the output is deterministic.
    treatment_name = max(
        agent_names,
        key=lambda name: (treatment_role.get(name, 0), -agent_names.index(name)),
    )
    baseline_name = [n for n in agent_names if n != treatment_name][0]

    pooled_treatment = SuiteResults(agent=treatment_name)
    for ep in pooled[treatment_name]:
        pooled_treatment.record(ep)
    pooled_baseline = SuiteResults(agent=baseline_name)
    for ep in pooled[baseline_name]:
        pooled_baseline.record(ep)

    pooled_delta = pooled_treatment.diff(pooled_baseline)

    print()
    print("Pooled across all runs:")
    print(_format_delta(pooled_delta))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noesis_eval.ab",
        description="Noesis A/B harness — agent-with-Noesis vs agent-alone.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run one agent across a task suite")
    run_p.add_argument(
        "agent",
        help=f"agent name (available: {', '.join(sorted(AGENT_FACTORIES))})",
    )
    run_p.add_argument(
        "--suite",
        default="default",
        choices=sorted(SUITES),
        help="which task suite to run (default: %(default)s)",
    )
    run_p.add_argument(
        "--output",
        type=Path,
        help="write JSONL here; default stdout",
    )
    run_p.add_argument(
        "--samples",
        type=int,
        default=1,
        help=(
            "replay each task N times (default: 1). Each replay gets a "
            "distinct seed in the JSONL record so downstream diff can "
            "compute per-task success rates."
        ),
    )
    run_p.set_defaults(func=_cmd_run)

    diff_p = sub.add_parser("diff", help="compare two JSONL runs")
    diff_p.add_argument("treatment", type=Path, help="treatment JSONL file")
    diff_p.add_argument("baseline", type=Path, help="baseline JSONL file")
    diff_p.set_defaults(func=_cmd_diff)

    ab_p = sub.add_parser(
        "ab",
        help=(
            "run treatment + baseline + diff in one shot — the "
            "canonical-A/B convenience wrapper"
        ),
    )
    ab_p.add_argument(
        "--treatment",
        required=True,
        help=(
            "treatment agent name. The canonical experiment uses "
            "mcp-treatment (Claude with the Noesis MCP servers wired "
            "in)."
        ),
    )
    ab_p.add_argument(
        "--baseline",
        required=True,
        help=(
            "baseline agent name. The canonical experiment uses "
            "mcp-baseline (same Claude config, no Noesis servers)."
        ),
    )
    ab_p.add_argument(
        "--suite",
        default="stage3",
        choices=sorted(SUITES),
        help="task suite (default: %(default)s)",
    )
    ab_p.add_argument(
        "--samples",
        type=int,
        default=1,
        help=(
            "replay each task N times per side (default: 1). "
            "Higher values shrink the per-task confidence interval at "
            "the cost of N× the budget; 3-5 is a reasonable starting "
            "point for stochastic agents."
        ),
    )
    ab_p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("ab-runs"),
        help=(
            "directory to write <treatment>.jsonl, <baseline>.jsonl, "
            "and delta.json (default: %(default)s). Created if absent. "
            "Existing files at those paths are overwritten."
        ),
    )
    ab_p.set_defaults(func=_cmd_ab)

    history_p = sub.add_parser(
        "history",
        help=(
            "walk a directory of past ab runs, print per-run headline "
            "numbers plus a pooled delta across all of them"
        ),
    )
    history_p.add_argument(
        "dir",
        type=Path,
        help=(
            "directory whose immediate subdirs are ab-run outputs "
            "(each containing two JSONL files). Typically the "
            "out-dir from prior `ab` invocations."
        ),
    )
    history_p.set_defaults(func=_cmd_history)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":  # pragma: no cover — dispatched via -m
    raise SystemExit(main())

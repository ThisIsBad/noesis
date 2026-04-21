"""CLI for the A/B harness.

Two subcommands:

    python -m noesis_eval.ab run <agent> [--suite default|stage3] --output run.jsonl
    python -m noesis_eval.ab diff <treatment.jsonl> <baseline.jsonl>

``run`` drives one agent across a task suite and writes one JSON object
per episode to stdout or ``--output``. ``diff`` loads two JSONL files,
pairs episodes by ``task_id``, and prints a summary plus per-task flip
table. JSONL is the record format so multiple independent runs can be
concatenated and re-diffed, which is how we'll measure variance once
the API-backed agent lands.

Kept deliberately argparse-only (no Click / Typer) so the eval package
doesn't grow dependencies for one CLI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import IO, Callable, Iterable, Iterator

from noesis_eval.alfworld_bench import (
    Task,
    build_default_suite,
    build_stage3_suite,
)
from noesis_eval.alfworld_bench.env import MockAlfworldEnv

from .agent import Agent, NullAgent, OracleAgent
from .results import EpisodeResult, SuiteDelta, SuiteResults
from .runner import run_episode

SUITES = {
    "default": build_default_suite,
    "stage3": build_stage3_suite,
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
}


def _run(
    agent: Agent, suite: Iterable[Task], sink: IO[str]
) -> SuiteResults:
    """Stream episode results as JSONL while aggregating into SuiteResults."""
    results = SuiteResults(agent=agent.name)
    for task in suite:
        ep = run_episode(MockAlfworldEnv(task), agent)
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
    lines = [
        f"treatment ({delta.treatment}) vs baseline ({delta.baseline})",
        f"  shared episodes: {delta.shared_episodes}",
        f"  treatment success: {delta.treatment_success_rate:.3f}",
        f"  baseline success:  {delta.baseline_success_rate:.3f}",
        f"  delta:             {delta.delta:+.3f}",
        f"  wins:   {delta.wins}",
        f"  losses: {delta.losses}",
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

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            results = _run(agent, suite, f)
    else:
        results = _run(agent, suite, sys.stdout)

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
    run_p.set_defaults(func=_cmd_run)

    diff_p = sub.add_parser("diff", help="compare two JSONL runs")
    diff_p.add_argument("treatment", type=Path, help="treatment JSONL file")
    diff_p.add_argument("baseline", type=Path, help="baseline JSONL file")
    diff_p.set_defaults(func=_cmd_diff)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":  # pragma: no cover — dispatched via -m
    raise SystemExit(main())

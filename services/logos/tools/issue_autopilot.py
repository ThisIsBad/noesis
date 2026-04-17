"""Auto-refill GitHub issues when backlog is low.

Default behavior is a dry run. Use ``--execute`` to create issues.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IssueTemplate:
    """Template for one backlog issue candidate."""

    title: str
    goal: str
    scope: tuple[str, ...]
    non_scope: tuple[str, ...]
    acceptance: tuple[str, ...]
    risk_notes: tuple[str, ...]
    success_metric: str


CATALOG: tuple[IssueTemplate, ...] = (
    IssueTemplate(
        title="Vision: v2.1 Semantic Memory Compaction with Proof Preservation",
        goal=(
            "Build long-horizon memory compaction that preserves verifiable reasoning "
            "invariants while reducing context footprint."
        ),
        scope=(
            "Compaction pipeline for assumptions, proofs, and plan traces",
            "Proof-preserving summarization checks",
            "Deterministic replay compatibility after compaction",
        ),
        non_scope=(
            "Vector database integration",
            "LLM prompt compression heuristics",
        ),
        acceptance=(
            "Compaction reduces stored state size with no proof-integrity regressions",
            "Replay from compacted state reproduces the same policy/proof decisions",
            "Metamorphic tests cover compaction-order invariance",
        ),
        risk_notes=(
            "Over-aggressive compaction can hide critical dependencies",
            "Must avoid non-deterministic summarization behavior",
        ),
        success_metric="Lower state footprint without increased verification failures.",
    ),
    IssueTemplate(
        title="Vision: v2.2 Mechanistic Explanation Generator for Decisions",
        goal="Generate machine-checkable explanations for why each autonomous decision was selected.",
        scope=(
            "Decision explanation schema linked to policy/proof/uncertainty inputs",
            "Minimal-cause extraction for accepted and rejected branches",
            "Serialization for audit and replay artifacts",
        ),
        non_scope=(
            "Natural-language storytelling outputs",
            "UI visualization tooling",
        ),
        acceptance=(
            "Every high-impact action has a structured explanation payload",
            "Explanation references resolvable evidence IDs",
            "Equivalent reasoning states yield equivalent explanation structure",
        ),
        risk_notes=(
            "Explanation payload bloat if schema is not normalized",
            "Causal ambiguity when multiple sufficient supports exist",
        ),
        success_metric="Higher post-mortem debuggability with deterministic explanation lineage.",
    ),
    IssueTemplate(
        title="Vision: v2.3 Sandbox World Models for Safe Plan Rehearsal",
        goal="Run proposed multi-step plans in deterministic sandbox world models before real execution.",
        scope=(
            "World-model interface with deterministic transitions",
            "Plan rehearsal API integrated with counterfactual branches",
            "Failure surface extraction from rehearsal runs",
        ),
        non_scope=(
            "Physics-grade simulators",
            "Real-time environment synchronization",
        ),
        acceptance=(
            "Plans can be rehearsed and scored before execution approval",
            "Rehearsal failures generate structured constraints for replanning",
            "Metamorphic tests cover world-state reset invariance",
        ),
        risk_notes=(
            "Model mismatch between sandbox and real execution",
            "State explosion for deep branch rehearsals",
        ),
        success_metric="Fewer execution-time failures after pre-execution rehearsal.",
    ),
    IssueTemplate(
        title="Vision: v2.4 Verifiable Tool Capability Registry",
        goal="Introduce a formal capability registry so agents can prove tool suitability before invoking actions.",
        scope=(
            "Capability schema with preconditions, guarantees, and side-effect classes",
            "Capability checks in action-policy and execution-bus paths",
            "Mismatch diagnostics when requested action exceeds capability",
        ),
        non_scope=(
            "External marketplace/discovery service",
            "Vendor-specific connectors",
        ),
        acceptance=(
            "Tool calls are blocked when required capability contracts are unmet",
            "Capability lookups are deterministic and versioned",
            "Metamorphic tests cover capability alias invariance",
        ),
        risk_notes=(
            "Capability taxonomy drift across modules",
            "Over-constrained capabilities can reduce utility",
        ),
        success_metric="Lower rate of invalid tool invocations under autonomous workloads.",
    ),
    IssueTemplate(
        title="Vision: v2.5 Long-Horizon Curriculum Benchmarks",
        goal="Create benchmark curricula that test reasoning integrity across extended autonomous episodes.",
        scope=(
            "Curriculum generator with escalating uncertainty/policy pressure",
            "Episode-level scoring (safety, correctness, recovery, efficiency)",
            "CI-compatible benchmark report artifacts",
        ),
        non_scope=(
            "Human annotation platforms",
            "Leaderboard infrastructure",
        ),
        acceptance=(
            "Benchmarks run reproducibly with fixed seeds",
            "Scorecards expose regression deltas between commits",
            "Adversarial and nominal tracks are both included",
        ),
        risk_notes=(
            "Benchmark overfitting if scenario diversity is low",
            "Runtime cost growth for long episodes",
        ),
        success_metric="Reliable measurement of long-horizon autonomy progress release-over-release.",
    ),
    IssueTemplate(
        title="Vision: v2.6 Formalized Multi-Agent Negotiation Protocol",
        goal="Add deterministic negotiation semantics for conflicting plans among collaborating agents.",
        scope=(
            "Negotiation protocol states (propose, challenge, revise, accept, reject)",
            "Proof-backed objections and counter-proposals",
            "Termination guarantees to prevent deadlock loops",
        ),
        non_scope=(
            "Distributed consensus algorithms",
            "Human arbitration interfaces",
        ),
        acceptance=(
            "Negotiation outcomes are replayable and deterministic",
            "Conflict reasons are machine-readable and evidence-backed",
            "Metamorphic tests cover participant-order invariance",
        ),
        risk_notes=(
            "Protocol complexity can mask simple conflict causes",
            "Deadlock risk without strict termination rules",
        ),
        success_metric="Higher agreement quality across independent agent planners.",
    ),
    IssueTemplate(
        title="Vision: v2.7 Safety Envelope Synthesis from Incident Data",
        goal="Derive tighter formal safety envelopes from observed failure incidents and near misses.",
        scope=(
            "Incident schema and ingestion path",
            "Deterministic synthesis of candidate safety constraints",
            "Review workflow for promoting synthesized constraints into active policy",
        ),
        non_scope=(
            "Automated policy auto-merge without review",
            "External SIEM integrations",
        ),
        acceptance=(
            "Incident-derived constraints are reproducible from source data",
            "Promotion process preserves policy traceability",
            "Regression tests cover incident replay consistency",
        ),
        risk_notes=(
            "Noisy incident data can produce brittle constraints",
            "Overfitting safety envelopes to historical failures",
        ),
        success_metric="Decreasing recurrence of previously observed failure classes.",
    ),
    IssueTemplate(
        title="Vision: v2.8 Governance Pack Export for External Auditors",
        goal="Produce audit-ready governance packs proving end-to-end compliance of autonomous runs.",
        scope=(
            "Export bundle combining decisions, proofs, policy checks, and uncertainty gates",
            "Deterministic redaction policy for sensitive fields",
            "Verifier tool for third-party audit reproduction",
        ),
        non_scope=(
            "Legal workflow automation",
            "External ticketing integrations",
        ),
        acceptance=(
            "Governance packs can be independently verified offline",
            "Redacted and unredacted packs preserve verification integrity",
            "Schema versioning and migration guidance included",
        ),
        risk_notes=(
            "Redaction could accidentally break referential integrity",
            "Pack size growth for long-horizon traces",
        ),
        success_metric="Faster, reproducible external audits with minimal manual reconstruction.",
    ),
)


def _run_gh_json(args: list[str]) -> object:
    command = ["gh", *args]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"gh command failed: {' '.join(command)}\n{process.stderr.strip()}")
    return json.loads(process.stdout)


def _load_known_titles_from_file(file_path: Path | None) -> set[str]:
    if file_path is None:
        return set()
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(v, str) for v in payload):
        raise ValueError("--known-titles-file must be a JSON array of strings")
    return set(payload)


def _list_open_issues() -> list[dict[str, object]]:
    payload = _run_gh_json(["issue", "list", "--state", "open", "--limit", "200", "--json", "number,title,url"])
    if not isinstance(payload, list):
        raise ValueError("Unexpected response for open issues")
    return payload


def _list_all_issue_titles() -> set[str]:
    payload = _run_gh_json(["issue", "list", "--state", "all", "--limit", "500", "--json", "title"])
    if not isinstance(payload, list):
        raise ValueError("Unexpected response for issue titles")
    titles: set[str] = set()
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("title"), str):
            titles.add(item["title"])
    return titles


def _build_issue_body(template: IssueTemplate) -> str:
    scope = "\n".join(f"- {item}" for item in template.scope)
    non_scope = "\n".join(f"- {item}" for item in template.non_scope)
    acceptance = "\n".join(f"- [ ] {item}" for item in template.acceptance)
    risk_notes = "\n".join(f"- {item}" for item in template.risk_notes)
    return (
        "## Goal\n"
        f"{template.goal}\n\n"
        "## Scope\n"
        f"{scope}\n\n"
        "## Non-scope\n"
        f"{non_scope}\n\n"
        "## Acceptance Criteria\n"
        f"{acceptance}\n\n"
        "## Test Plan\n"
        "- Local: full preflight gates from `docs/development_process.md`\n"
        "- CI: all required jobs green, including metamorphic gate\n\n"
        "## Risk Notes\n"
        f"{risk_notes}\n\n"
        "## Success Metric\n"
        f"- {template.success_metric}\n"
    )


def _create_issue(template: IssueTemplate) -> str:
    body = _build_issue_body(template)
    command = ["gh", "issue", "create", "--title", template.title, "--body", body]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(
            "Issue creation failed "
            f"for '{template.title}': {process.stderr.strip() or process.stdout.strip()}"
        )
    return process.stdout.strip()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-refill backlog issues when queue is low")
    parser.add_argument(
        "--min-open",
        type=int,
        default=2,
        help="Only refill when open issue count is below this threshold",
    )
    parser.add_argument(
        "--target-open",
        type=int,
        default=5,
        help="Desired open issue count after refill",
    )
    parser.add_argument(
        "--max-create",
        type=int,
        default=5,
        help="Maximum number of issues to create per run",
    )
    parser.add_argument("--execute", action="store_true", help="Create issues (default is dry-run)")
    parser.add_argument(
        "--open-count-override",
        type=int,
        help="Skip GitHub query and use this open issue count (useful for local dry-run tests)",
    )
    parser.add_argument(
        "--known-titles-file",
        type=Path,
        help="Optional JSON file with known issue titles to avoid duplicates in dry-run mode",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.min_open < 0 or args.target_open < 0 or args.max_create < 0:
        raise ValueError("--min-open, --target-open and --max-create must be >= 0")
    if args.target_open < args.min_open:
        raise ValueError("--target-open must be >= --min-open")

    if args.open_count_override is not None:
        open_count = args.open_count_override
        known_titles = _load_known_titles_from_file(args.known_titles_file)
    else:
        open_issues = _list_open_issues()
        open_count = len(open_issues)
        known_titles = _list_all_issue_titles()

    print(f"Open issues: {open_count}")

    if open_count >= args.min_open:
        print("Backlog threshold satisfied. No refill needed.")
        return 0

    refill_needed = max(0, args.target_open - open_count)
    create_limit = min(refill_needed, args.max_create)

    candidates = [template for template in CATALOG if template.title not in known_titles]
    selected = candidates[:create_limit]

    if not selected:
        print("No unique templates available in catalog. Nothing to create.")
        return 0

    print(f"Selected {len(selected)} issue(s) for backlog refill:")
    for template in selected:
        print(f"- {template.title}")

    if not args.execute:
        print("Dry-run mode: no issues created. Re-run with --execute to create them.")
        return 0

    print("Creating issues...")
    for template in selected:
        url = _create_issue(template)
        print(f"- created: {url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

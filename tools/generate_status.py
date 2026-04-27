#!/usr/bin/env python3
"""Generate STATUS.md from filesystem state.

Scans every service / cross-cutting component and builds a single
top-level ``STATUS.md`` that answers:

  - Does it have a Dockerfile / railway.toml / CI workflow / MCP server?
  - How big is it (src LOC, test LOC, test-file count)?
  - What's its declared description (from pyproject.toml)?
  - When was it last touched (git)?

We deliberately do NOT try to read CI results or Railway deploy status
— those require auth and API calls. Filesystem state is enough to
catch the biggest failure mode ("the README claims X is planned, but
X has 600 lines of code and a CI workflow").

Zero-dep: stdlib only, so the generator can run in any CI
environment without extra installs.

Run::

    python tools/generate_status.py

Or, to check for drift::

    python tools/generate_status.py --check

which writes to a temp file and diffs; exits non-zero on drift.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
STATUS_PATH = REPO_ROOT / "STATUS.md"


# Components to report on. Each entry declares the on-disk path and a
# short role tag used for the legend. Add new rows here when a new
# service / package lands.
COMPONENTS: list[tuple[str, str, str]] = [
    # (name,           path,                    role)
    ("logos",          "services/logos",        "service"),
    ("mneme",          "services/mneme",        "service"),
    ("praxis",         "services/praxis",       "service"),
    ("telos",          "services/telos",        "service"),
    ("episteme",       "services/episteme",     "service"),
    ("kosmos",         "services/kosmos",       "service"),
    ("empiria",        "services/empiria",      "service"),
    ("techne",         "services/techne",       "service"),
    ("console",        "services/console",      "service"),
    ("schemas",        "schemas",               "cross-cutting"),
    ("kairos",         "kairos",                "cross-cutting"),
    ("clients",        "clients",               "cross-cutting"),
    ("eval",           "eval",                  "cross-cutting"),
    ("theoria",        "ui/theoria",            "ui"),
    ("console-ui",     "ui/console",            "ui"),
]


@dataclasses.dataclass
class Report:
    name: str
    path: str
    role: str
    exists: bool
    has_dockerfile: bool
    has_railway: bool
    has_pyproject: bool
    has_mcp_server: bool
    has_ci_workflow: bool
    ci_workflow_path: str | None
    src_loc: int
    test_loc: int
    test_file_count: int
    description: str
    last_commit: str

    def mark(self, ok: bool) -> str:
        return "✓" if ok else "—"


def scan(name: str, rel_path: str, role: str) -> Report:
    base = REPO_ROOT / rel_path
    exists = base.exists()

    dockerfile = (base / "Dockerfile").is_file()
    railway = (base / "railway.toml").is_file()
    pyproject = (base / "pyproject.toml").is_file()

    mcp_server = _find_mcp_server(base, name, rel_path)
    ci_path = _find_ci_workflow(name)

    src_root = _src_root(base, name, rel_path)
    src_loc = _loc(src_root) if src_root else 0

    tests_root = base / "tests"
    test_loc = _loc(tests_root) if tests_root.is_dir() else 0
    test_files = (
        sum(1 for p in tests_root.rglob("test_*.py"))
        if tests_root.is_dir()
        else 0
    )

    description = _pyproject_description(base / "pyproject.toml")
    last_commit = _git_last_commit(rel_path)

    return Report(
        name=name,
        path=rel_path,
        role=role,
        exists=exists,
        has_dockerfile=dockerfile,
        has_railway=railway,
        has_pyproject=pyproject,
        has_mcp_server=mcp_server,
        has_ci_workflow=ci_path is not None,
        ci_workflow_path=ci_path,
        src_loc=src_loc,
        test_loc=test_loc,
        test_file_count=test_files,
        description=description,
        last_commit=last_commit,
    )


def _src_root(base: Path, name: str, rel_path: str) -> Path | None:
    # Services & kairos & theoria: src/<name>/
    candidate = base / "src" / name
    if candidate.is_dir():
        return candidate
    # schemas: src/noesis_schemas/
    candidate = base / "src" / "noesis_schemas"
    if candidate.is_dir():
        return candidate
    # clients: src/noesis_clients/
    candidate = base / "src" / "noesis_clients"
    if candidate.is_dir():
        return candidate
    # eval: src/noesis_eval/
    candidate = base / "src" / "noesis_eval"
    if candidate.is_dir():
        return candidate
    # fallback: whole src/
    if (base / "src").is_dir():
        return base / "src"
    return None


def _find_mcp_server(base: Path, name: str, rel_path: str) -> bool:
    """Return True if the component exposes an MCP HTTP server."""
    # Typical path: services/<name>/src/<name>/mcp_server_http.py
    for candidate in (
        base / "src" / name / "mcp_server_http.py",
        base / "src" / "noesis_schemas" / "mcp_server_http.py",  # (never)
        base / "src" / "noesis_clients" / "mcp_server_http.py",  # (never)
        base / "src" / "noesis_eval" / "mcp_server_http.py",     # (never)
        base / "src" / "kairos" / "mcp_server_http.py",
    ):
        if candidate.is_file():
            return True
    return False


def _find_ci_workflow(name: str) -> str | None:
    if not WORKFLOWS.is_dir():
        return None
    candidate = WORKFLOWS / f"{name}.yml"
    if candidate.is_file():
        return str(candidate.relative_to(REPO_ROOT))
    return None


def _loc(root: Path) -> int:
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                total += sum(1 for _ in fh)
        except OSError:
            pass
    return total


def _pyproject_description(pyproject: Path) -> str:
    if not pyproject.is_file():
        return ""
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("description"):
            # description = "..."
            _, _, rhs = stripped.partition("=")
            return rhs.strip().strip('"').strip("'")
    return ""


def _git_last_commit(rel_path: str) -> str:
    """Return the committer date (YYYY-MM-DD) of the most-recent commit
    touching ``rel_path``. Deliberately does NOT include the commit SHA:
    rebasing a split PR rewrites SHAs and would cause the
    ``Check STATUS.md is current`` CI gate to fail spuriously. The date
    is stable across rebases; the SHA is not.
    """
    full_path = (REPO_ROOT / rel_path).resolve()
    if not full_path.exists():
        return ""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cs", "--", rel_path],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return out.strip()


def render(reports: list[Report]) -> str:
    lines: list[str] = [
        "# Noesis — Component Status",
        "",
        "> **Auto-generated** by `tools/generate_status.py`. Do not edit by hand.",
        "> Regenerated on every push to master by `.github/workflows/status.yml`.",
        "",
        "This report is filesystem-derived: presence of a Dockerfile, "
        "`railway.toml`, an MCP server, a CI workflow, and line-count "
        "shape. It does NOT speak to live Railway deploy health or CI "
        "pass/fail — those require auth. For authoritative status see "
        "the `Deployments` tab on Railway and the `Actions` tab on "
        "GitHub.",
        "",
        "See [`docs/architect-review-2026-04-23.md`](docs/architect-review-2026-04-23.md) "
        "for the most recent architectural read.",
        "",
        "## Services",
        "",
    ]
    lines.extend(_render_section([r for r in reports if r.role == "service"]))
    lines.extend([
        "",
        "## Cross-cutting packages",
        "",
    ])
    lines.extend(_render_section([r for r in reports if r.role == "cross-cutting"]))
    lines.extend([
        "",
        "## UI clients",
        "",
    ])
    lines.extend(_render_section([r for r in reports if r.role == "ui"]))
    lines.extend([
        "",
        "## Legend",
        "",
        "- **Docker / Railway / pyproject / MCP / CI** — checkmark means the "
        "file or workflow exists on disk. Missing markers are real gaps.",
        "- **src LOC / test LOC / tests** — raw line counts (excluding "
        "`__pycache__`) and count of `test_*.py` files. Fast health "
        "signal, not a substitute for actually running the suite.",
        "- **Last commit** — `git log -1` on the component's directory.",
        "",
    ])
    return "\n".join(lines)


def _render_section(reports: list[Report]) -> list[str]:
    if not reports:
        return ["_(none)_"]
    header = (
        "| Name | Description | Docker | Railway | MCP | CI | src LOC | "
        "test LOC | tests | Last commit |"
    )
    sep = (
        "|------|-------------|:------:|:-------:|:---:|:--:|--------:|"
        "---------:|------:|-------------|"
    )
    lines = [header, sep]
    for r in sorted(reports, key=lambda x: x.name):
        ci_cell = (
            f"[{r.mark(True)}]({r.ci_workflow_path})"
            if r.ci_workflow_path
            else r.mark(False)
        )
        lines.append(
            "| "
            + " | ".join((
                f"**{r.name}**",
                r.description or "—",
                r.mark(r.has_dockerfile),
                r.mark(r.has_railway),
                r.mark(r.has_mcp_server),
                ci_cell,
                f"{r.src_loc:,}" if r.src_loc else "—",
                f"{r.test_loc:,}" if r.test_loc else "—",
                str(r.test_file_count) if r.test_file_count else "—",
                r.last_commit or "—",
            ))
            + " |"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate STATUS.md from filesystem state.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the generated file differs from STATUS.md "
             "(for CI drift detection).",
    )
    parser.add_argument(
        "--output",
        default=str(STATUS_PATH),
        help="Where to write the report (default: STATUS.md at repo root).",
    )
    args = parser.parse_args(argv)

    reports = [scan(name, path, role) for name, path, role in COMPONENTS]
    rendered = render(reports)

    if args.check:
        current = Path(args.output).read_text(encoding="utf-8") if Path(args.output).is_file() else ""
        if current != rendered:
            print(
                f"{args.output} is out of date. Run "
                "`python tools/generate_status.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{args.output} is up to date.")
        return 0

    Path(args.output).write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

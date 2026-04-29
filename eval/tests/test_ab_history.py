"""Tests for the ``ab history`` subcommand.

Pins:

* Discovery: walks immediate subdirs, skips dirs without exactly
  two JSONL files, prints a stderr warning for skipped dirs so
  silent data loss is impossible.
* Per-run rows: one row per valid run, treatment/baseline
  assignment follows each run's own ``delta.json`` (not the
  alphabetical filename), so weeks-long histories stay consistent
  even when the wrapper is invoked with different arg orders.
* Pooling: concat every treatment + every baseline episode across
  the whole tree, compute one ``SuiteDelta``. The pooled success
  rates must match the per-run rates when all runs are identical
  (e.g. oracle deterministically clearing 4/5 = 0.800 on every
  replay of the default suite), and the pooled role assignment
  follows the *majority* of per-run treatments rather than
  alphabetical sorting.
* Error paths: missing directory, no runs found, >2 distinct
  agent names across the tree — each surfaces a usable message
  instead of a silent zero-row output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from noesis_eval.ab.cli import main
from noesis_eval.ab.results import EpisodeResult

pytestmark = pytest.mark.unit


def _episode(
    agent: str, task_id: str, success: bool, seed: int = 0
) -> dict[str, object]:
    return EpisodeResult(
        agent=agent,
        task_id=task_id,
        success=success,
        steps_taken=1,
        failures_seen=0,
        failures_recovered=0,
        final_reward=1.0 if success else 0.0,
        seed=seed,
    ).to_dict()


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )


def _write_run(
    root: Path,
    run_name: str,
    treatment_name: str,
    baseline_name: str,
    task_wins: list[tuple[str, bool, bool]],
    *,
    drop_delta_json: bool = False,
) -> Path:
    """Materialise an ``ab-run`` directory layout.

    ``task_wins`` is a list of ``(task_id, treatment_success,
    baseline_success)`` tuples — one per task. The helper writes
    one JSONL per side plus a ``delta.json`` that pins who played
    the treatment role (which ``history`` uses to disambiguate).
    """
    run_dir = root / run_name
    run_dir.mkdir(parents=True)
    _write_jsonl(
        run_dir / f"{treatment_name}.jsonl",
        [_episode(treatment_name, tid, ok) for tid, ok, _ in task_wins],
    )
    _write_jsonl(
        run_dir / f"{baseline_name}.jsonl",
        [_episode(baseline_name, tid, ok) for tid, _, ok in task_wins],
    )
    if not drop_delta_json:
        (run_dir / "delta.json").write_text(
            json.dumps({"treatment": treatment_name, "baseline": baseline_name}),
            encoding="utf-8",
        )
    return run_dir


# ── happy paths ──────────────────────────────────────────────────────────────


def test_history_prints_one_row_per_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Three runs with oracle crushing null on 4/5 tasks → three
    per-run rows with identical deltas. Rough shape assertions
    only; format-details live in the column-header test below."""
    for i in (1, 2, 3):
        _write_run(
            tmp_path,
            f"run-{i}",
            "oracle",
            "null",
            [(f"t{j}", j < 4, False) for j in range(5)],
        )

    rc = main(["history", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "run-1" in out
    assert "run-2" in out
    assert "run-3" in out
    # Delta is +0.800 on every row.
    assert out.count("+0.800") >= 3


def test_history_pooled_row_uses_majority_treatment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the per-run delta.json files consistently stamp
    ``oracle`` as treatment (alphabetically *after* ``null``), the
    pooled summary must still print oracle as treatment — otherwise
    the sign of the pooled delta would flip relative to the
    per-run rows."""
    for i in (1, 2, 3):
        _write_run(
            tmp_path,
            f"run-{i}",
            "oracle",
            "null",
            [(f"t{j}", j < 4, False) for j in range(5)],
        )

    rc = main(["history", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Pooled across all runs:" in out
    assert "treatment (oracle) vs baseline (null)" in out
    # Sign is positive because oracle is the treatment side.
    assert "delta:             +0.800" in out


def test_history_pooled_episode_count_reflects_all_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Three runs × 5 tasks = 15 episodes per side in the pooled
    output. Episode-count is the headline reason to use `history`
    — pin it so a refactor can't silently drop pooling."""
    for i in (1, 2, 3):
        _write_run(
            tmp_path,
            f"run-{i}",
            "oracle",
            "null",
            [(f"t{j}", j < 4, False) for j in range(5)],
        )

    rc = main(["history", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "treatment=15 episodes" in out
    assert "baseline=15" in out


# ── discovery / error paths ──────────────────────────────────────────────────


def test_history_skips_subdirs_without_two_jsonls(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An incomplete run (e.g. treatment JSONL only) must be
    skipped, not crash the command — but the user needs to see
    *which* dir was skipped so they can investigate."""
    _write_run(
        tmp_path,
        "good",
        "oracle",
        "null",
        [(f"t{i}", True, False) for i in range(3)],
    )
    (tmp_path / "broken").mkdir()
    _write_jsonl(
        tmp_path / "broken" / "oracle.jsonl",
        [_episode("oracle", "t1", True)],
    )  # only one JSONL — skip

    rc = main(["history", str(tmp_path)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "broken" in err
    assert "expected 2" in err


def test_history_rejects_nonexistent_dir(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="not a directory"):
        main(["history", str(tmp_path / "does-not-exist")])


def test_history_rejects_dir_with_no_valid_runs(tmp_path: Path) -> None:
    """Directory with only skip-worthy subdirs → SystemExit with
    a useful message rather than a bare zero-row table."""
    (tmp_path / "junk").mkdir()  # no JSONLs
    with pytest.raises(SystemExit, match="no valid ab run"):
        main(["history", str(tmp_path)])


def test_history_skips_pooled_row_when_too_many_agents(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two weeks of different agent pairs (oracle vs null, then
    mcp-treatment vs mcp-baseline) — pooling would mix apples and
    oranges. Must refuse to emit a pooled delta, and say why."""
    _write_run(
        tmp_path,
        "week1",
        "oracle",
        "null",
        [(f"t{i}", i < 4, False) for i in range(5)],
    )
    _write_run(
        tmp_path,
        "week2",
        "mcp-treatment",
        "mcp-baseline",
        [(f"t{i}", i < 3, False) for i in range(5)],
    )

    rc = main(["history", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    # Per-run table rendered.
    assert "week1" in out
    assert "week2" in out
    # But pooled row refused.
    assert "Pooled across all runs" not in out
    assert "4 distinct agent names" in err or "4 distinct" in err


# ── treatment/baseline disambiguation ────────────────────────────────────────


def test_history_uses_delta_json_to_choose_treatment_side(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Filename alphabetical order would put ``null.jsonl`` first
    (before ``oracle.jsonl``), so without the ``delta.json``
    hint the per-run row would label null as treatment. Pin that
    the hint is read and respected."""
    _write_run(
        tmp_path,
        "run-1",
        "oracle",
        "null",
        [(f"t{i}", i < 4, False) for i in range(5)],
    )

    rc = main(["history", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    # Treatment column on the row should be oracle, not null.
    # Exact column widths are load-bearing; assert substring only.
    assert "+0.800" in out
    # Pooled row confirms it.
    assert "treatment (oracle) vs baseline (null)" in out


def test_history_falls_back_to_alphabetical_when_delta_json_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Runs without a ``delta.json`` (e.g. hand-assembled from
    concatenated JSONLs) fall back to alphabetical filename order.
    Documented behaviour — not ideal, but predictable."""
    _write_run(
        tmp_path,
        "run-1",
        "oracle",
        "null",
        [(f"t{i}", i < 4, False) for i in range(5)],
        drop_delta_json=True,
    )

    rc = main(["history", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    # Alphabetically null comes first, so null ends up on the
    # treatment column and delta is -0.800.
    assert "-0.800" in out

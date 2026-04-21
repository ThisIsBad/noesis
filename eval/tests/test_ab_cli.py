"""Unit tests for the A/B CLI.

Covers:
    * ``run`` writes one JSONL line per episode, columns match
      ``EpisodeResult`` fields.
    * ``run`` with no ``--output`` streams JSONL to stdout.
    * ``diff`` loads two JSONL files, pairs them, and prints the
      SuiteDelta summary.
    * Invalid JSON or agent-name mismatch inside a JSONL file fails
      loudly with a pointer to the bad line.
    * Unknown agent / suite names fail with usable error messages
      (argparse handles suite, the run dispatcher handles agent).
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from noesis_eval.ab.cli import build_parser, main
from noesis_eval.ab.results import EpisodeResult

pytestmark = pytest.mark.unit


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_oracle_writes_one_jsonl_line_per_episode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "oracle.jsonl"
    rc = main(["run", "oracle", "--suite", "default", "--output", str(out)])
    assert rc == 0

    lines = [ln for ln in out.read_text().splitlines() if ln.strip()]
    records = [json.loads(ln) for ln in lines]
    assert records, "expected at least one episode recorded"
    fields = set(records[0].keys())
    expected = {
        "agent", "task_id", "success", "steps_taken",
        "failures_seen", "failures_recovered", "final_reward",
        "seed",
    }
    assert fields == expected

    # Oracle clears the default suite, so every record should be success.
    assert all(r["agent"] == "oracle" for r in records)
    unsolvable = "t5_unrecoverable_locked_room"
    assert all(r["success"] for r in records if r["task_id"] != unsolvable)

    # Summary goes to stderr so stdout stays machine-parseable.
    err = capsys.readouterr().err
    assert "oracle:" in err
    assert "success" in err


def test_run_streams_to_stdout_when_no_output_given(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["run", "null", "--suite", "default"])
    assert rc == 0
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    # NullAgent never wins, so every record must be success=false.
    assert lines
    for ln in lines:
        record = json.loads(ln)
        assert record["agent"] == "null"
        assert record["success"] is False


def test_run_rejects_unknown_agent(tmp_path: Path) -> None:
    out = tmp_path / "x.jsonl"
    with pytest.raises(SystemExit, match="unknown agent"):
        main(["run", "definitely-not-an-agent", "--output", str(out)])


def test_run_rejects_unknown_suite() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "oracle", "--suite", "not-a-suite"])


def test_run_creates_parent_directory_if_missing(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "deep" / "results.jsonl"
    rc = main(["run", "null", "--output", str(out)])
    assert rc == 0
    assert out.exists()


# ── diff ──────────────────────────────────────────────────────────────────────


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _episode_dict(
    agent: str, task_id: str, success: bool
) -> dict[str, object]:
    return EpisodeResult(
        agent=agent,
        task_id=task_id,
        success=success,
        steps_taken=1,
        failures_seen=0,
        failures_recovered=0,
        final_reward=1.0 if success else 0.0,
    ).to_dict()


def test_diff_reports_wins_losses_and_delta(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    treatment = tmp_path / "t.jsonl"
    baseline = tmp_path / "b.jsonl"
    _write_jsonl(treatment, [
        _episode_dict("oracle", "t1", True),
        _episode_dict("oracle", "t2", True),
        _episode_dict("oracle", "t3", False),
    ])
    _write_jsonl(baseline, [
        _episode_dict("null", "t1", False),  # treatment wins
        _episode_dict("null", "t2", True),   # tie
        _episode_dict("null", "t3", False),  # tie on fail
    ])

    rc = main(["diff", str(treatment), str(baseline)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "treatment (oracle) vs baseline (null)" in out
    assert "shared tasks:      3" in out
    assert "wins:   1" in out
    assert "losses: 0" in out
    assert "delta:" in out
    # treatment 2/3 - baseline 1/3 = +1/3 ≈ 0.333
    assert "+0.333" in out
    assert "p-value:" in out
    assert "95% CI" in out


def test_diff_surfaces_only_one_side_task_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    treatment = tmp_path / "t.jsonl"
    baseline = tmp_path / "b.jsonl"
    _write_jsonl(treatment, [
        _episode_dict("oracle", "shared", True),
        _episode_dict("oracle", "only_t", True),
    ])
    _write_jsonl(baseline, [
        _episode_dict("null", "shared", False),
        _episode_dict("null", "only_b", False),
    ])

    rc = main(["diff", str(treatment), str(baseline)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "only in treatment (1)" in out
    assert "only_t" in out
    assert "only in baseline (1)" in out
    assert "only_b" in out


def test_diff_rejects_jsonl_with_mixed_agent_names(tmp_path: Path) -> None:
    treatment = tmp_path / "mixed.jsonl"
    baseline = tmp_path / "b.jsonl"
    _write_jsonl(treatment, [
        _episode_dict("oracle", "t1", True),
        _episode_dict("null", "t2", False),
    ])
    _write_jsonl(baseline, [_episode_dict("null", "t1", False)])

    with pytest.raises(SystemExit, match="multiple agents"):
        main(["diff", str(treatment), str(baseline)])


def test_diff_points_at_line_number_on_bad_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps(_episode_dict("oracle", "t1", True))
        + "\n{not valid json\n"
    )
    ok = tmp_path / "ok.jsonl"
    _write_jsonl(ok, [_episode_dict("null", "t1", False)])

    with pytest.raises(SystemExit, match=r"bad\.jsonl:2:"):
        main(["diff", str(bad), str(ok)])


def test_diff_rejects_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    ok = tmp_path / "ok.jsonl"
    _write_jsonl(ok, [_episode_dict("null", "t1", False)])

    with pytest.raises(SystemExit, match="no episodes recorded"):
        main(["diff", str(empty), str(ok)])


# ── round trip ────────────────────────────────────────────────────────────────


def test_run_then_diff_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: `run oracle` + `run null` + `diff` yields the same
    signal ``run_ab`` gives in-process."""
    oracle_out = tmp_path / "oracle.jsonl"
    null_out = tmp_path / "null.jsonl"
    assert main(["run", "oracle", "--output", str(oracle_out)]) == 0
    assert main(["run", "null", "--output", str(null_out)]) == 0
    capsys.readouterr()  # drop run summaries

    assert main(["diff", str(oracle_out), str(null_out)]) == 0
    summary = capsys.readouterr().out
    assert "treatment (oracle) vs baseline (null)" in summary
    # Oracle beats Null on every task it can solve; must be > 0 delta.
    assert "delta:             +" in summary


# ── parser smoke tests ───────────────────────────────────────────────────────


def test_parser_requires_subcommand() -> None:
    parser = build_parser()
    # argparse emits SystemExit(2) when a required subcommand is missing.
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_exposes_both_subcommands() -> None:
    parser = build_parser()
    assert parser.parse_args(["run", "oracle"]).command == "run"
    # Need real file args for diff, but argparse doesn't validate existence.
    buf = io.StringIO()
    parser.print_help(buf)
    help_text = buf.getvalue()
    assert "run" in help_text
    assert "diff" in help_text

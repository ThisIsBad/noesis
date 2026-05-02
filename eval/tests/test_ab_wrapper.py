"""Tests for the canonical-A/B wrapper subcommand.

Covers the contract:

* ``ab`` accepts ``--treatment`` / ``--baseline`` / ``--suite`` /
  ``--samples`` / ``--out-dir`` and writes three artifacts:
  ``<treatment>.jsonl``, ``<baseline>.jsonl``, ``delta.json``.
* Both JSONLs hold the right number of episodes given samples × suite,
  and ``delta.json`` is valid JSON containing the expected summary keys.
* The on-stdout summary prints the human-readable delta — same format
  as ``ab diff``.
* Unknown agent names abort *before* either side runs, so a typo in
  ``--baseline`` doesn't waste budget on the treatment side.
* Identical treatment/baseline emits a stderr warning (it's not an
  error: the user might be measuring noise on purpose) but proceeds.
* ``--samples 0`` is rejected with a useful message.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from noesis_eval.ab.cli import main

pytestmark = pytest.mark.unit


def test_ab_writes_treatment_baseline_and_delta_artifacts(
    tmp_path: Path,
) -> None:
    """One invocation produces three files in --out-dir, named after
    the agents and ``delta.json``. Episode counts match samples × suite.
    """
    out_dir = tmp_path / "ab"
    rc = main(
        [
            "ab",
            "--treatment",
            "oracle",
            "--baseline",
            "null",
            "--suite",
            "default",
            "--samples",
            "2",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0

    treatment_jsonl = out_dir / "oracle.jsonl"
    baseline_jsonl = out_dir / "null.jsonl"
    delta_json = out_dir / "delta.json"
    assert treatment_jsonl.exists()
    assert baseline_jsonl.exists()
    assert delta_json.exists()

    # 5 default-suite tasks × 2 samples = 10 lines per side.
    assert len(treatment_jsonl.read_text().splitlines()) == 10
    assert len(baseline_jsonl.read_text().splitlines()) == 10


def test_ab_delta_json_is_valid_and_has_expected_keys(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "ab"
    assert (
        main(
            [
                "ab",
                "--treatment",
                "oracle",
                "--baseline",
                "null",
                "--suite",
                "default",
                "--samples",
                "1",
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    summary = json.loads((out_dir / "delta.json").read_text())
    # Headline fields the dashboard / regression-gate logic depends on.
    for key in (
        "treatment",
        "baseline",
        "shared_tasks",
        "treatment_success_rate",
        "baseline_success_rate",
        "delta",
        "delta_ci95",
        "p_value",
        "wins",
        "losses",
        "treatment_tokens_per_episode",
        "baseline_tokens_per_episode",
        "tokens_ratio",
        "treatment_wall_time_per_episode",
        "baseline_wall_time_per_episode",
    ):
        assert key in summary, f"delta.json missing {key!r}"
    assert summary["treatment"] == "oracle"
    assert summary["baseline"] == "null"


def test_ab_creates_out_dir_if_missing(tmp_path: Path) -> None:
    out_dir = tmp_path / "nested" / "deep" / "ab-runs"
    rc = main(
        [
            "ab",
            "--treatment",
            "oracle",
            "--baseline",
            "null",
            "--suite",
            "default",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    assert out_dir.exists()


def test_ab_prints_human_summary_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "ab"
    assert (
        main(
            [
                "ab",
                "--treatment",
                "oracle",
                "--baseline",
                "null",
                "--suite",
                "default",
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    # Human-readable header + the cost / wall-time lines from diff.
    assert "treatment (oracle) vs baseline (null)" in out
    assert "p-value:" in out
    assert "cost (tokens/episode):" in out
    assert "wall time (s/episode):" in out


def test_ab_rejects_unknown_treatment_before_running(
    tmp_path: Path,
) -> None:
    """Typo in --treatment must fail before any episodes run; the
    test asserts the JSONL files were never written, so we know
    no budget would have been burned."""
    out_dir = tmp_path / "ab"
    with pytest.raises(SystemExit, match="unknown agent"):
        main(
            [
                "ab",
                "--treatment",
                "definitely-not-an-agent",
                "--baseline",
                "null",
                "--suite",
                "default",
                "--out-dir",
                str(out_dir),
            ]
        )
    # Side effect check: out_dir gets created by argparse handling but
    # neither agent JSONL should exist.
    assert not (out_dir / "definitely-not-an-agent.jsonl").exists()
    assert not (out_dir / "null.jsonl").exists()


def test_ab_rejects_unknown_baseline_before_treatment_runs(
    tmp_path: Path,
) -> None:
    """Same protection on --baseline: a misspelled baseline name must
    not waste a treatment run first."""
    out_dir = tmp_path / "ab"
    with pytest.raises(SystemExit, match="unknown agent"):
        main(
            [
                "ab",
                "--treatment",
                "oracle",
                "--baseline",
                "definitely-not-an-agent",
                "--suite",
                "default",
                "--out-dir",
                str(out_dir),
            ]
        )
    # Treatment must NOT have been written either.
    assert not (out_dir / "oracle.jsonl").exists()


def test_ab_rejects_zero_samples(tmp_path: Path) -> None:
    out_dir = tmp_path / "ab"
    with pytest.raises(SystemExit, match="--samples"):
        main(
            [
                "ab",
                "--treatment",
                "oracle",
                "--baseline",
                "null",
                "--suite",
                "default",
                "--samples",
                "0",
                "--out-dir",
                str(out_dir),
            ]
        )


def test_ab_warns_when_treatment_equals_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Self-A/B is legal (variance measurement) but is almost always
    a typo; we warn loudly to stderr so the user sees it without
    failing the run."""
    out_dir = tmp_path / "ab"
    assert (
        main(
            [
                "ab",
                "--treatment",
                "null",
                "--baseline",
                "null",
                "--suite",
                "default",
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    err = capsys.readouterr().err
    assert "noise" in err.lower() or "same" in err.lower() or "both" in err.lower()


def test_ab_default_out_dir_is_ab_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default ``--out-dir`` is the literal string ``ab-runs`` — pin
    that so the runbook + dashboard / artifact-upload step can rely on
    it without a flag."""
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "ab",
                "--treatment",
                "oracle",
                "--baseline",
                "null",
                "--suite",
                "default",
            ]
        )
        == 0
    )
    assert (tmp_path / "ab-runs" / "oracle.jsonl").exists()
    assert (tmp_path / "ab-runs" / "null.jsonl").exists()
    assert (tmp_path / "ab-runs" / "delta.json").exists()


def test_ab_default_suite_is_stage3(
    tmp_path: Path,
) -> None:
    """Default ``--suite`` is stage3 (50 tasks) so the canonical
    invocation is just ``ab --treatment ... --baseline ...`` without
    needing to remember which suite is "the" one."""
    out_dir = tmp_path / "ab"
    assert (
        main(
            [
                "ab",
                "--treatment",
                "oracle",
                "--baseline",
                "null",
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    # Stage3 has 50 tasks; with default samples=1 → 50 lines per side.
    assert len((out_dir / "oracle.jsonl").read_text().splitlines()) == 50


def test_ab_overwrites_existing_artifacts(tmp_path: Path) -> None:
    """Re-running ``ab`` to the same out-dir replaces the JSONLs and
    delta.json wholesale — no append, no stale partial data carried
    forward from a previous failed run."""
    out_dir = tmp_path / "ab"
    out_dir.mkdir()
    (out_dir / "oracle.jsonl").write_text("STALE GARBAGE\n")
    (out_dir / "delta.json").write_text("STALE GARBAGE")

    assert (
        main(
            [
                "ab",
                "--treatment",
                "oracle",
                "--baseline",
                "null",
                "--suite",
                "default",
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    assert "STALE" not in (out_dir / "oracle.jsonl").read_text()
    # delta.json must round-trip through json.loads now — no garbage.
    json.loads((out_dir / "delta.json").read_text())

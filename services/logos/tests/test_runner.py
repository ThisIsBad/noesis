"""Direct tests for logos.runner."""

from __future__ import annotations

from logos.models import Argument, Proposition, VerificationResult
from logos.runner import BenchmarkRunner, ProblemResult, format_report


def test_problem_result_sets_verifier_correct_flag():
    verification = VerificationResult(valid=True, rule="Identity", explanation="ok")
    result = ProblemResult(
        problem_id="L1-01",
        level=1,
        category="sanity",
        natural_language="P therefore P",
        expected_valid=True,
        actual_valid=True,
        verification=verification,
    )

    assert result.verifier_correct is True


def test_format_report_includes_failure_details():
    good = ProblemResult(
        problem_id="L1-01",
        level=1,
        category="sanity",
        natural_language="P therefore P",
        expected_valid=True,
        actual_valid=True,
        verification=VerificationResult(valid=True, rule="Identity", explanation="ok"),
    )
    bad = ProblemResult(
        problem_id="L1-02",
        level="challenge",
        category="fallacy",
        natural_language="If P then Q; Q therefore P",
        expected_valid=False,
        actual_valid=True,
        verification=VerificationResult(
            valid=True,
            rule="Wrong",
            explanation="incorrectly marked valid",
            counterexample={"P": False, "Q": True},
        ),
    )

    report = format_report([good, bad])

    assert "Overall: 1/2 correct" in report
    assert "Failure Details" in report
    assert "L1-02" in report
    assert "Counterexample" in report


def test_runner_run_all_uses_loader_and_verifier(monkeypatch):
    import logos.runner as runner_mod

    argument = Argument(premises=[Proposition("P")], conclusion=Proposition("P"), natural_language="P therefore P")
    meta = {
        "id": "L1-01",
        "level": 1,
        "category": "sanity",
        "expected_valid": True,
        "natural_language": "P therefore P",
    }

    monkeypatch.setattr(runner_mod, "load_problems", lambda: [{"id": "L1-01"}])
    monkeypatch.setattr(runner_mod, "parse_problem", lambda _raw: (argument, meta))

    class _FakeVerifier:
        def verify(self, _argument):
            return VerificationResult(valid=True, rule="Identity", explanation="ok")

    runner = BenchmarkRunner()
    runner.verifier = _FakeVerifier()

    results = runner.run_all()
    assert len(results) == 1
    assert results[0].problem_id == "L1-01"
    assert results[0].verifier_correct is True

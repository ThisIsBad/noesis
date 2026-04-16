from empiria.core import EmpiriaCore


def test_record_and_retrieve():
    core = EmpiriaCore()
    core.record(
        context="deploy service",
        action_taken="restart container",
        outcome="service recovered",
        success=True,
        lesson_text="Restart fixes transient deploy failures",
        domain="devops",
    )
    results = core.retrieve("deploy", domain="devops")
    assert len(results) == 1
    assert results[0].success


def test_retrieve_sorted_by_confidence():
    core = EmpiriaCore()
    core.record("deploy", "action1", "ok", True, "lesson1", confidence=0.3)
    core.record("deploy", "action2", "ok", True, "lesson2", confidence=0.9)
    results = core.retrieve("deploy")
    assert results[0].confidence > results[1].confidence


def test_successful_patterns():
    core = EmpiriaCore()
    core.record("ctx", "a", "ok", True, "worked", domain="x")
    core.record("ctx", "b", "fail", False, "failed", domain="x")
    patterns = core.successful_patterns(domain="x")
    assert len(patterns) == 1
    assert patterns[0].success

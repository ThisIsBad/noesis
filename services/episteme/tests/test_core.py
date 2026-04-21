from episteme.core import EpistemeCore


def test_log_and_resolve_prediction():
    core = EpistemeCore()
    pred = core.log_prediction(
        "It will rain tomorrow", confidence=0.8, domain="weather"
    )
    assert pred.correct is None
    resolved = core.log_outcome(pred.prediction_id, correct=True)
    assert resolved.correct is True


def test_calibration_perfect():
    core = EpistemeCore()
    for _ in range(10):
        pred = core.log_prediction("claim", confidence=1.0)
        core.log_outcome(pred.prediction_id, correct=True)
    report = core.get_calibration()
    assert report.ece < 0.01
    assert report.sample_size == 10


def test_calibration_overconfident():
    core = EpistemeCore()
    for _ in range(10):
        pred = core.log_prediction("claim", confidence=0.9)
        core.log_outcome(pred.prediction_id, correct=False)
    report = core.get_calibration()
    assert report.bias > 0.5


def test_should_escalate_low_confidence():
    core = EpistemeCore()
    assert core.should_escalate(confidence=0.3)
    assert not core.should_escalate(confidence=0.8)


def test_competence_map_empty():
    core = EpistemeCore()
    cmap = core.get_competence_map()
    assert cmap.total_predictions == 0
    assert cmap.domains == []
    assert cmap.weaknesses == []
    assert cmap.strengths == []


def test_competence_map_skips_unresolved_and_undomained():
    core = EpistemeCore()
    # Unresolved — excluded.
    core.log_prediction("a", confidence=0.9, domain="weather")
    # No domain — excluded.
    pred = core.log_prediction("b", confidence=0.9)
    core.log_outcome(pred.prediction_id, correct=True)
    cmap = core.get_competence_map()
    assert cmap.total_predictions == 0


def test_competence_map_flags_overconfident_domain_as_weakness():
    core = EpistemeCore()
    for _ in range(12):
        p = core.log_prediction("claim", confidence=0.9, domain="chess")
        core.log_outcome(p.prediction_id, correct=False)
    # A well-calibrated domain with enough samples.
    for i in range(12):
        p = core.log_prediction("claim", confidence=0.8, domain="weather")
        core.log_outcome(p.prediction_id, correct=(i < 10))  # 10/12 ≈ 0.83

    cmap = core.get_competence_map(min_samples=10, weakness_threshold=0.15)
    assert cmap.total_predictions == 24
    assert "chess" in cmap.weaknesses
    assert "chess" not in cmap.strengths
    assert "weather" in cmap.strengths
    assert "weather" not in cmap.weaknesses

    chess_stats = next(d for d in cmap.domains if d.domain == "chess")
    assert chess_stats.accuracy == 0.0
    assert chess_stats.confidence_gap > 0.15


def test_competence_map_respects_min_samples_threshold():
    core = EpistemeCore()
    # Only 3 samples — below default min_samples=10.
    for _ in range(3):
        p = core.log_prediction("x", confidence=0.99, domain="niche")
        core.log_outcome(p.prediction_id, correct=False)
    cmap = core.get_competence_map(min_samples=10)
    # Domain shows up in stats but is not labelled a weakness.
    assert any(d.domain == "niche" for d in cmap.domains)
    assert "niche" not in cmap.weaknesses
    assert "niche" not in cmap.strengths


def test_competence_map_weaknesses_ranked_by_gap():
    core = EpistemeCore()
    # Worst gap: chess (conf 0.95, acc 0.0)
    for _ in range(10):
        p = core.log_prediction("c", confidence=0.95, domain="chess")
        core.log_outcome(p.prediction_id, correct=False)
    # Moderate gap: poker (conf 0.8, acc ~0.5)
    for i in range(10):
        p = core.log_prediction("p", confidence=0.8, domain="poker")
        core.log_outcome(p.prediction_id, correct=(i < 5))

    cmap = core.get_competence_map(min_samples=10, weakness_threshold=0.15)
    assert cmap.weaknesses == ["chess", "poker"]

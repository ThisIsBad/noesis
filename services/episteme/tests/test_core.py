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

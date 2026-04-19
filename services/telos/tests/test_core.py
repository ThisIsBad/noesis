from noesis_schemas import GoalConstraint, GoalContract

from telos.core import TelosCore


def test_register_and_list_active():
    core = TelosCore()
    contract = GoalContract(
        description="Never delete user data",
        postconditions=[GoalConstraint(description="not delete user data")],
    )
    core.register(contract)
    assert len(core.list_active()) == 1


def test_aligned_action():
    core = TelosCore()
    contract = GoalContract(description="Serve users well")
    core.register(contract)
    result = core.check_alignment("Send a helpful response to the user")
    assert result.aligned
    assert result.drift_score == 0.0


def test_drift_score_accumulates():
    core = TelosCore()
    for _ in range(5):
        core.check_alignment("neutral action")
    assert core.get_drift_score() == 0.0


def test_no_goals_always_aligned():
    core = TelosCore()
    result = core.check_alignment("anything")
    assert result.aligned

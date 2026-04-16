from kosmos.core import KosmosCore


def test_add_edge_and_intervention():
    core = KosmosCore()
    core.add_edge("rain", "wet_ground", strength=0.9)
    core.add_edge("wet_ground", "slippery", strength=0.8)
    downstream = core.compute_intervention("rain", True)
    assert "wet_ground" in downstream
    assert "slippery" in downstream
    assert downstream["slippery"] < downstream["wet_ground"]


def test_query_causes():
    core = KosmosCore()
    core.add_edge("fire", "smoke")
    core.add_edge("volcano", "smoke")
    causes = core.query_causes("smoke")
    assert set(causes) == {"fire", "volcano"}


def test_counterfactual_path():
    core = KosmosCore()
    core.add_edge("A", "B", strength=0.5)
    core.add_edge("B", "C", strength=0.5)
    result = core.counterfactual("A", "C")
    assert result is not None
    assert abs(result - 0.25) < 0.01


def test_counterfactual_no_path():
    core = KosmosCore()
    core.add_edge("X", "Y")
    assert core.counterfactual("Y", "X") is None

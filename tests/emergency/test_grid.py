import pytest

from prl.emergency import grid


def test_la_grilla_tiene_162_variantes_unicas_y_ordenadas():
    g = grid.build_grid()
    assert len(g) == 162
    assert len({v["variant_id"] for v in g}) == 162
    assert g[0]["weights"] == "equal" and g[0]["theta"] == 0.5 and g[0]["k"] == 2
    assert g[0]["m"] == 5 and g[0]["destination"] == "TLT"
    assert g[-1]["weights"] == "tvc2" and g[-1]["theta"] == 1.5 and g[-1]["k"] == 5
    assert g[-1]["m"] == 20 and g[-1]["destination"] == "MIX"
    assert {v["destination"] for v in g} == {"TLT", "CASH", "MIX"}
    assert {v["theta"] for v in g} == {0.5, 1.0, 1.5}


def test_pesos_de_dimensiones():
    eq = grid.dimension_weights("equal")
    tv = grid.dimension_weights("tvc2")
    assert set(eq) == {"trend", "vol", "correlation", "credit", "breadth", "drawdown_velocity"}
    assert all(v == 1.0 for v in eq.values())
    assert tv["trend"] == tv["vol"] == tv["credit"] == 2.0
    assert tv["correlation"] == tv["breadth"] == tv["drawdown_velocity"] == 1.0
    with pytest.raises(ValueError):
        grid.dimension_weights("otro")


def test_pesos_de_destino():
    assert grid.destination_weights("TLT") == {"TLT": 1.0}
    assert grid.destination_weights("CASH") == {"CASH": 1.0}
    assert grid.destination_weights("MIX") == {"TLT": 0.5, "CASH": 0.5}
    with pytest.raises(ValueError):
        grid.destination_weights("XYZ")

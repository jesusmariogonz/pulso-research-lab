import numpy as np
import pandas as pd

from prl.short_pressure.baselines import (
    baseline_buy_hold,
    baseline_caida_simple,
    baseline_combo_ingenuo,
    baseline_price_exhaustion,
    baseline_short_pressure,
)


def test_baseline_buy_hold():
    r = baseline_buy_hold(["AAA", "BBB", "CCC"])
    assert list(r.index) == ["AAA", "BBB", "CCC"]
    assert r.all()


def test_baseline_caida_simple_limite_inclusivo_y_nan():
    tabla = pd.DataFrame({"ret_5d": [-0.15, -0.10, -0.05, np.nan]}, index=["A", "B", "C", "D"])
    r = baseline_caida_simple(tabla)
    assert list(r[r].index) == ["A", "B"]
    assert r.loc["D"] == False


def test_baseline_price_exhaustion_limite_inclusivo():
    tabla = pd.DataFrame({"PRICE_EXHAUSTION_SCORE": [0.05, 0.10, 0.11, np.nan]}, index=["A", "B", "C", "D"])
    r = baseline_price_exhaustion(tabla)
    assert list(r[r].index) == ["A", "B"]
    assert r.loc["D"] == False


def test_baseline_short_pressure_limite_inclusivo():
    tabla = pd.DataFrame({"SHORT_PRESSURE_SCORE": [0.95, 0.90, 0.89, np.nan]}, index=["A", "B", "C", "D"])
    r = baseline_short_pressure(tabla)
    assert list(r[r].index) == ["A", "B"]
    assert r.loc["D"] == False


def test_baseline_combo_ingenuo_casos():
    tabla = pd.DataFrame({
        "SHORT_PRESSURE_SCORE": [0.95, 0.80, 0.95, 0.95, np.nan],
        "PRICE_EXHAUSTION_SCORE": [0.05, 0.05, 0.50, 0.05, 0.05],
        "confirmacion_a": [True, True, True, False, True],
    }, index=["cumple", "falla_sp", "falla_pe", "falla_conf", "nan"])
    r = baseline_combo_ingenuo(tabla)
    assert r.loc["cumple"] == True
    assert r.loc["falla_sp"] == False
    assert r.loc["falla_pe"] == False
    assert r.loc["falla_conf"] == False
    assert r.loc["nan"] == False

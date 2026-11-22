import numpy as np
import pandas as pd

from prl.reverse_winners import baselines


def test_baseline_momentum_simple_top20():
    simbolos = [f"s{i}" for i in range(10)]
    percentiles = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
    df = pd.DataFrame({"mom_20d": percentiles}, index=simbolos)
    out = baselines.baseline_momentum_simple(df, pct=0.20)
    seleccionados = set(out[out].index)
    assert seleccionados == {"s8", "s9"}


def test_baseline_buy_hold():
    out = baselines.baseline_buy_hold(["AAA", "BBB", "CCC"])
    assert list(out.index) == ["AAA", "BBB", "CCC"]
    assert out.all()
    assert len(out) == 3


def test_baseline_rsi_simple_bottom10():
    simbolos = [f"s{i}" for i in range(10)]
    percentiles = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
    df = pd.DataFrame({"rsi14": percentiles}, index=simbolos)
    out = baselines.baseline_rsi_simple(df, pct=0.10)
    seleccionados = set(out[out].index)
    assert seleccionados == {"s0"}


def test_baseline_combo_ingenuo_casos():
    df = pd.DataFrame(
        {
            "mom_20d": [0.05, 0.05, 0.0, np.nan],
            "dist_sma50": [0.02, -0.01, 0.0, 0.02],
            "vol_relativo_20d": [1.5, 1.5, 1.2, 1.5],
        },
        index=["cumple", "falla_sma", "limite_exacto", "nan_mom"],
    )
    out = baselines.baseline_combo_ingenuo(df)
    assert bool(out.loc["cumple"]) is True
    assert bool(out.loc["falla_sma"]) is False
    assert bool(out.loc["limite_exacto"]) is False
    assert bool(out.loc["nan_mom"]) is False

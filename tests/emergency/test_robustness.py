import numpy as np
import pandas as pd
import pytest

from prl.emergency.backtest import metrics, run_backtest
from prl.emergency.robustness import (cost_sensitivity, exclude_window, reality_check,
                                      required_sample_size, subperiod_metrics)


def _prices(n=300, seed=1):
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(seed)
    spy = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n))
    return pd.DataFrame({"SPY": spy, "TLT": 100 * np.cumprod(1 + rng.normal(0.0001, 0.005, n))}, index=idx)


def _expo(idx):
    e = pd.Series(1.0, index=idx)
    e.iloc[50:120] = 0.5
    e.iloc[120:160] = 0.0
    return e


def test_cost_sensitivity_matches_run_backtest_and_is_monotone():
    p = _prices(); e = _expo(p.index)
    out = cost_sensitivity(p, e, "SPY", {"TLT": 1.0}, [0, 10, 50])
    assert list(out.index) == [0, 10, 50] and out.index.name == "cost_bps"
    assert set(["cagr", "max_drawdown", "calmar", "sharpe"]) <= set(out.columns)
    ref = metrics(run_backtest(p, e, "SPY", {"TLT": 1.0}, 10 / 10000)["ret"])
    assert out.loc[10, "cagr"] == pytest.approx(ref["cagr"])
    assert out.loc[0, "cagr"] > out.loc[10, "cagr"] > out.loc[50, "cagr"]


def test_subperiod_metrics_and_exclude():
    r = pd.Series(np.random.default_rng(0).normal(0.0005, 0.01, 400), index=pd.bdate_range("2020-01-01", periods=400))
    out = subperiod_metrics(r, {"a": ("2020-01-01", "2020-06-30"), "vacia": ("1990-01-01", "1990-12-31")})
    assert out.loc["a", "n_days"] == len(r.loc["2020-01-01":"2020-06-30"])
    assert out.loc["a", "sharpe"] == pytest.approx(metrics(r.loc["2020-01-01":"2020-06-30"])["sharpe"])
    assert out.loc["vacia", "n_days"] == 0 and np.isnan(out.loc["vacia", "cagr"])
    ex = exclude_window(r, "2020-03-01", "2020-03-31")
    assert len(ex) == len(r) - len(r.loc["2020-03-01":"2020-03-31"])
    assert ex.loc["2020-03-01":"2020-03-31"].empty


def test_reality_check_detects_real_edge_and_is_deterministic():
    idx = pd.bdate_range("2015-01-01", periods=1500)
    rng = np.random.default_rng(3)
    bench = pd.Series(rng.normal(0.0, 0.01, 1500), index=idx)
    real = bench + 0.003 + rng.normal(0, 0.002, 1500)
    noise = pd.DataFrame({f"n{i}": bench + rng.normal(0, 0.003, 1500) for i in range(5)}, index=idx)
    r1 = reality_check(pd.concat([noise, real.rename("real")], axis=1), bench, n_boot=300, seed=7)
    r2 = reality_check(pd.concat([noise, real.rename("real")], axis=1), bench, n_boot=300, seed=7)
    assert r1 == r2 and r1["best_variant"] == "real" and r1["p_value"] < 0.05 and r1["n_boot"] == 300
    r3 = reality_check(noise, bench, n_boot=300, seed=7)
    assert r3["p_value"] > 0.05
    with pytest.raises(ValueError):
        reality_check(noise.iloc[:-1], bench, n_boot=10)


def test_required_sample_size():
    assert required_sample_size(0.5, 1.0) == pytest.approx(((1.6448536 + 0.8416212) * 2) ** 2, rel=1e-5)
    assert required_sample_size(0.25, 1.0) == pytest.approx(4 * required_sample_size(0.5, 1.0))
    with pytest.raises(ValueError):
        required_sample_size(0, 1)
    with pytest.raises(ValueError):
        required_sample_size(1, -1)

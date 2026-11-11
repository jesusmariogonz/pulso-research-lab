"""Prueba de integración del orquestador con datos SINTÉTICOS (no son datos de mercado)."""
import json

import numpy as np
import pandas as pd
import pytest

from prl.emergency import exp001

SECTORES = ["XLK", "XLE", "XLF", "XLV", "XLP", "XLU", "XLY", "XLI", "XLB"]


def _precio(idx, seed, mu=0.0003, sd=0.01, inicio=100.0):
    r = np.random.default_rng(seed).normal(mu, sd, len(idx))
    return pd.Series(inicio * np.exp(np.cumsum(r)), index=idx)


@pytest.fixture
def inputs_dir(tmp_path):
    d = tmp_path / "inputs"
    d.mkdir()
    idx = pd.bdate_range("2003-01-01", "2012-12-31")
    spy = _precio(idx, 1)
    # un crash sintético a mitad de muestra para que los estados se activen
    spy.iloc[1500:1560] *= np.linspace(1.0, 0.65, 60)
    spy.iloc[1560:] *= 0.65

    def guarda(nombre, serie, col="adj_close"):
        df = pd.DataFrame({col: serie})
        df.index.name = "date"
        df.to_parquet(d / f"{nombre}.parquet")

    guarda("SPY", spy)
    guarda("RSP", spy * 0.5 * (1 + 0.01 * np.sin(np.arange(len(idx)) / 9)))
    guarda("TLT", _precio(idx, 3, mu=0.0002, sd=0.006))
    guarda("BIL", pd.Series(np.linspace(90, 100, len(idx[1000:])), index=idx[1000:]))
    guarda("VIX", pd.Series(15 + 10 * (spy.pct_change().abs().rolling(10).mean().fillna(0) * 100), index=idx))
    guarda("BAA10Y", pd.Series(2.0 + np.abs(np.sin(np.arange(len(idx)) / 200)), index=idx), col="value")
    guarda("DTB3", pd.Series(2.0, index=idx), col="value")
    for i, s in enumerate(SECTORES):
        guarda(s, _precio(idx, 10 + i))
    return d


EPISODIOS = [{"name": "sintetico", "peak": "2009-01-02", "trough": "2009-03-27"}]


def test_run_escribe_results_con_las_claves_esperadas(inputs_dir, tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    r = exp001.run(inputs_dir, out, first_test_year=2006, n_boot=50, episodes=EPISODIOS)
    guardado = json.loads((out / "results.json").read_text())
    for k in ["experiment", "first_test_year", "oos_start", "oos_end", "n_variants", "n_oos_days", "metrics",
              "calmar_diff_vs_sma200", "episodes", "non_episode_shortfall", "deflated_sharpe",
              "chosen_by_year", "level_fractions", "turnover", "costs_paid", "label", "notes"]:
        assert k in guardado, k
    assert guardado["experiment"] == "EXP-001" and guardado["n_variants"] == 162
    assert set(guardado["metrics"]) == {"model", "buy_hold", "sma200", "sixty_forty"}
    for m in guardado["metrics"].values():
        assert {"cagr", "max_drawdown", "calmar", "sharpe", "sortino", "n_days"} <= set(m)
    assert guardado["label"] in {"VALIDATED", "REJECTED", "INCONCLUSIVE"}
    assert guardado["oos_start"] >= "2006-01-01"
    assert set(guardado["chosen_by_year"]) == {str(y) for y in range(2006, 2013)}
    assert sum(guardado["level_fractions"].values()) == pytest.approx(1.0)
    assert 0.0 <= guardado["deflated_sharpe"] <= 1.0
    assert guardado["calmar_diff_vs_sma200"]["n_boot"] == 50
    assert r["label"] == guardado["label"]


def test_run_es_determinista(inputs_dir, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    exp001.run(inputs_dir, a, first_test_year=2006, n_boot=30, episodes=EPISODIOS)
    exp001.run(inputs_dir, b, first_test_year=2006, n_boot=30, episodes=EPISODIOS)
    assert (a / "results.json").read_text() == (b / "results.json").read_text()


def test_run_falla_con_claridad_si_falta_una_serie(inputs_dir, tmp_path):
    (inputs_dir / "TLT.parquet").unlink()
    out = tmp_path / "run"
    out.mkdir()
    with pytest.raises((FileNotFoundError, ValueError)):
        exp001.run(inputs_dir, out, first_test_year=2006, n_boot=10, episodes=EPISODIOS)

"""Prueba de integración del orquestador con datos SINTÉTICOS (no son datos de mercado)."""
import json

import numpy as np
import pandas as pd
import pytest

from prl.growth_max import exp002
from prl.growth_max.exp002 import escalar_por_regimen


def test_escalar_por_regimen_aplica_k_solo_en_contraccion_sin_importar_el_metodo():
    idx = pd.bdate_range("2020-01-01", periods=4)
    pesos_base = pd.DataFrame({"A": [1.0] * 4, "B": [-0.5] * 4}, index=idx)
    regimen = pd.Series([1.0, 3.0, 4.0, np.nan], index=idx)
    out = escalar_por_regimen(pesos_base, regimen, k=0.5)

    # Día 0: régimen 1.0 (concuerda) -> sin escalar.
    assert out.loc[idx[0], "A"] == pytest.approx(1.0)
    assert out.loc[idx[0], "B"] == pytest.approx(-0.5)
    # Días 1 y 2: contracción (régimen 3/4) -> escalado por k, toda la fila.
    assert out.loc[idx[1], "A"] == pytest.approx(0.5)
    assert out.loc[idx[1], "B"] == pytest.approx(-0.25)
    assert out.loc[idx[2], "A"] == pytest.approx(0.5)
    assert out.loc[idx[2], "B"] == pytest.approx(-0.25)
    # Día 3: régimen NaN -> sin escalar.
    assert out.loc[idx[3], "A"] == pytest.approx(1.0)
    assert out.loc[idx[3], "B"] == pytest.approx(-0.5)

UNIVERSO = [
    "SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "EWJ",
    "XLK", "XLE", "XLF", "XLV", "XLP", "XLU", "XLY", "XLI", "XLB",
    "EWG", "EWQ", "EWU", "EWL", "EWI", "EWP", "EWN", "EWA", "EWH", "EWS",
    "EWZ", "EWW", "EWY", "EWT", "MCHI", "INDA", "EIDO", "EZA", "TUR", "EPOL",
    "MTUM", "QUAL", "USMV", "VLUE",
    "TLT", "IEF", "SHY", "BIL", "HYG", "LQD", "TIP", "EMB", "BNDX", "MBB",
    "GLD", "SLV", "USO", "UNG", "DBC", "DBA",
    "UUP", "FXE", "FXY", "FXB", "FXF", "FXC", "FXA",
    "VNQ", "VNQI",
]


def _precio(idx, seed, mu=0.0003, sd=0.01, inicio=100.0):
    r = np.random.default_rng(seed).normal(mu, sd, len(idx))
    return pd.Series(inicio * np.exp(np.cumsum(r)), index=idx)


@pytest.fixture
def inputs_dir(tmp_path):
    d = tmp_path / "inputs"
    d.mkdir()
    idx = pd.bdate_range("2006-01-01", "2012-12-31")

    for i, ticker in enumerate(UNIVERSO):
        precio = _precio(idx, seed=i, mu=0.0002 + 0.00001 * i, sd=0.008 + 0.0002 * (i % 7))
        df = pd.DataFrame({"adj_close": precio})
        df.index.name = "date"
        df.to_parquet(d / f"{ticker}.parquet")

    dtb3 = pd.DataFrame({"value": pd.Series(2.0, index=idx)})
    dtb3.index.name = "date"
    dtb3.to_parquet(d / "DTB3.parquet")

    def guarda_vintage(nombre, valores_mensuales):
        fechas_obs = pd.date_range("2006-01-01", periods=len(valores_mensuales), freq="MS")
        filas = []
        for fecha, valor in zip(fechas_obs, valores_mensuales):
            filas.append(
                {
                    "obs_date": fecha,
                    "value": float(valor),
                    "realtime_start": fecha + pd.Timedelta(days=20),
                    "realtime_end": pd.Timestamp("9999-12-31"),
                }
            )
        pd.DataFrame(filas).to_parquet(d / f"{nombre}.parquet")

    n_meses = 96
    guarda_vintage("M2", 1000 * np.exp(np.cumsum(np.random.default_rng(100).normal(0.004, 0.002, n_meses))))
    guarda_vintage("FED_BALANCE", 800 * np.exp(np.cumsum(np.random.default_rng(101).normal(0.003, 0.003, n_meses))))
    guarda_vintage("LEADING", 100 + np.cumsum(np.random.default_rng(102).normal(0.05, 0.3, n_meses)))

    return d


def test_run_escribe_results_con_las_claves_esperadas(inputs_dir, tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    r = exp002.run(inputs_dir, out, discovery_end="2009-12-31", validation_end="2010-12-31", n_boot=20, seed=0)
    guardado = json.loads((out / "results.json").read_text())

    for k in [
        "experiment", "variant_id_ganador", "motivo_seleccion", "n_variants",
        "fecha_inicio_backtest", "discovery_end", "validation_end", "n_dias_locked_test",
        "niveles", "comparacion_bootstrap_growth50", "label", "deflated_sharpe",
        "percentil_vs_placebo", "notes",
    ]:
        assert k in guardado, k

    assert guardado["experiment"] == "EXP-002"
    assert guardado["n_variants"] == 17280
    assert guardado["label"] in {"VALIDATED", "REJECTED", "INCONCLUSIVE"}

    if guardado["variant_id_ganador"] is not None:
        assert set(guardado["niveles"]) == {"Conservative", "Growth25", "Growth50", "Growth75", "Max"}
        for nivel in guardado["niveles"].values():
            assert {"cagr", "max_drawdown", "calmar", "sharpe", "sortino", "n_days"} <= set(nivel["metricas"])
            assert set(nivel["probabilidad_ruina"].keys()) == {"0.5", "0.75", "0.9", "0.99"} or set(
                float(k) for k in nivel["probabilidad_ruina"].keys()
            ) == {0.5, 0.75, 0.9, 0.99}

    assert r["label"] == guardado["label"]


def test_run_es_determinista(inputs_dir, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    exp002.run(inputs_dir, a, discovery_end="2009-12-31", validation_end="2010-12-31", n_boot=15, seed=0)
    exp002.run(inputs_dir, b, discovery_end="2009-12-31", validation_end="2010-12-31", n_boot=15, seed=0)
    assert (a / "results.json").read_text() == (b / "results.json").read_text()

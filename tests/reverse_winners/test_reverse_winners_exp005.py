"""Prueba de integración del orquestador con datos SINTÉTICOS (no son datos de mercado)."""
import json

import numpy as np
import pandas as pd
import pytest

from prl.reverse_winners import exp005
from prl.reverse_winners.exp005 import ajustar_ohlc, fechas_t0


def test_fechas_t0_paso_10():
    calendario = pd.bdate_range("2020-01-01", periods=40)
    out = fechas_t0(calendario, inicio="2020-01-01", paso=10)
    assert len(out) == 4
    sub = calendario[calendario >= pd.Timestamp("2020-01-01")]
    assert list(out) == [sub[0], sub[10], sub[20], sub[30]]


def test_ajustar_ohlc_factor_y_division_por_cero():
    df = pd.DataFrame(
        {
            "open": [110.0, 50.0],
            "high": [115.0, 55.0],
            "low": [105.0, 45.0],
            "close": [100.0, 0.0],
            "adj_close": [90.0, 10.0],
            "volume": [1000, 2000],
        }
    )
    out = ajustar_ohlc(df)
    assert out.loc[0, "close"] == 90.0
    assert out.loc[0, "open"] == pytest.approx(99.0)
    assert pd.isna(out.loc[1, "open"])
    assert out.loc[0, "volume"] == 1000


UNIVERSO_SINTETICO = [f"T{i:02d}" for i in range(12)]


def _ohlcv_desde_close(idx, close):
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "adj_close": close,
            "volume": pd.Series(1_000_000.0, index=idx),
        },
        index=idx,
    )


def _precio(idx, seed, mu, sd=0.012, inicio=50.0):
    r = np.random.default_rng(seed).normal(mu, sd, len(idx))
    return pd.Series(inicio * np.exp(np.cumsum(r)), index=idx)


@pytest.fixture
def inputs_dir(tmp_path):
    d = tmp_path / "inputs"
    d.mkdir()
    idx = pd.bdate_range("2015-01-01", "2023-12-31")

    # Benchmark con deriva moderada.
    spy = _precio(idx, seed=999, mu=0.0003, sd=0.009, inicio=100.0)
    df_spy = _ohlcv_desde_close(idx, spy)
    df_spy.index.name = "date"
    df_spy.to_parquet(d / "SPY.parquet")

    # Universo: distintas combinaciones de deriva para que algunos símbolos
    # sean sistemáticamente "ganadores" y otros no, con una feature
    # (momentum) claramente relacionada con quién gana.
    for i, t in enumerate(UNIVERSO_SINTETICO):
        mu = 0.0001 + 0.0004 * (i / len(UNIVERSO_SINTETICO))
        precio = _precio(idx, seed=i, mu=mu, sd=0.010 + 0.001 * (i % 5), inicio=30.0 + i)
        df = _ohlcv_desde_close(idx, precio)
        # Simula un split a mitad de la historia en un par de símbolos: close
        # salta pero adj_close sigue la serie continua.
        if i in (2, 5):
            mitad = len(idx) // 2
            df.loc[idx[mitad:], "close"] = df.loc[idx[mitad:], "close"] * 2.0
            df.loc[idx[mitad:], "open"] = df.loc[idx[mitad:], "open"] * 2.0
            df.loc[idx[mitad:], "high"] = df.loc[idx[mitad:], "high"] * 2.0
            df.loc[idx[mitad:], "low"] = df.loc[idx[mitad:], "low"] * 2.0
        df.index.name = "date"
        df.to_parquet(d / f"{t}.parquet")

    universo_path = tmp_path / "universo.txt"
    universo_path.write_text("\n".join(UNIVERSO_SINTETICO + ["SIN_DATOS"]))

    return d, universo_path


def test_run_escribe_results_con_las_claves_esperadas(inputs_dir, tmp_path):
    d, universo_path = inputs_dir
    out = tmp_path / "run"
    out.mkdir()
    r = exp005.run(
        d, universo_path, out,
        discovery_start="2016-01-01", discovery_end="2019-12-31",
        validation_end="2021-12-31",
        n_boot=20, n_placebos=20, n_particiones_pbo=4, seed=0,
    )
    guardado = json.loads((out / "results.json").read_text())

    for k in [
        "experiment", "n_simbolos_universo", "n_simbolos_con_datos", "fechas_t0",
        "features_discriminantes", "direcciones", "n_variantes_grid_total",
        "n_variantes_sobreviven_filtro_soporte", "variant_id_ganador", "motivo",
        "metricas_locked", "comparacion_bootstrap_vs_baseline1", "dsr", "n_trials_dsr",
        "pbo", "n_variantes_pbo", "concentracion", "leave_one_ticker_out",
        "sensibilidad_vecinos", "placebo", "label", "notes",
    ]:
        assert k in guardado, k

    assert guardado["experiment"] == "EXP-005"
    assert guardado["label"] in {"VALIDATED", "REJECTED", "INCONCLUSIVE"}
    assert r["label"] == guardado["label"]
    assert any("SIN_DATOS" in n for n in guardado["notes"])

    if guardado["variant_id_ganador"] is not None:
        assert set(guardado["metricas_locked"]) == {
            "ganador", "baseline_momentum_simple", "baseline_buy_hold",
            "baseline_rsi_simple", "baseline_combo_ingenuo",
        }
        for m in guardado["metricas_locked"].values():
            assert {"media", "mediana", "frac_positivo", "retorno_10d", "retorno_20d", "retorno_60d"} <= set(m)


def test_run_es_determinista(inputs_dir, tmp_path):
    d, universo_path = inputs_dir
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    exp005.run(
        d, universo_path, a,
        discovery_start="2016-01-01", discovery_end="2019-12-31",
        validation_end="2021-12-31",
        n_boot=15, n_placebos=15, n_particiones_pbo=4, seed=0,
    )
    exp005.run(
        d, universo_path, b,
        discovery_start="2016-01-01", discovery_end="2019-12-31",
        validation_end="2021-12-31",
        n_boot=15, n_placebos=15, n_particiones_pbo=4, seed=0,
    )
    assert (a / "results.json").read_text() == (b / "results.json").read_text()


def test_run_sin_feature_discriminante(inputs_dir, tmp_path):
    d, universo_path = inputs_dir
    idx = pd.bdate_range("2015-01-01", "2023-12-31")
    d2 = tmp_path / "inputs_ruido"
    d2.mkdir()
    rng = np.random.default_rng(42)
    spy = _precio(idx, seed=1000, mu=0.0001, sd=0.01, inicio=100.0)
    df_spy = _ohlcv_desde_close(idx, spy)
    df_spy.index.name = "date"
    df_spy.to_parquet(d2 / "SPY.parquet")
    for i, t in enumerate(UNIVERSO_SINTETICO):
        # Mismo proceso aleatorio (ruido puro, sin relación con quién
        # termina "ganador") para todos los símbolos.
        precio = _precio(idx, seed=int(rng.integers(0, 1_000_000)), mu=0.0002, sd=0.012, inicio=40.0)
        df = _ohlcv_desde_close(idx, precio)
        df.index.name = "date"
        df.to_parquet(d2 / f"{t}.parquet")
    universo_path2 = tmp_path / "universo_ruido.txt"
    universo_path2.write_text("\n".join(UNIVERSO_SINTETICO))

    out = tmp_path / "run_ruido"
    out.mkdir()
    r = exp005.run(
        d2, universo_path2, out,
        discovery_start="2016-01-01", discovery_end="2019-12-31",
        validation_end="2021-12-31",
        umbral_correlacion=0.999,  # fuerza a que nada discrimine
        n_boot=10, n_placebos=10, n_particiones_pbo=4, seed=0,
    )
    assert r["label"] == "INCONCLUSIVE"
    assert r["motivo"] == "ninguna_feature_discrimina"

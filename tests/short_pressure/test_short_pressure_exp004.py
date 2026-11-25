"""Prueba de integración del orquestador con datos SINTÉTICOS (no son datos de mercado)."""
import json

import numpy as np
import pandas as pd
import pytest

from prl.short_pressure import exp004
from prl.short_pressure.exp004 import ajustar_ohlc, retorno_forward


def test_ajustar_ohlc_factor_y_division_por_cero():
    df = pd.DataFrame({
        "open": [110.0, 50.0], "high": [115.0, 55.0], "low": [105.0, 45.0],
        "close": [100.0, 0.0], "adj_close": [90.0, 10.0], "volume": [1000, 2000],
    })
    out = ajustar_ohlc(df)
    assert out.loc[0, "close"] == 90.0
    assert out.loc[0, "open"] == pytest.approx(99.0)
    assert pd.isna(out.loc[1, "open"])


def test_retorno_forward():
    precio = pd.Series([100.0, 110.0, 121.0, 100.0])
    r = retorno_forward(precio, 1)
    assert r.iloc[0] == pytest.approx(0.10)
    assert pd.isna(r.iloc[-1])


UNIVERSO_SINTETICO = [f"T{i:02d}" for i in range(15)]


def _ohlcv_desde_close(idx, close):
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "adj_close": close, "volume": pd.Series(1_000_000.0, index=idx),
    }, index=idx)


def _precio(idx, seed, mu, sd=0.015, inicio=50.0):
    r = np.random.default_rng(seed).normal(mu, sd, len(idx))
    return pd.Series(inicio * np.exp(np.cumsum(r)), index=idx)


@pytest.fixture
def inputs(tmp_path):
    d = tmp_path / "inputs"
    d.mkdir()
    idx = pd.bdate_range("2019-01-01", "2025-12-31")

    sv_filas = []
    si_filas = []
    for i, t in enumerate(UNIVERSO_SINTETICO):
        mu = -0.0002 + 0.0008 * (i / len(UNIVERSO_SINTETICO))
        precio = _precio(idx, seed=i, mu=mu, sd=0.012 + 0.001 * (i % 5), inicio=30.0 + i)
        df = _ohlcv_desde_close(idx, precio)
        df.index.name = "date"
        df.to_parquet(d / f"{t}.parquet")

        # Short volume: una fila cada 2 días, ratio sintético creciente con i.
        fechas_sv = idx[::2]
        sv_filas.append(pd.DataFrame({
            "date": fechas_sv, "symbol": t, "short_volume_ratio": 0.1 + 0.03 * i,
        }))

        # Short interest: un settlement cada ~15 sesiones.
        settlements = idx[::15]
        si_filas.append(pd.DataFrame({
            "symbol": t, "settlement_date": settlements,
            "days_to_cover": 1.0 + 0.2 * i, "short_interest_change_pct": 0.01 * i,
        }))

    sv_path = tmp_path / "short_volume.parquet"
    si_path = tmp_path / "short_interest.parquet"
    pd.concat(sv_filas, ignore_index=True).to_parquet(sv_path)
    pd.concat(si_filas, ignore_index=True).to_parquet(si_path)

    universo_path = tmp_path / "universo.txt"
    universo_path.write_text("\n".join(UNIVERSO_SINTETICO + ["SIN_DATOS"]))

    return d, sv_path, si_path, universo_path


def test_run_escribe_results_con_las_claves_esperadas(inputs, tmp_path):
    d, sv_path, si_path, universo_path = inputs
    out = tmp_path / "run"
    out.mkdir()
    r = exp004.run(
        d, sv_path, si_path, universo_path, out,
        discovery_start="2019-02-01", discovery_end="2021-12-31",
        validation_end="2023-06-30", locked_end="2025-12-31",
        n_boot=15, n_placebos=15, n_particiones_pbo=4, seed=0,
    )
    guardado = json.loads((out / "results.json").read_text())

    for k in [
        "experiment", "n_simbolos_universo", "n_simbolos_con_datos", "fechas_t0",
        "n_variantes_grid_total", "n_variantes_sobreviven_filtro_soporte",
        "variant_id_ganador", "motivo", "metricas_locked", "n_horizontes_superados",
        "mejor_baseline_10d", "comparacion_bootstrap_vs_mejor_baseline", "dsr",
        "n_trials_dsr", "pbo", "n_variantes_pbo", "concentracion",
        "leave_one_ticker_out", "sensibilidad_vecinos", "placebo", "label", "notes",
    ]:
        assert k in guardado, k

    assert guardado["experiment"] == "EXP-004"
    assert guardado["n_trials_dsr"] == 140
    assert guardado["label"] in {"VALIDATED", "REJECTED", "INCONCLUSIVE"}
    assert r["label"] == guardado["label"]
    assert any("SIN_DATOS" in n for n in guardado["notes"])

    if guardado["variant_id_ganador"] is not None:
        assert set(guardado["metricas_locked"]) == {
            "ganador", "baseline_buy_hold", "baseline_caida_simple",
            "baseline_price_exhaustion", "baseline_short_pressure", "baseline_combo_ingenuo",
        }
        for m in guardado["metricas_locked"].values():
            assert {"5", "10", "20"} <= set(m)


def test_run_es_determinista(inputs, tmp_path):
    d, sv_path, si_path, universo_path = inputs
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    kwargs = dict(
        discovery_start="2019-02-01", discovery_end="2021-12-31",
        validation_end="2023-06-30", locked_end="2025-12-31",
        n_boot=10, n_placebos=10, n_particiones_pbo=4, seed=0,
    )
    exp004.run(d, sv_path, si_path, universo_path, a, **kwargs)
    exp004.run(d, sv_path, si_path, universo_path, b, **kwargs)
    assert (a / "results.json").read_text() == (b / "results.json").read_text()


def test_run_sin_variante_sobreviviente(inputs, tmp_path):
    d, sv_path, si_path, universo_path = inputs
    out = tmp_path / "run_sin_soporte"
    out.mkdir()
    r = exp004.run(
        d, sv_path, si_path, universo_path, out,
        discovery_start="2019-02-01", discovery_end="2021-12-31",
        validation_end="2023-06-30", locked_end="2025-12-31",
        min_senales_discovery=1_000_000,  # imposible de alcanzar -> ninguna variante sobrevive
        n_boot=10, n_placebos=10, n_particiones_pbo=4, seed=0,
    )
    assert r["label"] == "INCONCLUSIVE"
    assert r["motivo"] == "ninguna_variante_pasa_el_filtro_de_soporte"
    assert r["variant_id_ganador"] is None

"""Prueba de integración del runner congelado con datos SINTÉTICOS (no son datos de mercado)."""
import numpy as np
import pandas as pd
import pytest

from prl.reverse_winners import forward_runner
from prl.reverse_winners.exp005 import retorno_forward


UNIVERSO_SINTETICO = [f"T{i:02d}" for i in range(8)]


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
    idx = pd.bdate_range("2018-01-01", "2021-12-31")

    spy = _precio(idx, seed=999, mu=0.0003, sd=0.009, inicio=100.0)
    df_spy = _ohlcv_desde_close(idx, spy)
    df_spy.index.name = "date"
    df_spy.to_parquet(d / "SPY.parquet")

    for i, t in enumerate(UNIVERSO_SINTETICO):
        mu = 0.0001 + 0.0004 * (i / len(UNIVERSO_SINTETICO))
        precio = _precio(idx, seed=i, mu=mu, sd=0.010 + 0.001 * (i % 5), inicio=30.0 + i)
        df = _ohlcv_desde_close(idx, precio)
        df.index.name = "date"
        df.to_parquet(d / f"{t}.parquet")

    universo_path = tmp_path / "universo.txt"
    universo_path.write_text("\n".join(UNIVERSO_SINTETICO + ["SIN_DATOS"]))

    return d, universo_path, idx


def test_construir_senales_caso_referencia(inputs_dir):
    d, universo_path, idx = inputs_dir
    fecha_corte = idx[300]

    # Bucket congelado de 1 sola feature, umbral conocido, para poder
    # verificar a mano qué símbolos debía seleccionar.
    bucket = {
        "umbrales": {
            "mom_20d": {"direccion": "alto", "percentil": 0.75},
        }
    }
    out = forward_runner.construir_senales_para_fechas(
        d, universo_path, [fecha_corte], bucket, benchmark="SPY"
    )
    assert set(out.keys()) == {
        "ganador", "baseline_momentum_simple", "baseline_buy_hold",
        "baseline_rsi_simple", "baseline_combo_ingenuo", "spy",
    }
    for df in out.values():
        if len(df) > 0:
            assert set(df["fecha"].unique()) <= {fecha_corte}


def test_spy_es_el_propio_retorno_del_indice(inputs_dir):
    d, universo_path, idx = inputs_dir
    fechas = [idx[300], idx[320]]
    bucket = {"umbrales": {"mom_20d": {"direccion": "alto", "percentil": 0.90}}}
    out = forward_runner.construir_senales_para_fechas(d, universo_path, fechas, bucket)
    spy_df = out["spy"]
    assert len(spy_df) == 2
    assert set(spy_df["ticker"]) == {"SPY"}

    df_spy_raw = pd.read_parquet(d / "SPY.parquet")
    ret30_spy = retorno_forward(df_spy_raw["close"], 30)
    for fecha in fechas:
        esperado = float(ret30_spy.loc[fecha])
        obtenido = float(spy_df.loc[spy_df["fecha"] == fecha, "retorno_30d"].iloc[0])
        assert obtenido == pytest.approx(esperado)


def test_simbolo_sin_archivo_no_lanza_excepcion(inputs_dir):
    d, universo_path, idx = inputs_dir
    bucket = {"umbrales": {"mom_20d": {"direccion": "alto", "percentil": 0.90}}}
    out = forward_runner.construir_senales_para_fechas(d, universo_path, [idx[300]], bucket)
    for df in out.values():
        assert "SIN_DATOS" not in set(df.get("ticker", []))


def test_determinismo(inputs_dir):
    d, universo_path, idx = inputs_dir
    bucket = {"umbrales": {"mom_20d": {"direccion": "alto", "percentil": 0.75}}}
    out1 = forward_runner.construir_senales_para_fechas(d, universo_path, [idx[300], idx[320]], bucket)
    out2 = forward_runner.construir_senales_para_fechas(d, universo_path, [idx[300], idx[320]], bucket)
    for key in out1:
        pd.testing.assert_frame_equal(
            out1[key].reset_index(drop=True), out2[key].reset_index(drop=True)
        )

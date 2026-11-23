"""Prueba de integración del runner congelado con datos SINTÉTICOS (no son datos de mercado).

Las pruebas comparan contra una tabla de percentiles construida llamando
directamente a las funciones ya probadas (features.calcular_features_simbolo,
features.normalizar_percentil_cross_sectional, grid.aplicar_bucket) sobre los
mismos datos — no basta con verificar que el resultado no esté vacío o que las
fechas sean correctas: esto existe específicamente para atrapar errores de
orden de argumentos o de "mirroring" de umbrales que un chequeo superficial no
detectaría.
"""
import numpy as np
import pandas as pd
import pytest

from prl.reverse_winners import baselines, features, grid
from prl.reverse_winners import forward_runner
from prl.reverse_winners.exp005 import ajustar_ohlc, retorno_forward


UNIVERSO_SINTETICO = [f"T{i:02d}" for i in range(10)]


def _ohlcv_desde_close(idx, close, seed_volumen=0):
    # Volumen con variación real (no constante): volume_spike_z depende de la
    # desviación estándar del volumen en una ventana — con volumen constante
    # esa desviación es 0 y la feature queda NaN SIEMPRE, lo que haría que
    # ningún símbolo sea nunca elegible (bug de fixture, no de la
    # implementación — detectado al construir este archivo).
    rng = np.random.default_rng(seed_volumen)
    volumen = pd.Series(
        1_000_000.0 * np.exp(rng.normal(0.0, 0.15, len(idx))), index=idx
    )
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "adj_close": close,
            "volume": volumen,
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
    df_spy = _ohlcv_desde_close(idx, spy, seed_volumen=999)
    df_spy.index.name = "date"
    df_spy.to_parquet(d / "SPY.parquet")

    for i, t in enumerate(UNIVERSO_SINTETICO):
        mu = 0.0001 + 0.0004 * (i / len(UNIVERSO_SINTETICO))
        precio = _precio(idx, seed=i, mu=mu, sd=0.010 + 0.001 * (i % 5), inicio=30.0 + i)
        df = _ohlcv_desde_close(idx, precio, seed_volumen=100 + i)
        df.index.name = "date"
        df.to_parquet(d / f"{t}.parquet")

    universo_path = tmp_path / "universo.txt"
    universo_path.write_text("\n".join(UNIVERSO_SINTETICO + ["SIN_DATOS"]))

    return d, universo_path, idx


def _tabla_percentil_real(inputs_dir, universo, benchmark, fecha, min_historia=252):
    """Replica independiente (usando solo funciones ya probadas) de la tabla
    cross-sectional esperada en `fecha`, para comparar contra forward_runner."""
    df_bench_raw = pd.read_parquet(inputs_dir / f"{benchmark}.parquet")
    df_bench_adj = ajustar_ohlc(df_bench_raw).sort_index()

    filas = {}
    for sym in universo:
        p = inputs_dir / f"{sym}.parquet"
        if not p.exists():
            continue
        df_raw = pd.read_parquet(p).sort_index()
        df_adj = ajustar_ohlc(df_raw).sort_index()
        n_historia = (df_raw.index <= fecha).sum()
        if n_historia < min_historia:
            continue
        bench_reindexado = df_bench_adj.reindex(df_adj.index)
        feat = features.calcular_features_simbolo(df_adj, bench_reindexado)
        if fecha not in feat.index:
            continue
        fila = feat.loc[fecha]
        if fila.isna().any():
            continue
        filas[sym] = fila

    tabla_cruda = pd.DataFrame(filas).T.sort_index()
    tabla_percentil = features.normalizar_percentil_cross_sectional(tabla_cruda)
    return tabla_cruda, tabla_percentil


@pytest.mark.parametrize("direccion", ["alto", "bajo"])
def test_ganador_coincide_exactamente_con_grid_aplicar_bucket(inputs_dir, direccion):
    d, universo_path, idx = inputs_dir
    fecha_corte = idx[300]

    bucket = {
        "umbrales": {"mom_20d": {"direccion": direccion, "percentil": 0.75}}
    }

    _, tabla_percentil_real = _tabla_percentil_real(
        d, UNIVERSO_SINTETICO, "SPY", fecha_corte
    )
    assert len(tabla_percentil_real) == len(UNIVERSO_SINTETICO)  # todos con historia suficiente

    seleccion_real = grid.aplicar_bucket(bucket, tabla_percentil_real)
    esperado = set(tabla_percentil_real.index[seleccion_real])

    out = forward_runner.construir_senales_para_fechas(
        d, universo_path, [fecha_corte], bucket, benchmark="SPY"
    )
    obtenido = set(out["ganador"]["ticker"])

    assert obtenido == esperado
    assert len(esperado) > 0  # el bucket de prueba no debe seleccionar 0 símbolos


def test_baseline_buy_hold_incluye_a_todos_los_elegibles(inputs_dir):
    d, universo_path, idx = inputs_dir
    fecha_corte = idx[300]
    bucket = {"umbrales": {"mom_20d": {"direccion": "alto", "percentil": 0.90}}}

    tabla_cruda, _ = _tabla_percentil_real(d, UNIVERSO_SINTETICO, "SPY", fecha_corte)

    out = forward_runner.construir_senales_para_fechas(
        d, universo_path, [fecha_corte], bucket, benchmark="SPY"
    )
    assert set(out["baseline_buy_hold"]["ticker"]) == set(tabla_cruda.index)
    assert len(out["baseline_buy_hold"]) == len(UNIVERSO_SINTETICO)


def test_baseline_momentum_simple_coincide_con_baselines_directo(inputs_dir):
    d, universo_path, idx = inputs_dir
    fecha_corte = idx[300]
    bucket = {"umbrales": {"mom_20d": {"direccion": "alto", "percentil": 0.90}}}

    _, tabla_percentil_real = _tabla_percentil_real(d, UNIVERSO_SINTETICO, "SPY", fecha_corte)
    seleccion_real = baselines.baseline_momentum_simple(tabla_percentil_real, pct=0.20)
    esperado = set(tabla_percentil_real.index[seleccion_real])

    out = forward_runner.construir_senales_para_fechas(
        d, universo_path, [fecha_corte], bucket, benchmark="SPY"
    )
    assert set(out["baseline_momentum_simple"]["ticker"]) == esperado
    assert len(esperado) > 0


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
    # confirma que, pese al símbolo faltante, el resto sí produjo señales
    assert len(out["baseline_buy_hold"]) == len(UNIVERSO_SINTETICO)


def test_determinismo(inputs_dir):
    d, universo_path, idx = inputs_dir
    bucket = {"umbrales": {"mom_20d": {"direccion": "alto", "percentil": 0.75}}}
    out1 = forward_runner.construir_senales_para_fechas(d, universo_path, [idx[300], idx[320]], bucket)
    out2 = forward_runner.construir_senales_para_fechas(d, universo_path, [idx[300], idx[320]], bucket)
    for key in out1:
        assert len(out1[key]) > 0 or key not in ("ganador", "baseline_buy_hold")
        pd.testing.assert_frame_equal(
            out1[key].reset_index(drop=True), out2[key].reset_index(drop=True)
        )

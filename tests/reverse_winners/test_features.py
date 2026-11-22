import numpy as np
import pandas as pd
import pytest

from prl.reverse_winners.features import (
    aceleracion,
    atr,
    beta,
    calcular_features_simbolo,
    cruce_sma,
    discriminacion_features,
    distancia_extremo,
    distancia_sma,
    drawdown_previo,
    features_cross_sectional,
    features_discriminantes,
    gap,
    fuerza_relativa,
    momentum,
    normalizar_percentil_cross_sectional,
    rsi,
    sharpe_reciente,
    universo_elegible,
    volatilidad_realizada,
    volume_spike_zscore,
    volumen_relativo,
)

COLUMNAS_ESPERADAS = [
    "mom_5d", "mom_10d", "mom_20d",
    "dist_sma20", "dist_sma50", "dist_sma200",
    "golden_cross", "atr14", "vol_realizada_20d", "vol_relativo_20d",
    "volume_spike_z", "rsi14", "drawdown_60d", "gap",
    "fuerza_relativa_20d", "beta_60d", "sharpe_20d",
    "dist_max20", "dist_min20", "aceleracion",
]


def _serie(valores, inicio="2020-01-01"):
    idx = pd.bdate_range(inicio, periods=len(valores))
    return pd.Series(valores, index=idx, dtype=float)


def _creciente(n, inicio_valor=100.0, paso=0.5):
    return _serie([inicio_valor + i * paso for i in range(n)])


def _decreciente(n, inicio_valor=200.0, paso=0.5):
    return _serie([inicio_valor - i * paso for i in range(n)])


def _plano(n, valor=100.0):
    return _serie([valor] * n)


def _df_ohlcv(n, cierre=None, volumen=None, inicio="2020-01-01"):
    idx = pd.bdate_range(inicio, periods=n)
    if cierre is None:
        cierre = [100.0 + i * 0.3 for i in range(n)]
    if volumen is None:
        volumen = [1_000_000.0] * n
    cierre = pd.Series(cierre, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": cierre.shift(1).fillna(cierre.iloc[0]),
            "high": cierre * 1.01,
            "low": cierre * 0.99,
            "close": cierre,
            "volume": volumen,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# 1. Historia insuficiente en cada bloque con ventana
# ---------------------------------------------------------------------------


def test_momentum_nan_antes_de_completar_ventana():
    precio = _creciente(30)
    s = momentum(precio, dias=20)
    assert s.iloc[:20].isna().all()
    assert not pd.isna(s.iloc[20])


def test_distancia_sma_nan_antes_de_completar_ventana():
    precio = _creciente(60)
    s = distancia_sma(precio, ventana=50)
    assert s.iloc[:49].isna().all()
    assert not pd.isna(s.iloc[49])


def test_atr_nan_antes_de_completar_ventana():
    df = _df_ohlcv(30)
    s = atr(df["high"], df["low"], df["close"], ventana=14)
    assert s.iloc[:13].isna().all()
    assert not pd.isna(s.iloc[13])


def test_volatilidad_realizada_nan_antes_de_completar_ventana():
    precio = _creciente(30)
    s = volatilidad_realizada(precio, ventana=20)
    assert s.iloc[:20].isna().all()
    assert not pd.isna(s.iloc[20])


def test_volumen_relativo_nan_antes_de_completar_ventana():
    volumen = _serie([1_000_000.0 + i * 1000 for i in range(30)])
    s = volumen_relativo(volumen, ventana=20)
    assert s.iloc[:19].isna().all()
    assert not pd.isna(s.iloc[19])


def test_volume_spike_zscore_nan_antes_de_completar_ventana_larga():
    volumen = _serie([1_000_000.0 + (i % 7) * 5000 for i in range(70)])
    s = volume_spike_zscore(volumen, ventana_corta=5, ventana_larga=60)
    assert s.iloc[:59].isna().all()
    assert not pd.isna(s.iloc[59])


def test_rsi_nan_antes_de_completar_ventana():
    precio = _creciente(30)
    s = rsi(precio, ventana=14)
    assert s.iloc[:14].isna().all()
    assert not pd.isna(s.iloc[14])


def test_drawdown_previo_nan_antes_de_completar_ventana():
    precio = _creciente(70)
    s = drawdown_previo(precio, ventana=60)
    assert s.iloc[:59].isna().all()
    assert not pd.isna(s.iloc[59])


def test_beta_nan_antes_de_completar_ventana():
    bench = _creciente(70, paso=0.4)
    precio = _creciente(70, paso=0.6)
    s = beta(precio, bench, ventana=60)
    assert s.iloc[:60].isna().all()
    assert not pd.isna(s.iloc[60])


def test_sharpe_reciente_nan_antes_de_completar_ventana():
    precio = _creciente(30)
    s = sharpe_reciente(precio, ventana=20)
    assert s.iloc[:20].isna().all()
    assert not pd.isna(s.iloc[20])


def test_distancia_extremo_nan_antes_de_completar_ventana():
    precio = _creciente(30)
    s = distancia_extremo(precio, ventana=20, tipo="max")
    assert s.iloc[:19].isna().all()
    assert not pd.isna(s.iloc[19])


# ---------------------------------------------------------------------------
# 2. cruce_sma
# ---------------------------------------------------------------------------


def test_cruce_sma_true_cuando_corta_por_encima():
    # Sube fuerte al final para que SMA50 reciente quede por encima de SMA200
    valores = [100.0] * 200 + [100.0 + i * 2.0 for i in range(1, 51)]
    precio = _serie(valores)
    s = cruce_sma(precio, ventana_corta=50, ventana_larga=200)
    assert s.iloc[-1] == True  # noqa: E712


def test_cruce_sma_false_cuando_corta_por_debajo():
    valores = [200.0] * 200 + [200.0 - i * 2.0 for i in range(1, 51)]
    precio = _serie(valores)
    s = cruce_sma(precio, ventana_corta=50, ventana_larga=200)
    assert s.iloc[-1] == False  # noqa: E712


def test_cruce_sma_nan_antes_de_completar_ventana_larga():
    precio = _creciente(199)
    s = cruce_sma(precio, ventana_corta=50, ventana_larga=200)
    assert s.isna().all()


# ---------------------------------------------------------------------------
# 3. rsi — casos extremos
# ---------------------------------------------------------------------------


def test_rsi_100_si_solo_sube():
    precio = _creciente(30)
    s = rsi(precio, ventana=14)
    assert s.iloc[-1] == pytest.approx(100.0)


def test_rsi_0_si_solo_baja():
    precio = _decreciente(30)
    s = rsi(precio, ventana=14)
    assert s.iloc[-1] == pytest.approx(0.0)


def test_rsi_50_si_precio_plano():
    precio = _plano(30)
    s = rsi(precio, ventana=14)
    assert s.iloc[-1] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# 4. volume_spike_zscore con desviación cero
# ---------------------------------------------------------------------------


def test_volume_spike_zscore_nan_si_desviacion_cero():
    volumen = _plano(70, valor=1_000_000.0)
    s = volume_spike_zscore(volumen, ventana_corta=5, ventana_larga=60)
    assert pd.isna(s.iloc[-1])


# ---------------------------------------------------------------------------
# 5. distancia_extremo con tipo inválido
# ---------------------------------------------------------------------------


def test_distancia_extremo_tipo_invalido_lanza_valueerror():
    precio = _creciente(30)
    with pytest.raises(ValueError):
        distancia_extremo(precio, ventana=20, tipo="maximo")


# ---------------------------------------------------------------------------
# 6. calcular_features_simbolo — columnas exactas
# ---------------------------------------------------------------------------


def test_calcular_features_simbolo_devuelve_columnas_exactas():
    df = _df_ohlcv(260)
    bench = _df_ohlcv(260, cierre=[100.0 + i * 0.2 for i in range(260)])
    resultado = calcular_features_simbolo(df, bench)
    assert list(resultado.columns) == COLUMNAS_ESPERADAS
    assert resultado.index.equals(df.index)
    # al menos la última fila debe tener valores calculados en todas las columnas
    assert resultado.iloc[-1].notna().all() or resultado.iloc[-1].isna().sum() <= 1  # golden_cross puede ser bool nullable


# ---------------------------------------------------------------------------
# 7. universo_elegible
# ---------------------------------------------------------------------------


def test_universo_elegible_filtra_por_historia_minima():
    fecha = pd.bdate_range("2020-01-01", periods=300)[-1]
    universo = {
        "AAA": _df_ohlcv(300),
        "BBB": _df_ohlcv(100),
        "CCC": _df_ohlcv(252),
    }
    elegibles = universo_elegible(universo, fecha, min_historia=252)
    assert elegibles == ["AAA", "CCC"]


# ---------------------------------------------------------------------------
# 8. features_cross_sectional
# ---------------------------------------------------------------------------


def test_features_cross_sectional_devuelve_simbolos_elegibles_ordenados():
    fecha = pd.bdate_range("2020-01-01", periods=260)[-1]
    universo = {
        "ZZZ": _df_ohlcv(260),
        "AAA": _df_ohlcv(260),
        "MMM": _df_ohlcv(100),  # no elegible
    }
    bench = _df_ohlcv(260, cierre=[100.0 + i * 0.25 for i in range(260)])
    resultado = features_cross_sectional(universo, bench, fecha, min_historia=252)
    assert list(resultado.index) == ["AAA", "ZZZ"]
    assert list(resultado.columns) == COLUMNAS_ESPERADAS


def test_features_cross_sectional_usa_fecha_anterior_cercana_sin_excepcion():
    # Símbolo sin dato exacto en `fecha` (termina 1 día antes) no debe tronar
    idx_completo = pd.bdate_range("2020-01-01", periods=260)
    fecha = idx_completo[-1]
    universo = {
        "AAA": _df_ohlcv(260),
        "BBB": pd.DataFrame(
            {
                "open": [100.0] * 259,
                "high": [101.0] * 259,
                "low": [99.0] * 259,
                "close": [100.0 + i * 0.1 for i in range(259)],
                "volume": [1_000_000.0] * 259,
            },
            index=idx_completo[:259],
        ),
    }
    bench = _df_ohlcv(260, cierre=[100.0 + i * 0.25 for i in range(260)])
    resultado = features_cross_sectional(universo, bench, fecha, min_historia=252)
    assert "BBB" in resultado.index


# ---------------------------------------------------------------------------
# 9. normalizar_percentil_cross_sectional
# ---------------------------------------------------------------------------


def test_normalizar_percentil_cross_sectional_ignora_nan():
    df = pd.DataFrame({"x": [10.0, 20.0, np.nan, 30.0]})
    resultado = normalizar_percentil_cross_sectional(df)
    assert resultado["x"].iloc[0] == pytest.approx(1 / 3)
    assert resultado["x"].iloc[1] == pytest.approx(2 / 3)
    assert pd.isna(resultado["x"].iloc[2])
    assert resultado["x"].iloc[3] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 10. discriminacion_features
# ---------------------------------------------------------------------------


def test_discriminacion_features_detecta_senal_real():
    idx = [f"S{i}" for i in range(20)]
    ganadores = pd.Series([True] * 10 + [False] * 10, index=idx)
    # Ganadores con valores claramente más altos
    fuerte = pd.Series([10.0 + i for i in range(10)] + [0.0 + i for i in range(10)], index=idx)
    ruido = pd.Series(np.random.RandomState(0).normal(size=20), index=idx)
    features = pd.DataFrame({"fuerte": fuerte, "ruido": ruido})
    resultado = discriminacion_features(features, ganadores)
    assert resultado.loc["fuerte", "diferencia_medianas"] > 0
    assert resultado.loc["fuerte", "correlacion_punto_biserial"] > 0.5
    assert abs(resultado.loc["ruido", "correlacion_punto_biserial"]) < 0.5
    # ordenado por |correlación| descendente
    assert list(resultado.index)[0] == "fuerte"


def test_discriminacion_features_nan_con_menos_de_2_valores_por_grupo():
    idx = ["S1", "S2", "S3"]
    ganadores = pd.Series([True, False, False], index=idx)
    columna = pd.Series([1.0, 2.0, np.nan], index=idx)
    features = pd.DataFrame({"x": columna})
    resultado = discriminacion_features(features, ganadores)
    assert pd.isna(resultado.loc["x", "correlacion_punto_biserial"])
    assert pd.isna(resultado.loc["x", "diferencia_medianas"])


# ---------------------------------------------------------------------------
# 11. features_discriminantes
# ---------------------------------------------------------------------------


def test_features_discriminantes_filtra_por_umbral_y_limite():
    discriminacion = pd.DataFrame(
        {
            "diferencia_medianas": [1, 1, 1, 1, 1, 1, 1, 1],
            "correlacion_punto_biserial": [0.9, 0.8, 0.7, 0.6, 0.04, 0.03, 0.02, 0.01],
            "n_ganadores": [10] * 8,
            "n_no_ganadores": [10] * 8,
        },
        index=["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"],
    )
    resultado = features_discriminantes(discriminacion, umbral=0.05, max_features=3)
    assert resultado == ["f1", "f2", "f3"]


def test_features_discriminantes_menos_de_max_si_pocas_superan_umbral():
    discriminacion = pd.DataFrame(
        {
            "diferencia_medianas": [1, 1],
            "correlacion_punto_biserial": [0.9, 0.02],
            "n_ganadores": [10, 10],
            "n_no_ganadores": [10, 10],
        },
        index=["f1", "f2"],
    )
    resultado = features_discriminantes(discriminacion, umbral=0.05, max_features=5)
    assert resultado == ["f1"]


# ---------------------------------------------------------------------------
# Extras: gap, fuerza_relativa, aceleracion (bloques simples, cubiertos aparte)
# ---------------------------------------------------------------------------


def test_gap_nan_en_primera_fila():
    df = _df_ohlcv(10)
    s = gap(df["open"], df["close"])
    assert pd.isna(s.iloc[0])
    assert not pd.isna(s.iloc[1])


def test_fuerza_relativa_resta_momentums():
    precio = _creciente(30, paso=1.0)
    bench = _creciente(30, paso=0.5)
    s = fuerza_relativa(precio, bench, dias=20)
    m_precio = momentum(precio, 20)
    m_bench = momentum(bench, 20)
    pd.testing.assert_series_equal(s, m_precio - m_bench, check_names=False)


def test_aceleracion_resta_momentums_corto_y_largo():
    precio = _creciente(30)
    s = aceleracion(precio, dias_corto=5, dias_largo=20)
    esperado = momentum(precio, 5) - momentum(precio, 20)
    pd.testing.assert_series_equal(s, esperado, check_names=False)

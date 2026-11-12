import numpy as np
import pandas as pd

from prl.growth_max.signals import (
    breakout_signal,
    composite_score,
    es_regimen_de_rango,
    regimen_macro,
    reversion_zscore,
    senal_compuesta_con_overlay,
    senal_reversion,
    signo_cambio_trailing,
    trend_signal,
    ts_momentum_signal,
    volatilidad_realizada,
)


def _precios(valores, inicio="2020-01-01"):
    idx = pd.bdate_range(inicio, periods=len(valores))
    return pd.Series(valores, index=idx, dtype=float)


def _creciente(n, inicio_valor=100.0, paso=0.5):
    return _precios([inicio_valor + i * paso for i in range(n)])


def _decreciente(n, inicio_valor=200.0, paso=0.5):
    return _precios([inicio_valor - i * paso for i in range(n)])


def _plano(n, valor=100.0):
    return _precios([valor] * n)


# ---------------------------------------------------------------------------
# Historia insuficiente / NaN antes de completar ventana
# ---------------------------------------------------------------------------


def test_ts_momentum_signal_nan_antes_de_completar_ventana():
    precio = _creciente(100)
    meses = 3
    ventana = meses * 21
    s = ts_momentum_signal(precio, meses)
    assert s.iloc[:ventana].isna().all()
    assert not pd.isna(s.iloc[ventana])


def test_trend_signal_nan_antes_de_completar_ventana():
    precio = _creciente(60)
    s = trend_signal(precio, ventana=50)
    assert s.iloc[:49].isna().all()
    assert not pd.isna(s.iloc[49])


def test_breakout_signal_nan_antes_de_completar_ventana():
    precio = _creciente(60)
    s = breakout_signal(precio, ventana=55)
    assert s.iloc[:54].isna().all()
    assert not pd.isna(s.iloc[54])


def test_reversion_zscore_nan_antes_de_completar_ventana():
    precio = _creciente(30)
    s = reversion_zscore(precio, ventana=20)
    assert s.iloc[:19].isna().all()
    assert not pd.isna(s.iloc[19])


def test_volatilidad_realizada_nan_antes_de_completar_ventana():
    precio = _creciente(30)
    s = volatilidad_realizada(precio, ventana=20)
    assert s.iloc[:20].isna().all()
    assert not pd.isna(s.iloc[20])


# ---------------------------------------------------------------------------
# Signo correcto
# ---------------------------------------------------------------------------


def test_momentum_trend_breakout_dan_mas_uno_en_serie_creciente():
    precio = _creciente(300)
    assert ts_momentum_signal(precio, meses=3).iloc[-1] == 1.0
    assert trend_signal(precio, ventana=50).iloc[-1] == 1.0
    assert breakout_signal(precio, ventana=55).iloc[-1] == 1.0


def test_momentum_trend_breakout_dan_menos_uno_en_serie_decreciente():
    precio = _decreciente(300)
    assert ts_momentum_signal(precio, meses=3).iloc[-1] == -1.0
    assert trend_signal(precio, ventana=50).iloc[-1] == -1.0
    assert breakout_signal(precio, ventana=55).iloc[-1] == -1.0


# ---------------------------------------------------------------------------
# Empates y división por cero
# ---------------------------------------------------------------------------


def test_breakout_con_precio_plano_da_mas_uno():
    precio = _plano(60)
    s = breakout_signal(precio, ventana=55)
    assert s.iloc[-1] == 1.0


def test_reversion_con_desviacion_cero_da_nan_no_inf():
    precio = _plano(30)
    s = reversion_zscore(precio, ventana=20)
    assert pd.isna(s.iloc[-1])
    assert not np.isinf(s.fillna(0.0)).any()


def test_senal_reversion_signo_opuesto_al_zscore():
    # Precio con una subida fuerte al final: z-score alto -> reversión -1.
    valores = [100.0] * 25 + [130.0]
    precio = _precios(valores)
    z = reversion_zscore(precio, ventana=20)
    r = senal_reversion(precio, ventana=20)
    assert z.iloc[-1] > 0
    assert r.iloc[-1] == -1.0


# ---------------------------------------------------------------------------
# composite_score (mismo comportamiento que prl.emergency.features)
# ---------------------------------------------------------------------------


def test_composite_score_promedia_solo_disponibles_y_renormaliza():
    dims = pd.DataFrame(
        {
            "momentum": [1.0, np.nan, -1.0],
            "trend": [1.0, 1.0, -1.0],
            "breakout": [np.nan, 1.0, 1.0],
        }
    )
    pesos = {"momentum": 1.0, "trend": 1.0, "breakout": 1.0}
    out = composite_score(dims, pesos)
    assert out.iloc[0] == 1.0  # (1+1)/2
    assert out.iloc[1] == 1.0  # (1+1)/2
    assert np.isclose(out.iloc[2], -1 / 3)  # (-1 + -1 + 1)/3


def test_composite_score_nan_si_ninguna_disponible():
    dims = pd.DataFrame({"momentum": [np.nan], "trend": [np.nan]})
    out = composite_score(dims, {"momentum": 1.0, "trend": 1.0})
    assert pd.isna(out.iloc[0])


# ---------------------------------------------------------------------------
# signo_cambio_trailing
# ---------------------------------------------------------------------------


def test_signo_cambio_trailing_nan_antes_de_dias_observaciones():
    serie = _creciente(50, inicio_valor=10.0, paso=0.1)
    s = signo_cambio_trailing(serie, dias=20)
    assert s.iloc[:20].isna().all()
    assert s.iloc[20] == 1.0


def test_signo_cambio_trailing_propaga_hueco_de_nan():
    valores = [1.0] * 10 + [np.nan] * 5 + [2.0] * 10
    serie = _precios(valores)
    s = signo_cambio_trailing(serie, dias=5)
    # La fila 15 (índice 0-based) necesita serie[15] (válida) y serie[10] (NaN, en el hueco).
    assert pd.isna(s.iloc[15])


# ---------------------------------------------------------------------------
# regimen_macro / es_regimen_de_rango
# ---------------------------------------------------------------------------


def test_regimen_macro_los_cuatro_casos():
    liquidez = pd.Series([1.0, 1.0, -1.0, -1.0])
    crecimiento = pd.Series([1.0, -1.0, 1.0, -1.0])
    r = regimen_macro(liquidez, crecimiento)
    assert list(r) == [1.0, 2.0, 3.0, 4.0]


def test_regimen_macro_nan_si_alguna_entrada_nan_o_cero():
    liquidez = pd.Series([1.0, np.nan, 0.0, 1.0])
    crecimiento = pd.Series([np.nan, 1.0, 1.0, 0.0])
    r = regimen_macro(liquidez, crecimiento)
    assert r.isna().all()


def test_es_regimen_de_rango_solo_2_y_3():
    regimen = pd.Series([1.0, 2.0, 3.0, 4.0, np.nan])
    out = es_regimen_de_rango(regimen)
    assert list(out) == [False, True, True, False, False]


# ---------------------------------------------------------------------------
# senal_compuesta_con_overlay
# ---------------------------------------------------------------------------


def test_senal_compuesta_con_overlay_elige_segun_regimen():
    direccional = pd.Series([1.0, 1.0, -1.0, -1.0])
    reversion = pd.Series([-1.0, -1.0, 1.0, 1.0])
    regimen_de_rango = pd.Series([False, True, False, True])
    out = senal_compuesta_con_overlay(direccional, reversion, regimen_de_rango)
    assert list(out) == [1.0, -1.0, -1.0, 1.0]


def test_senal_compuesta_con_overlay_propaga_nan_del_valor_elegido():
    direccional = pd.Series([1.0, np.nan])
    reversion = pd.Series([-1.0, -1.0])
    regimen_de_rango = pd.Series([False, False])
    out = senal_compuesta_con_overlay(direccional, reversion, regimen_de_rango)
    assert out.iloc[0] == 1.0
    assert pd.isna(out.iloc[1])

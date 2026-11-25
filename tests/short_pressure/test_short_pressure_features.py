import numpy as np
import pandas as pd
import pytest

from prl.short_pressure.features import (
    calcular_features_simbolo,
    confirmacion_a,
    confirmacion_b,
    confirmacion_c,
    confirmacion_d,
    confirmacion_e,
    days_to_cover_serie,
    distancia_sma,
    drawdown_previo,
    momentum,
    rsi,
    short_interest_change_pct_serie,
    short_volume_ratio_serie,
    volatilidad_realizada,
    volumen_relativo,
    zscore_nivel,
    zscore_retorno,
    PRICE_EXHAUSTION_SCORE,
    SHORT_PRESSURE_SCORE,
)

COLUMNAS_ESPERADAS = [
    "short_volume_ratio", "short_volume_ratio_zscore_20d", "days_to_cover", "short_interest_change_pct",
    "ret_1d", "ret_5d", "ret_20d", "drawdown_5d", "drawdown_20d", "drawdown_60d",
    "dist_sma20", "dist_sma50", "dist_sma200", "rsi_2", "rsi_14",
    "realized_vol_20d", "rel_volume", "zscore_ret_5d",
    "confirmacion_a", "confirmacion_b", "confirmacion_c", "confirmacion_d", "confirmacion_e",
]


def _serie(valores, inicio="2020-01-01"):
    idx = pd.bdate_range(inicio, periods=len(valores))
    return pd.Series(valores, index=idx, dtype=float)


def _creciente(n, inicio_valor=100.0, paso=0.5):
    return _serie([inicio_valor + i * paso for i in range(n)])


def _plano(n, valor=100.0):
    return _serie([valor] * n)


# ---------------------------------------------------------------------------
# Bloques base de precio
# ---------------------------------------------------------------------------


def test_momentum_calculo_y_nan_insuficiente():
    precio = _serie([100.0, 110.0, 121.0])
    r = momentum(precio, 2)
    assert pd.isna(r.iloc[0]) and pd.isna(r.iloc[1])
    assert r.iloc[2] == pytest.approx(0.21)


def test_distancia_sma_ventana_completa_y_nan():
    precio = _serie([10.0, 20.0, 30.0, 40.0])
    r = distancia_sma(precio, 2)
    assert pd.isna(r.iloc[0])
    assert r.iloc[1] == pytest.approx(20.0 / 15.0 - 1.0)
    assert r.iloc[3] == pytest.approx(40.0 / 35.0 - 1.0)


def test_rsi_casos_extremos():
    solo_sube = _creciente(20, paso=1.0)
    r = rsi(solo_sube, 14)
    assert r.iloc[-1] == pytest.approx(100.0)

    plano = _plano(20)
    r2 = rsi(plano, 14)
    assert r2.iloc[-1] == pytest.approx(50.0)

    assert pd.isna(rsi(solo_sube, 14).iloc[5])


def test_drawdown_previo():
    precio = _serie([100.0, 120.0, 90.0])
    r = drawdown_previo(precio, 2)
    assert pd.isna(r.iloc[0])
    assert r.iloc[2] == pytest.approx(90.0 / 120.0 - 1.0)


def test_volatilidad_realizada_nan_antes_de_ventana():
    precio = _creciente(10, paso=1.0)
    r = volatilidad_realizada(precio, 5)
    assert pd.isna(r.iloc[3])
    assert not pd.isna(r.iloc[5])
    assert r.iloc[5] >= 0


def test_volumen_relativo_division_por_cero():
    volumen = _serie([0.0, 0.0, 0.0, 100.0])
    r = volumen_relativo(volumen, 3)
    assert pd.isna(r.iloc[2])


def test_zscore_retorno_y_zscore_nivel():
    precio = _creciente(300, paso=0.1)
    r = zscore_retorno(precio, dias_retorno=5, ventana=252)
    assert pd.isna(r.iloc[250])
    assert not pd.isna(r.iloc[260])

    nivel = _serie(list(np.linspace(1.0, 2.0, 40)))
    z = zscore_nivel(nivel, ventana=20)
    assert pd.isna(z.iloc[18])
    assert not pd.isna(z.iloc[25])


# ---------------------------------------------------------------------------
# Short pressure point-in-time
# ---------------------------------------------------------------------------


def test_short_volume_ratio_serie_con_huecos():
    calendario = pd.bdate_range("2020-01-01", periods=10)
    sv = pd.DataFrame({"date": [calendario[0], calendario[3], calendario[7]], "short_volume_ratio": [0.1, 0.2, 0.3]})
    r = short_volume_ratio_serie(sv, calendario)
    assert r.iloc[0] == pytest.approx(0.1)
    assert pd.isna(r.iloc[1])
    assert r.iloc[3] == pytest.approx(0.2)
    assert r.iloc[7] == pytest.approx(0.3)


def test_days_to_cover_point_in_time():
    settlement1 = pd.Timestamp("2020-01-15")
    settlement2 = pd.Timestamp("2020-01-31")
    pub1 = settlement1 + pd.tseries.offsets.BDay(7)
    si = pd.DataFrame({
        "settlement_date": [settlement1, settlement2],
        "days_to_cover": [1.5, 3.0],
        "short_interest_change_pct": [0.05, -0.10],
    })
    antes_de_publicar = pub1 - pd.tseries.offsets.BDay(1)
    justo_publicado = pub1

    calendario = pd.DatetimeIndex([antes_de_publicar, justo_publicado])
    dtc = days_to_cover_serie(si, calendario)
    assert pd.isna(dtc.loc[antes_de_publicar])
    assert dtc.loc[justo_publicado] == pytest.approx(1.5)

    sic = short_interest_change_pct_serie(si, calendario)
    assert sic.loc[justo_publicado] == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# Scores agregados
# ---------------------------------------------------------------------------


def test_short_pressure_score_promedio_simple():
    tabla = pd.DataFrame({
        "short_volume_ratio": [0.2, 0.8],
        "short_volume_ratio_zscore_20d": [0.3, 0.9],
        "days_to_cover": [0.1, 0.7],
        "short_interest_change_pct": [0.4, 1.0],
    })
    r = SHORT_PRESSURE_SCORE(tabla)
    assert r.iloc[0] == pytest.approx((0.2 + 0.3 + 0.1 + 0.4) / 4)
    assert r.iloc[1] == pytest.approx((0.8 + 0.9 + 0.7 + 1.0) / 4)


def test_short_pressure_score_nan_si_falta_una_columna():
    tabla = pd.DataFrame({
        "short_volume_ratio": [0.2],
        "short_volume_ratio_zscore_20d": [0.3],
        "days_to_cover": [np.nan],
        "short_interest_change_pct": [0.4],
    })
    r = SHORT_PRESSURE_SCORE(tabla)
    assert pd.isna(r.iloc[0])


def test_price_exhaustion_score_orientacion():
    # Símbolo "muy agotado": retornos/drawdown/dist_sma/rsi en su percentil
    # MÁS BAJO (0.0) y volumen/volatilidad en su percentil MÁS ALTO (1.0) —
    # debe terminar con el PRICE_EXHAUSTION_SCORE más bajo del grupo.
    agotado = {
        "ret_1d": 0.0, "ret_5d": 0.0, "ret_20d": 0.0,
        "drawdown_5d": 0.0, "drawdown_20d": 0.0, "drawdown_60d": 0.0,
        "dist_sma20": 0.0, "dist_sma50": 0.0, "dist_sma200": 0.0,
        "rsi_2": 0.0, "rsi_14": 0.0,
        "realized_vol_20d": 1.0, "rel_volume": 1.0, "zscore_ret_5d": 0.0,
    }
    neutral = {k: 0.5 for k in agotado}
    tabla = pd.DataFrame([agotado, neutral])
    r = PRICE_EXHAUSTION_SCORE(tabla)
    assert r.iloc[0] < r.iloc[1]
    assert r.iloc[0] == pytest.approx(1.0 - 1.0)  # promedio orientado = 1.0 en los 14 -> score final = 0.0


def test_price_exhaustion_score_nan_si_falta_columna():
    fila = {k: 0.5 for k in [
        "ret_1d", "ret_5d", "ret_20d", "drawdown_5d", "drawdown_20d", "drawdown_60d",
        "dist_sma20", "dist_sma50", "dist_sma200", "rsi_2", "rsi_14",
        "realized_vol_20d", "rel_volume", "zscore_ret_5d",
    ]}
    fila["ret_1d"] = np.nan
    r = PRICE_EXHAUSTION_SCORE(pd.DataFrame([fila]))
    assert pd.isna(r.iloc[0])


# ---------------------------------------------------------------------------
# Reversal confirmation
# ---------------------------------------------------------------------------


def test_confirmacion_a():
    cierre = _serie([10.0, 12.0, 11.0])
    r = confirmacion_a(cierre)
    assert pd.isna(r.iloc[0])
    assert bool(r.iloc[1]) is True
    assert bool(r.iloc[2]) is False


def test_confirmacion_b_rango_cero_y_recuperacion():
    cierre = _serie([10.0, 9.0, 8.0, 9.5, 10.0])
    alto = cierre + 0.1
    bajo = cierre - 0.1
    r = confirmacion_b(cierre, alto, bajo, ventana_caida=3)
    assert pd.isna(r.iloc[1])

    plano_c = _plano(5, 10.0)
    plano_a = plano_c + 0.0
    plano_b = plano_c - 0.0
    r2 = confirmacion_b(plano_c, plano_a, plano_b, ventana_caida=3)
    assert bool(r2.iloc[3]) is False  # rango == 0 -> False, no NaN


def test_confirmacion_c():
    alto = _serie([10.0, 12.0, 11.0])
    r = confirmacion_c(alto)
    assert pd.isna(r.iloc[0])
    assert bool(r.iloc[1]) is True
    assert bool(r.iloc[2]) is False


def test_confirmacion_d():
    vol = _serie([0.3, 0.2, 0.4])
    r = confirmacion_d(vol)
    assert pd.isna(r.iloc[0])
    assert bool(r.iloc[1]) is True
    assert bool(r.iloc[2]) is False


def test_confirmacion_e():
    rel_volume = _serie([1.5, 0.8, 1.2, np.nan])
    cierre = _serie([10.0, 11.0, 9.0, 12.0])
    r = confirmacion_e(rel_volume, cierre)
    assert pd.isna(r.iloc[0])  # primera fila de cierre sin shift
    assert bool(r.iloc[1]) is True  # rel_volume>1 y cierre sube
    assert bool(r.iloc[2]) is False  # cierre baja
    assert pd.isna(r.iloc[3])  # rel_volume NaN


# ---------------------------------------------------------------------------
# Ensamblador
# ---------------------------------------------------------------------------


def test_calcular_features_simbolo_columnas_y_valor_conocido():
    n = 300
    idx = pd.bdate_range("2020-01-01", periods=n)
    cierre = pd.Series(100.0 + np.arange(n) * 0.1, index=idx)
    df = pd.DataFrame({
        "open": cierre, "high": cierre + 0.5, "low": cierre - 0.5,
        "close": cierre, "volume": pd.Series(1_000_000.0, index=idx),
    })
    sv = pd.DataFrame({"date": idx[::5], "short_volume_ratio": [0.3] * len(idx[::5])})
    si = pd.DataFrame({
        "settlement_date": [idx[0]],
        "days_to_cover": [2.0],
        "short_interest_change_pct": [0.1],
    })

    out = calcular_features_simbolo(df, sv, si)
    assert list(out.index) is not None and len(out) == n
    for col in COLUMNAS_ESPERADAS:
        assert col in out.columns, col

    r = momentum(cierre, 1)
    pd.testing.assert_series_equal(out["ret_1d"], r, check_names=False)

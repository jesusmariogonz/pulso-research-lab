import math

import numpy as np
import pandas as pd
import pytest

from prl.reverse_winners import forward_validation as fv


def _fecha(s):
    return pd.Timestamp(s)


# --------------------------------------------------------------------------- #
# serie_por_fecha
# --------------------------------------------------------------------------- #


def test_serie_por_fecha_basico():
    senales = pd.DataFrame(
        {
            "fecha": [_fecha("2022-01-01"), _fecha("2022-01-01"), _fecha("2022-01-15")],
            "ticker": ["A", "B", "C"],
            "retorno_30d": [0.10, 0.20, -0.05],
        }
    )
    out = fv.serie_por_fecha(senales)
    assert out.loc[_fecha("2022-01-01")] == pytest.approx(0.15)
    assert out.loc[_fecha("2022-01-15")] == pytest.approx(-0.05)


def test_serie_por_fecha_vacio():
    out = fv.serie_por_fecha(pd.DataFrame({"fecha": [], "retorno_30d": []}))
    assert len(out) == 0


# --------------------------------------------------------------------------- #
# retorno_acumulado / volatilidad / sharpe / max_drawdown
# --------------------------------------------------------------------------- #


def test_retorno_acumulado():
    serie = pd.Series([0.10, -0.05, 0.10])
    esperado = 1.10 * 0.95 * 1.10 - 1.0
    assert fv.retorno_acumulado(serie) == pytest.approx(esperado)
    assert math.isnan(fv.retorno_acumulado(pd.Series(dtype=float)))


def test_volatilidad_y_sharpe():
    serie = pd.Series([0.02, -0.01, 0.03, 0.00])
    vol_esperada = serie.std(ddof=1)
    assert fv.volatilidad(serie) == pytest.approx(vol_esperada)
    sharpe_esperado = serie.mean() / vol_esperada * math.sqrt(25.2)
    assert fv.sharpe(serie) == pytest.approx(sharpe_esperado)

    serie_1 = pd.Series([0.02])
    assert math.isnan(fv.volatilidad(serie_1))
    assert math.isnan(fv.sharpe(serie_1))


def test_max_drawdown():
    serie = pd.Series([0.10, -0.20, 0.05])
    equity = (1 + serie).cumprod()
    esperado = (equity / equity.cummax() - 1).min()
    assert fv.max_drawdown(serie) == pytest.approx(esperado)
    assert math.isnan(fv.max_drawdown(pd.Series(dtype=float)))


# --------------------------------------------------------------------------- #
# hit_rate
# --------------------------------------------------------------------------- #


def test_hit_rate():
    # Estrictamente > 0 (misma convención que frac_positivo en exp005.py
    # original) — 0.0 exacto NO cuenta como acierto, a propósito.
    senales = pd.DataFrame({"retorno_30d": [0.1, -0.1, 0.2, 0.0, -0.3, 0.05, 0.01, -0.02, 0.3, -0.4]})
    assert fv.hit_rate(senales) == pytest.approx(0.5)
    senales_nan = pd.DataFrame({"retorno_30d": [float("nan"), float("nan")]})
    assert math.isnan(fv.hit_rate(senales_nan))


# --------------------------------------------------------------------------- #
# turnover_por_fecha
# --------------------------------------------------------------------------- #


def test_turnover_por_fecha():
    composiciones = {
        _fecha("2022-01-01"): {"A", "B"},
        _fecha("2022-01-15"): {"A", "C"},
        _fecha("2022-01-29"): {"A", "C", "D"},
    }
    out = fv.turnover_por_fecha(composiciones)
    assert _fecha("2022-01-01") not in out.index
    assert out.loc[_fecha("2022-01-15")] == pytest.approx(0.5)
    assert out.loc[_fecha("2022-01-29")] == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# concentracion_del_efecto
# --------------------------------------------------------------------------- #


def test_concentracion_del_efecto_depende_de_pocas():
    retornos = [0.5, 0.4] + [-0.05] * 8
    senales = pd.DataFrame({"retorno_30d": retornos})
    out = fv.concentracion_del_efecto(senales, top_n=2)
    assert out["media_total"] > 0
    assert out["media_sin_top_n"] <= 0
    assert out["depende_de_pocas_senales"] is True


def test_concentracion_del_efecto_robusto():
    retornos = [0.5, 0.4] + [0.05] * 8
    senales = pd.DataFrame({"retorno_30d": retornos})
    out = fv.concentracion_del_efecto(senales, top_n=2)
    assert out["depende_de_pocas_senales"] is False


def test_concentracion_del_efecto_pocas_filas():
    senales = pd.DataFrame({"retorno_30d": [0.1, 0.2]})
    out = fv.concentracion_del_efecto(senales, top_n=5)
    assert math.isnan(out["media_sin_top_n"])
    assert out["depende_de_pocas_senales"] is False


# --------------------------------------------------------------------------- #
# exceso_vs_benchmark
# --------------------------------------------------------------------------- #


def test_exceso_vs_benchmark():
    a = pd.Series([0.10, 0.20], index=[_fecha("2022-01-01"), _fecha("2022-01-15")])
    b = pd.Series([0.05, 0.05, 0.05], index=[_fecha("2022-01-01"), _fecha("2022-01-15"), _fecha("2022-01-29")])
    out = fv.exceso_vs_benchmark(a, b)
    assert out.loc[_fecha("2022-01-01")] == pytest.approx(0.05)
    assert out.loc[_fecha("2022-01-15")] == pytest.approx(0.15)
    assert pd.isna(out.loc[_fecha("2022-01-29")])


# --------------------------------------------------------------------------- #
# desglose_por_periodo
# --------------------------------------------------------------------------- #


def test_desglose_por_periodo():
    senales = pd.DataFrame(
        {
            "fecha": [_fecha("2022-01-05"), _fecha("2022-02-10"), _fecha("2022-04-05")],
            "retorno_30d": [0.10, 0.20, -0.05],
        }
    )
    out = fv.desglose_por_periodo(senales, frecuencia="Q")
    assert len(out) == 2
    fila_q1 = out.iloc[0]
    assert fila_q1["n"] == 2
    assert fila_q1["media"] == pytest.approx(0.15)


# --------------------------------------------------------------------------- #
# desglose_por_regimen_vix
# --------------------------------------------------------------------------- #


def test_desglose_por_regimen_vix():
    fechas = [_fecha(f"2022-01-{d:02d}") for d in [1, 5, 10, 15, 20, 25]]
    vix = pd.Series([12.0, 13.0, 20.0, 21.0, 35.0, 36.0], index=fechas)
    senales = pd.DataFrame(
        {
            "fecha": fechas + [_fecha("2022-02-01")],
            "retorno_30d": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07],
        }
    )
    out = fv.desglose_por_regimen_vix(senales, vix)
    assert set(out.index) == {"bajo", "medio", "alto", "sin_dato"}
    assert out.loc["sin_dato", "n"] == 1


# --------------------------------------------------------------------------- #
# desglose_por_volatilidad
# --------------------------------------------------------------------------- #


def test_desglose_por_volatilidad():
    senales = pd.DataFrame(
        {
            "vol_realizada_20d_cruda": [0.10, 0.12, 0.30, 0.32, 0.60, 0.62, float("nan")],
            "retorno_30d": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.99],
        }
    )
    out = fv.desglose_por_volatilidad(senales)
    assert set(out.index) == {"bajo", "medio", "alto"}
    assert out["n"].sum() == 6


# --------------------------------------------------------------------------- #
# etiqueta_forward
# --------------------------------------------------------------------------- #


def test_etiqueta_forward():
    assert fv.etiqueta_forward(5, True, False) == "inconclusa"
    assert fv.etiqueta_forward(12, False, False) == "negativa"
    assert fv.etiqueta_forward(12, True, True) == "inconclusa"
    assert fv.etiqueta_forward(12, True, False) == "favorable"

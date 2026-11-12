import numpy as np
import pandas as pd
import pytest

from prl.growth_max.portfolio import (
    aplicar_leverage_y_cash,
    cash_pct_dinamico,
    costo_apalancamiento_diario,
    pesos_equal,
    pesos_inv_vol,
    pesos_kelly_frac,
    pesos_vol_target,
    retorno_esperado_trailing,
    varianza_trailing,
)


def _df(data, index=None):
    idx = index if index is not None else pd.bdate_range("2020-01-01", periods=len(next(iter(data.values()))))
    return pd.DataFrame(data, index=idx)


# ---------------------------------------------------------------------------
# pesos_equal
# ---------------------------------------------------------------------------


def test_pesos_equal_caso_basico():
    senales = _df({"A": [1.0], "B": [-1.0], "C": [0.0], "D": [np.nan]})
    out = pesos_equal(senales)
    assert out.iloc[0].tolist() == [0.5, -0.5, 0.0, 0.0]


def test_pesos_equal_fila_sin_senales_validas_da_cero():
    senales = _df({"A": [0.0], "B": [np.nan]})
    out = pesos_equal(senales)
    assert out.iloc[0].tolist() == [0.0, 0.0]


# ---------------------------------------------------------------------------
# pesos_inv_vol
# ---------------------------------------------------------------------------


def test_pesos_inv_vol_menor_vol_recibe_mayor_peso_y_gross_uno():
    senales = _df({"A": [1.0], "B": [1.0]})
    vol = _df({"A": [0.10], "B": [0.40]})
    out = pesos_inv_vol(senales, vol)
    assert out.iloc[0]["A"] > out.iloc[0]["B"]
    assert np.isclose(out.iloc[0].abs().sum(), 1.0)


def test_pesos_inv_vol_excluye_vol_nan_o_cero_sin_romper_normalizacion():
    senales = _df({"A": [1.0], "B": [1.0], "C": [1.0]})
    vol = _df({"A": [0.20], "B": [np.nan], "C": [0.0]})
    out = pesos_inv_vol(senales, vol)
    assert out.iloc[0]["B"] == 0.0
    assert out.iloc[0]["C"] == 0.0
    assert np.isclose(out.iloc[0]["A"], 1.0)


# ---------------------------------------------------------------------------
# pesos_vol_target
# ---------------------------------------------------------------------------


def test_pesos_vol_target_escala_proporcionalmente():
    senales = _df({"A": [1.0], "B": [-1.0]})
    vol = _df({"A": [0.10], "B": [0.20]})
    base = pesos_inv_vol(senales, vol)
    vol_aprox = np.sqrt((base.iloc[0] ** 2 * vol.iloc[0] ** 2).sum())
    objetivo = vol_aprox * 2
    out = pesos_vol_target(senales, vol, objetivo)
    assert np.allclose(out.iloc[0].to_numpy(), base.iloc[0].to_numpy() * 2)


def test_pesos_vol_target_sin_posiciones_no_lanza_ni_da_nan():
    senales = _df({"A": [0.0], "B": [np.nan]})
    vol = _df({"A": [0.10], "B": [0.20]})
    out = pesos_vol_target(senales, vol, objetivo=0.15)
    assert out.iloc[0].tolist() == [0.0, 0.0]
    assert not out.isna().any().any()


# ---------------------------------------------------------------------------
# retorno_esperado_trailing / varianza_trailing
# ---------------------------------------------------------------------------


def test_retorno_y_varianza_trailing_nan_antes_de_ventana():
    retornos = _df({"A": [0.01] * 25})
    mu = retorno_esperado_trailing(retornos, ventana=20)
    var = varianza_trailing(retornos, ventana=20)
    assert mu["A"].iloc[:19].isna().all()
    assert not pd.isna(mu["A"].iloc[19])
    assert var["A"].iloc[:19].isna().all()


def test_varianza_trailing_retornos_constantes_da_cero_no_nan():
    retornos = _df({"A": [0.01] * 25})
    var = varianza_trailing(retornos, ventana=20)
    assert var["A"].iloc[19] == 0.0


# ---------------------------------------------------------------------------
# pesos_kelly_frac
# ---------------------------------------------------------------------------


def test_pesos_kelly_frac_recorta_al_tope_por_posicion():
    senales = _df({"A": [1.0]})
    mu = _df({"A": [0.05]})
    varianza = _df({"A": [0.0001]})  # kelly = 500, muy por encima del tope
    out = pesos_kelly_frac(senales, mu, varianza, fraccion=1.0, tope_posicion=0.20)
    assert out.iloc[0]["A"] == pytest.approx(0.20)


def test_pesos_kelly_frac_reescala_si_gross_excede_uno_preservando_proporcion():
    # kelly_A = 0.007/0.01 = 0.7, kelly_B = 0.005/0.01 = 0.5 — ninguno toca
    # el tope (0.8), pero la suma (1.2) excede el gross máximo de 1.0.
    senales = _df({"A": [1.0], "B": [1.0]})
    mu = _df({"A": [0.007], "B": [0.005]})
    varianza = _df({"A": [0.01], "B": [0.01]})
    out = pesos_kelly_frac(senales, mu, varianza, fraccion=1.0, tope_posicion=0.80)
    gross = out.iloc[0].abs().sum()
    assert gross == pytest.approx(1.0)
    assert out.iloc[0]["A"] / out.iloc[0]["B"] == pytest.approx(0.7 / 0.5)


def test_pesos_kelly_frac_mu_nan_con_varianza_valida_no_contagia_nan():
    senales = _df({"A": [1.0], "B": [1.0]})
    mu = _df({"A": [np.nan], "B": [0.01]})
    varianza = _df({"A": [0.001], "B": [0.001]})
    out = pesos_kelly_frac(senales, mu, varianza, fraccion=0.5, tope_posicion=0.20)
    assert out.iloc[0]["A"] == 0.0
    assert not pd.isna(out.iloc[0]["B"])


# ---------------------------------------------------------------------------
# cash_pct_dinamico
# ---------------------------------------------------------------------------


def test_cash_pct_dinamico_todos_los_casos():
    regimen = pd.Series([1.0, 2.0, 3.0, 4.0, np.nan])
    out = cash_pct_dinamico(regimen)
    assert out.tolist() == [0.02, 0.02, 0.10, 0.10, 0.10]


# ---------------------------------------------------------------------------
# aplicar_leverage_y_cash / costo_apalancamiento_diario
# ---------------------------------------------------------------------------


def test_aplicar_leverage_y_cash_escala_correctamente():
    pesos_base = _df({"A": [0.5, -0.3], "B": [0.5, 0.3]})
    cash_pct = pd.Series([0.10, 0.10], index=pesos_base.index)
    out = aplicar_leverage_y_cash(pesos_base, L=2.0, cash_pct=cash_pct)
    esperado = pesos_base * 1.8
    assert np.allclose(out.to_numpy(), esperado.to_numpy())


def test_aplicar_leverage_y_cash_rechaza_cash_fuera_de_rango():
    pesos_base = _df({"A": [0.5]})
    with pytest.raises(ValueError):
        aplicar_leverage_y_cash(pesos_base, L=1.0, cash_pct=pd.Series([1.5], index=pesos_base.index))
    with pytest.raises(ValueError):
        aplicar_leverage_y_cash(pesos_base, L=1.0, cash_pct=pd.Series([-0.1], index=pesos_base.index))


def test_costo_apalancamiento_sin_leverage_es_cero_incluso_con_tasa_nan():
    tasa = pd.Series([0.03, np.nan, 0.05])
    out = costo_apalancamiento_diario(L=1.0, tasa_cash_anual=tasa, spread_anual=0.01)
    assert (out == 0.0).all()


def test_costo_apalancamiento_con_leverage_coincide_con_calculo_manual():
    tasa = pd.Series([0.04, 0.04])
    out = costo_apalancamiento_diario(L=2.0, tasa_cash_anual=tasa, spread_anual=0.02)
    esperado = (2.0 - 1) * (0.04 / 252 + 0.02 / 252)
    assert np.allclose(out.to_numpy(), esperado)

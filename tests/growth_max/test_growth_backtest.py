import numpy as np
import pandas as pd
import pytest

from prl.growth_max.backtest import costo_transaccion_diario, ejecutar_backtest, metricas


def _idx(n):
    return pd.bdate_range("2020-01-01", periods=n)


def test_rezago_sin_look_ahead():
    idx = _idx(5)
    # El peso salta de 0.0 a 1.0 en la fila 2 (índice 2).
    pesos = pd.DataFrame({"A": [0.0, 0.0, 1.0, 1.0, 1.0]}, index=idx)
    retornos = pd.DataFrame({"A": [0.0, 0.0, 0.10, 0.20, 0.0]}, index=idx)
    costo_lev = pd.Series(0.0, index=idx)
    out = ejecutar_backtest(pesos, retornos, costo_lev, costo_por_lado=0.0)
    # Fila 2: el peso vigente todavía es el de la fila 1 (0.0) -> no captura el +10%.
    assert out["ret"].iloc[2] == 0.0
    # Fila 3: ya rige el peso decidido en la fila 2 (1.0) -> sí captura el +20%.
    assert out["ret"].iloc[3] == pytest.approx(0.20)


def test_primer_dia_retorno_y_turnover_cero():
    idx = _idx(3)
    pesos = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx)
    retornos = pd.DataFrame({"A": [0.05, 0.05, 0.05]}, index=idx)
    costo_lev = pd.Series(0.0, index=idx)
    out = ejecutar_backtest(pesos, retornos, costo_lev, costo_por_lado=0.001)
    assert out["ret"].iloc[0] == 0.0
    assert out["turnover"].iloc[0] == 0.0


def test_primer_dia_con_costo_de_apalancamiento_no_nulo():
    idx = _idx(3)
    pesos = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx)
    retornos = pd.DataFrame({"A": [0.05, 0.05, 0.05]}, index=idx)
    costo_lev = pd.Series(0.002, index=idx)
    out = ejecutar_backtest(pesos, retornos, costo_lev, costo_por_lado=0.001)
    assert out["ret"].iloc[0] == pytest.approx(-0.002)


def test_turnover_y_costo_de_transaccion():
    idx = _idx(4)
    # Fila 0 y 1 deciden la misma posición (0.5,0.5): sin cambio real.
    # Fila 2 decide (1.0,0.0): ese cambio rige recién desde la fila 3.
    pesos = pd.DataFrame({"A": [0.5, 0.5, 1.0, 1.0], "B": [0.5, 0.5, 0.0, 0.0]}, index=idx)
    retornos = pd.DataFrame({"A": [0.0] * 4, "B": [0.0] * 4}, index=idx)
    costo_lev = pd.Series(0.0, index=idx)
    out = ejecutar_backtest(pesos, retornos, costo_lev, costo_por_lado=0.001)
    assert out["turnover"].iloc[2] == 0.0  # pesos_aplicados no cambió entre fila 1 y 2
    assert out["turnover"].iloc[3] == pytest.approx(1.0)
    assert out["costo_transaccion"].iloc[3] == pytest.approx(0.001)


def test_pesos_con_nan_lanza_value_error():
    idx = _idx(2)
    pesos = pd.DataFrame({"A": [1.0, np.nan]}, index=idx)
    retornos = pd.DataFrame({"A": [0.01, 0.01]}, index=idx)
    with pytest.raises(ValueError):
        ejecutar_backtest(pesos, retornos, pd.Series(0.0, index=idx))


def test_posicion_sin_retorno_lanza_value_error():
    idx = _idx(3)
    pesos = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx)
    retornos = pd.DataFrame({"A": [0.01, np.nan, 0.01]}, index=idx)
    with pytest.raises(ValueError):
        ejecutar_backtest(pesos, retornos, pd.Series(0.0, index=idx))


def test_peso_cero_con_retorno_nan_no_lanza_excepcion():
    idx = _idx(3)
    pesos = pd.DataFrame({"A": [1.0, 1.0, 1.0], "B": [0.0, 0.0, 0.0]}, index=idx)
    retornos = pd.DataFrame({"A": [0.01, 0.01, 0.01], "B": [np.nan, np.nan, np.nan]}, index=idx)
    out = ejecutar_backtest(pesos, retornos, pd.Series(0.0, index=idx), costo_por_lado=0.0)
    assert not out["ret"].isna().any()


def test_equity_consistente_con_retornos():
    idx = _idx(4)
    pesos = pd.DataFrame({"A": [1.0, 1.0, 1.0, 1.0]}, index=idx)
    retornos = pd.DataFrame({"A": [0.0, 0.01, -0.02, 0.03]}, index=idx)
    out = ejecutar_backtest(pesos, retornos, pd.Series(0.0, index=idx), costo_por_lado=0.0)
    esperado = (1 + out["ret"]).prod()
    assert out["equity"].iloc[-1] == pytest.approx(esperado)


# ---------------------------------------------------------------------------
# metricas
# ---------------------------------------------------------------------------


def test_metricas_sin_drawdown_da_calmar_nan():
    idx = _idx(300)
    ret = pd.Series(0.0005, index=idx)
    m = metricas(ret)
    assert m["max_drawdown"] == 0.0
    assert pd.isna(m["calmar"])


def test_metricas_sin_retornos_negativos_da_sortino_nan():
    idx = _idx(50)
    ret = pd.Series(0.001, index=idx)
    m = metricas(ret)
    assert pd.isna(m["sortino"])


def test_metricas_cagr_coincide_con_calculo_manual():
    idx = _idx(252)
    r = 0.001
    ret = pd.Series(r, index=idx)
    m = metricas(ret)
    equity_final = (1 + ret).prod()
    dias_calendario = (idx[-1] - idx[0]).days
    esperado = equity_final ** (365.25 / dias_calendario) - 1
    assert m["cagr"] == pytest.approx(esperado)
    assert m["n_days"] == 252

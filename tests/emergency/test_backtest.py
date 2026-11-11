import numpy as np
import pandas as pd
import pytest

from prl.emergency import backtest as bt


def _idx(n):
    return pd.bdate_range("2020-01-01", periods=n)


def _precios(n=30, **cols):
    idx = _idx(n)
    return pd.DataFrame({k: pd.Series(v, index=idx) for k, v in cols.items()})


def test_exposicion_total_sin_costos_replica_comprar_y_mantener():
    n = 40
    rng = np.random.default_rng(0)
    a = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, n)))
    p = _precios(n, A=a, B=np.full(n, 100.0))
    out = bt.run_backtest(p, pd.Series(1.0, index=p.index), "A", {"B": 1.0}, cost_per_side=0.0)
    assert out["equity"].iloc[0] == pytest.approx(1.0)
    assert out["equity"].iloc[-1] == pytest.approx(a[-1] / a[0])
    assert out["ret"].iloc[0] == 0.0


def _caida_en_dia_11():
    n = 20
    a = np.full(n, 100.0)
    a[11:] = 50.0  # el retorno de -50% ocurre en la fila 11
    return _precios(n, A=a, B=np.full(n, 100.0))


def test_ejecucion_t_mas_1_evita_la_caida_si_se_decide_el_dia_anterior():
    p = _caida_en_dia_11()
    e = pd.Series(1.0, index=p.index)
    e.iloc[10:] = 0.0  # decidido al cierre de la fila 10, aplica desde la fila 11
    out = bt.run_backtest(p, e, "A", {"B": 1.0}, cost_per_side=0.0)
    assert out["equity"].iloc[-1] == pytest.approx(1.0)


def test_no_se_evita_la_caida_si_se_decide_el_mismo_dia():
    p = _caida_en_dia_11()
    e = pd.Series(1.0, index=p.index)
    e.iloc[11:] = 0.0  # decidido al cierre de la fila 11: la caída ya ocurrió
    out = bt.run_backtest(p, e, "A", {"B": 1.0}, cost_per_side=0.0)
    assert out["equity"].iloc[-1] == pytest.approx(0.5)


def test_costos_por_cambio_de_exposicion():
    n = 20
    p = _precios(n, A=np.full(n, 100.0), B=np.full(n, 100.0))
    e = pd.Series(1.0, index=p.index)
    e.iloc[8:] = 0.0
    out = bt.run_backtest(p, e, "A", {"B": 1.0}, cost_per_side=0.001)
    assert out["equity"].iloc[-1] == pytest.approx(1 - 0.002)
    assert out["cost"].sum() == pytest.approx(0.002)
    e2 = e.copy()
    e2.iloc[14:] = 1.0
    out2 = bt.run_backtest(p, e2, "A", {"B": 1.0}, cost_per_side=0.001)
    assert out2["equity"].iloc[-1] == pytest.approx((1 - 0.002) ** 2)


def test_refugio_con_varios_activos_se_rebalancea_a_diario():
    n = 25
    rng = np.random.default_rng(2)
    b = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    p = _precios(n, A=np.full(n, 100.0), B=b, C=c)
    out = bt.run_backtest(p, pd.Series(0.0, index=p.index), "A", {"B": 0.5, "C": 0.5}, cost_per_side=0.0)
    esperado = 0.5 * pd.Series(b, index=p.index).pct_change() + 0.5 * pd.Series(c, index=p.index).pct_change()
    pd.testing.assert_series_equal(out["ret"].iloc[1:], esperado.iloc[1:], check_names=False)


def test_exposicion_aplicada_es_la_del_dia_anterior():
    n = 10
    p = _precios(n, A=np.full(n, 100.0), B=np.full(n, 100.0))
    e = pd.Series([1, 1, 0.5, 0.5, 0, 0, 0, 0, 0, 0], index=p.index, dtype=float)
    out = bt.run_backtest(p, e, "A", {"B": 1.0}, cost_per_side=0.0)
    assert list(out["exposure_applied"]) == [1, 1, 1, 0.5, 0.5, 0, 0, 0, 0, 0]


def test_metricas_basicas():
    idx = _idx(5)
    equity = pd.Series([1.0, 1.2, 0.6, 0.9, 1.5], index=idx)
    r = equity.pct_change().fillna(0.0)
    m = bt.metrics(r)
    anios = (idx[-1] - idx[0]).days / 365.25
    assert m["max_drawdown"] == pytest.approx(-0.5)
    assert m["cagr"] == pytest.approx(1.5 ** (1 / anios) - 1)
    assert m["calmar"] == pytest.approx(m["cagr"] / 0.5)
    assert m["n_days"] == 5
    assert set(m) >= {"cagr", "max_drawdown", "calmar", "sharpe", "sortino", "n_days"}


def test_sharpe_positivo_con_deriva_positiva():
    idx = _idx(500)
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.001, 0.01, 500), index=idx)
    m = bt.metrics(r)
    assert m["sharpe"] > 0 and m["sortino"] > 0
    esperado = r.mean() / r.std(ddof=1) * np.sqrt(252)
    assert m["sharpe"] == pytest.approx(esperado)


def _base_sin_nan(n=15):
    p = _precios(n, A=np.linspace(100, 110, n), B=np.full(n, 100.0))
    return p, pd.Series(1.0, index=p.index)


def test_rechaza_nan_en_la_exposicion():
    p, e = _base_sin_nan()
    e.iloc[4:6] = np.nan
    with pytest.raises(ValueError):
        bt.run_backtest(p, e, "A", {"B": 1.0})


def test_rechaza_exposicion_fuera_de_rango():
    p, e = _base_sin_nan()
    e.iloc[3] = 1.5
    with pytest.raises(ValueError):
        bt.run_backtest(p, e, "A", {"B": 1.0})


def test_rechaza_nan_en_los_precios_usados_aunque_la_exposicion_sea_total():
    p, e = _base_sin_nan()
    p.loc[p.index[:4], "B"] = np.nan  # refugio sin historia al inicio
    with pytest.raises(ValueError):
        bt.run_backtest(p, e, "A", {"B": 1.0})


def test_ignora_columnas_no_usadas_con_nan():
    p, e = _base_sin_nan()
    p["Z"] = np.nan
    out = bt.run_backtest(p, e, "A", {"B": 1.0}, cost_per_side=0.0)
    assert out["ret"].notna().all()


def test_rechaza_pesos_del_refugio_que_no_suman_uno_o_activo_ausente():
    p, e = _base_sin_nan()
    with pytest.raises(ValueError):
        bt.run_backtest(p, e, "A", {"B": 0.5})
    with pytest.raises(ValueError):
        bt.run_backtest(p, e, "A", {"NO_EXISTE": 1.0})

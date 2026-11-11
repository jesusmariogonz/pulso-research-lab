import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from prl.emergency import evaluation as ev


def _idx(a="2010-01-01", b="2013-12-31"):
    return pd.bdate_range(a, b)


# ---------------- walk-forward ----------------
def test_walk_forward_no_mira_el_anio_de_prueba_para_elegir():
    idx = _idx()
    rng = np.random.default_rng(0)
    base = pd.Series(rng.normal(0.0004, 0.005, len(idx)), index=idx)
    a = base.copy()
    b = base.copy()
    b[b.index.year <= 2011] *= 0.0  # B es malo antes (retorno 0 => Calmar NaN/ bajo)
    b[b.index.year <= 2011] = -0.001  # claramente peor en entrenamiento
    b[b.index.year == 2012] = 0.01  # pero espectacular en 2012 (año de prueba)
    oos, elegidas = ev.walk_forward_select({"A": a, "B": b}, first_test_year=2012)
    assert elegidas[2012] == "A"  # elegida solo con datos hasta 2011
    pd.testing.assert_series_equal(oos[oos.index.year == 2012], a[a.index.year == 2012], check_names=False)
    assert oos.index.min().year == 2012 and oos.index.is_monotonic_increasing
    assert set(elegidas) == {2012, 2013}


def test_walk_forward_exige_entrenamiento_minimo():
    idx = _idx("2012-01-01", "2013-12-31")
    r = pd.Series(0.001, index=idx)
    with pytest.raises(ValueError):
        ev.walk_forward_select({"A": r}, first_test_year=2012)


# ---------------- bootstrap ----------------
def _dif_medias(a, b):
    return float(a.mean() - b.mean())


def test_bootstrap_identicas_da_intervalo_cero_y_es_reproducible():
    idx = _idx()
    r = pd.Series(np.random.default_rng(1).normal(0, 0.01, len(idx)), index=idx)
    lo, hi = ev.block_bootstrap_ci(r, r, _dif_medias, n_boot=200, seed=3)
    assert lo == 0.0 and hi == 0.0
    r2 = pd.Series(np.random.default_rng(2).normal(0, 0.01, len(idx)), index=idx)
    x = ev.block_bootstrap_ci(r, r2, _dif_medias, n_boot=200, seed=7)
    y = ev.block_bootstrap_ci(r, r2, _dif_medias, n_boot=200, seed=7)
    assert x == y and x[0] <= x[1]


def test_bootstrap_detecta_una_mejora_clara_y_exige_bloque_valido():
    idx = _idx()
    rng = np.random.default_rng(4)
    b = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    a = b + 0.002  # mejora constante de 0.2% diario
    lo, hi = ev.block_bootstrap_ci(a, b, _dif_medias, n_boot=300, seed=0)
    assert lo > 0
    with pytest.raises(ValueError):
        ev.block_bootstrap_ci(a.iloc[:10], b.iloc[:10], _dif_medias, block=20)


# ---------------- Deflated Sharpe ----------------
def test_dsr_con_un_intento_es_el_psr_contra_cero_y_baja_con_mas_intentos():
    idx = _idx("2005-01-01", "2013-12-31")
    r = pd.Series(np.random.default_rng(5).normal(0.0006, 0.01, len(idx)), index=idx)
    n = len(r)
    sr = r.mean() / r.std(ddof=1)
    g3, g4 = r.skew(), r.kurt() + 3
    sr_std = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr**2) / (n - 1))
    assert ev.deflated_sharpe_ratio(r, 1) == pytest.approx(norm.cdf(sr / sr_std))
    d10, d162 = ev.deflated_sharpe_ratio(r, 10), ev.deflated_sharpe_ratio(r, 162)
    assert 0.0 <= d162 < d10 < ev.deflated_sharpe_ratio(r, 1) <= 1.0


# ---------------- episodios ----------------
def _serie_con_crash():
    idx = pd.bdate_range("2020-01-01", periods=300)
    p = np.full(300, 100.0)
    p[100:140] = np.linspace(100, 70, 40)  # caída del 30% entre filas 100 y 139
    p[140:] = np.linspace(70, 90, 160)
    return pd.Series(p, index=idx)


def test_episode_report_detecta_con_anticipacion():
    close = _serie_con_crash()
    nivel = pd.Series(0, index=close.index)
    nivel.iloc[110:] = 2  # alerta desde la fila 110
    ep = [{"name": "crash", "peak": str(close.index[99].date()), "trough": str(close.index[139].date())}]
    rep = ev.episode_report(close, nivel, ep)["episodes"][0]
    cruz = close.index[(close / close.iloc[99] - 1 <= -0.20) & (close.index > close.index[99])][0]
    assert rep["cross20"] == str(cruz.date())
    assert rep["detection_date"] == str(close.index[110].date())
    assert rep["lead_days"] == (cruz - close.index[110]).days
    assert rep["detected"] is True


def test_episode_report_marca_no_detectado_si_la_alerta_llega_tarde():
    close = _serie_con_crash()
    nivel = pd.Series(0, index=close.index)
    nivel.iloc[139:] = 3  # después de cruzar el -20%
    ep = [{"name": "crash", "peak": str(close.index[99].date()), "trough": str(close.index[139].date())}]
    rep = ev.episode_report(close, nivel, ep)["episodes"][0]
    assert rep["detected"] is False and rep["detection_date"] is None and rep["lead_days"] is None


def test_alarmas_falsas_y_no_evaluables():
    idx = pd.bdate_range("2020-01-01", periods=300)
    close = pd.Series(100.0 + np.sin(np.arange(300) / 20), index=idx)  # sin caídas de 10%
    nivel = pd.Series(0, index=idx)
    nivel.iloc[50:55] = 4   # alarma falsa (nada cae 10%)
    nivel.iloc[280:285] = 4  # quedan < 60 filas: no evaluable
    r = ev.episode_report(close, nivel, [])["alarms"]
    assert r["n_alarms"] == 2 and r["n_false"] == 1 and r["n_unevaluable"] == 1
    assert r["false_dates"] == [str(idx[50].date())]


def test_non_episode_shortfall_excluye_los_episodios():
    idx = pd.bdate_range("2020-01-01", periods=10)
    bench = pd.Series(0.01, index=idx)
    modelo = pd.Series(0.00, index=idx)
    ep = [{"name": "e", "peak": str(idx[3].date()), "trough": str(idx[5].date())}]
    esperado = 1.01**7 - 1.0
    assert ev.non_episode_shortfall(modelo, bench, ep) == pytest.approx(esperado)


# ---------------- etiqueta ----------------
def _m(**kw):
    base = dict(maxdd_model=-0.30, maxdd_bh=-0.55, cagr_model=0.10, cagr_bh=0.105,
                calmar_model=0.33, calmar_sma=0.20, calmar_diff_ci_lo=0.05)
    base.update(kw)
    return base


def test_label_validated_rejected_inconclusive():
    assert ev.label_result(_m()) == "VALIDATED"
    assert ev.label_result(_m(calmar_model=0.15)) == "REJECTED"          # no supera a SMA200
    assert ev.label_result(_m(maxdd_model=-0.56)) == "REJECTED"          # no reduce el MaxDD
    assert ev.label_result(_m(maxdd_model=-0.45)) == "INCONCLUSIVE"      # reduce pero > 70%
    assert ev.label_result(_m(cagr_model=0.08)) == "INCONCLUSIVE"        # sacrifica CAGR
    assert ev.label_result(_m(calmar_diff_ci_lo=-0.01)) == "INCONCLUSIVE"  # IC incluye 0


def test_label_con_datos_faltantes_es_inconcluso():
    assert ev.label_result(_m(calmar_sma=float("nan"))) == "INCONCLUSIVE"
    d = _m()
    d.pop("cagr_bh")
    assert ev.label_result(d) == "INCONCLUSIVE"

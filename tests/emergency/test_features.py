import numpy as np
import pandas as pd
import pytest

from prl.emergency import features as f


def _serie(n=900, seed=0, start=100.0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.Series(start * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))), index=idx)


def _vix(n=900, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.Series(15 + np.abs(rng.normal(0, 1.5, n)), index=idx)


SERIES_FNS = [f.trend_stress, f.drawdown_velocity_stress, f.credit_stress, f.vol_stress]


def test_expanding_zscore_formula_y_minimo_de_periodos():
    s = _serie()
    z = f.expanding_zscore(s, min_periods=50)
    assert z.iloc[:49].isna().all() and z.iloc[49:].notna().all()
    t = 100
    w = s.iloc[: t + 1]
    assert z.iloc[t] == pytest.approx((w.iloc[-1] - w.mean()) / w.std(ddof=1))


@pytest.mark.parametrize("fn", SERIES_FNS)
def test_sin_look_ahead_truncar_no_cambia_el_pasado(fn):
    s = _vix() if fn in (f.vol_stress, f.credit_stress) else _serie()
    corte = 600
    pd.testing.assert_series_equal(fn(s).iloc[:corte], fn(s.iloc[:corte]), check_names=False)


@pytest.mark.parametrize("fn", SERIES_FNS)
def test_sin_look_ahead_alterar_el_futuro_no_cambia_el_pasado(fn):
    s = _vix() if fn in (f.vol_stress, f.credit_stress) else _serie()
    corte = 600
    s2 = s.copy()
    s2.iloc[corte:] = s2.iloc[corte:] * 3
    pd.testing.assert_series_equal(fn(s).iloc[:corte], fn(s2).iloc[:corte], check_names=False)


def test_trend_stress_sube_cuando_el_precio_cae_bajo_su_media():
    idx = pd.bdate_range("2015-01-01", periods=700)
    subida = 100 * np.exp(np.linspace(0, 0.8, 500))
    caida = subida[-1] * np.exp(np.linspace(0, -0.5, 200))
    s = pd.Series(np.concatenate([subida, caida]), index=idx)
    z = f.trend_stress(s)
    assert z.iloc[-1] > z.iloc[499] + 1.0


def test_vol_stress_se_dispara_con_un_pico_de_vix():
    v = _vix(700)
    v.iloc[-1] = 70.0
    z = f.vol_stress(v)
    assert z.iloc[-1] > 3.0 and z.iloc[-2] < 2.0


def test_credit_stress_se_dispara_con_un_pico_de_spread():
    sp = _vix(700) / 10.0
    sp.iloc[-1] = 12.0
    assert f.credit_stress(sp).iloc[-1] > 3.0


def test_drawdown_velocity_stress_detecta_caida_rapida():
    idx = pd.bdate_range("2015-01-01", periods=700)
    p = pd.Series(100.0 + np.sin(np.arange(700) / 10), index=idx)
    p.iloc[-5:] = p.iloc[-6] * np.array([0.97, 0.94, 0.92, 0.90, 0.88])
    assert f.drawdown_velocity_stress(p).iloc[-1] > 3.0


def test_breadth_stress_sube_si_rsp_pierde_contra_spy():
    spy = _serie(700, seed=3)
    oscila = 1 + 0.01 * np.sin(np.arange(700) / 7)  # ratio no constante (si no, el z-score es 0/0)
    rsp_ok = spy * 0.5 * oscila
    ratio_cae = np.concatenate([np.ones(500), np.linspace(1, 0.75, 200)])
    rsp_mal = spy * 0.5 * oscila * ratio_cae
    assert f.breadth_stress(rsp_mal, spy).iloc[-1] > f.breadth_stress(rsp_ok, spy).iloc[-1] + 1.0


def test_breadth_stress_sin_look_ahead():
    spy, rsp = _serie(900, seed=3), _serie(900, seed=4)
    full = f.breadth_stress(rsp, spy)
    corte = f.breadth_stress(rsp.iloc[:600], spy.iloc[:600])
    pd.testing.assert_series_equal(full.iloc[:600], corte, check_names=False)


def _sectores(n=700, comun_desde=500, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    comun = rng.normal(0, 0.01, n)
    peso = np.where(np.arange(n) >= comun_desde, 0.95, 0.1)
    data = {c: peso * comun + (1 - peso) * rng.normal(0, 0.01, n) for c in "ABCDEFGHI"}
    return pd.DataFrame(data, index=idx)


def test_correlation_stress_sube_cuando_los_sectores_se_mueven_juntos():
    z = f.correlation_stress(_sectores())
    assert z.iloc[-1] > z.iloc[490] + 1.0


def test_correlation_stress_sin_look_ahead():
    r = _sectores(900, comun_desde=700)
    full = f.correlation_stress(r)
    corte = f.correlation_stress(r.iloc[:600])
    pd.testing.assert_series_equal(full.iloc[:600], corte, check_names=False)


def test_composite_score_promedia_solo_las_dimensiones_disponibles():
    dims = pd.DataFrame({"A": [1.0, 2.0, np.nan], "B": [3.0, np.nan, np.nan], "C": [9.0, 9.0, 9.0]})
    out = f.composite_score(dims, {"A": 1.0, "B": 3.0})
    assert out.iloc[0] == pytest.approx((1 * 1 + 3 * 3) / 4)
    assert out.iloc[1] == pytest.approx(2.0)
    assert np.isnan(out.iloc[2])

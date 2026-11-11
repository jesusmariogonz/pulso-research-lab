import numpy as np
import pandas as pd
import pytest

from prl.emergency import inputs


def test_cash_index_sintetico_usa_la_tasa_del_dia_anterior():
    idx = pd.bdate_range("2010-01-01", periods=10)
    dtb3 = pd.Series([5.0, 5.0, 5.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0], index=idx)
    bil = pd.Series(dtype=float)
    c = inputs.build_cash_index(dtb3, bil)
    assert c.iloc[0] == pytest.approx(1.0)
    assert c.iloc[1] == pytest.approx(1 + 0.05 / 252)
    # el día 3 todavía usa la tasa del día 2 (5%), no la del día 3 (10%)
    assert c.iloc[3] / c.iloc[2] == pytest.approx(1 + 0.05 / 252)
    assert c.iloc[4] / c.iloc[3] == pytest.approx(1 + 0.10 / 252)


def test_cash_index_empalma_con_bil_desde_su_primera_fecha():
    idx = pd.bdate_range("2010-01-01", periods=30)
    dtb3 = pd.Series(2.0, index=idx)
    bil = pd.Series(np.linspace(90, 93, 10), index=idx[20:])
    c = inputs.build_cash_index(dtb3, bil)
    t0 = idx[20]
    assert c.loc[idx[-1]] / c.loc[t0] == pytest.approx(bil.iloc[-1] / bil.iloc[0])
    assert c.loc[t0] == pytest.approx((1 + 0.02 / 252) ** 20)
    assert c.index.is_monotonic_increasing


def test_sma200_exposure():
    idx = pd.bdate_range("2015-01-01", periods=400)
    p = pd.Series(np.concatenate([np.linspace(100, 150, 250), np.linspace(150, 90, 150)]), index=idx)
    e = inputs.sma200_exposure(p)
    assert (e.iloc[:199] == 1.0).all()
    assert e.iloc[240] == 1.0 and e.iloc[-1] == 0.0
    corte = inputs.sma200_exposure(p.iloc[:300])
    pd.testing.assert_series_equal(e.iloc[:300], corte, check_names=False)


def test_common_start():
    a = pd.Series([np.nan, np.nan, 1.0, 2.0], index=pd.bdate_range("2020-01-01", periods=4))
    b = pd.Series([1.0, 2.0, 3.0, 4.0], index=pd.bdate_range("2020-01-01", periods=4))
    c = pd.Series([np.nan, 5.0, 6.0, 7.0], index=pd.bdate_range("2020-01-01", periods=4))
    assert inputs.common_start({"a": a, "b": b, "c": c}) == pd.Timestamp("2020-01-03")

import json

import numpy as np
import pandas as pd
import pytest

from prl.emergency import daily

SECTORES = ["XLK", "XLE", "XLF", "XLV", "XLP", "XLU", "XLY", "XLI", "XLB"]


def _precio(idx, seed, mu=0.0003, sd=0.01, inicio=100.0):
    r = np.random.default_rng(seed).normal(mu, sd, len(idx))
    return pd.Series(inicio * np.exp(np.cumsum(r)), index=idx)


def _datos(n_fin="2012-12-31", crash=True):
    idx = pd.bdate_range("2003-01-01", n_fin)
    spy = _precio(idx, 1)
    if crash and len(idx) > 1700:
        spy.iloc[1500:1560] *= np.linspace(1.0, 0.6, 60)
        spy.iloc[1560:] *= 0.6
    vix = pd.Series(15 + 10 * (spy.pct_change().abs().rolling(10).mean().fillna(0) * 100), index=idx)
    baa = pd.Series(2.0 + np.abs(np.sin(np.arange(len(idx)) / 200)), index=idx)
    rsp = spy * 0.5 * (1 + 0.01 * np.sin(np.arange(len(idx)) / 9))
    sect = pd.DataFrame({s: _precio(idx, 10 + i) for i, s in enumerate(SECTORES)})
    return spy, vix, baa, rsp, sect


def test_compute_indicator_columnas_y_tipos():
    df = daily.compute_indicator(*_datos())
    for c in ["trend", "vol", "correlation", "credit", "breadth", "drawdown_velocity", "score", "level", "exposure"]:
        assert c in df.columns
    assert np.issubdtype(df["level"].dtype, np.integer)
    assert df["exposure"].isin([1.0, 0.75, 0.5, 0.25, 0.0]).all()
    assert df["score"].notna().sum() > 1000


def test_sin_look_ahead_el_valor_de_un_dia_no_cambia_si_se_trunca_el_futuro():
    spy, vix, baa, rsp, sect = _datos()
    full = daily.compute_indicator(spy, vix, baa, rsp, sect)
    corte = spy.index[1800]
    t = lambda x: x.loc[:corte]  # noqa: E731
    parcial = daily.compute_indicator(t(spy), t(vix), t(baa), t(rsp), sect.loc[:corte])
    assert parcial.loc[corte, "score"] == pytest.approx(full.loc[corte, "score"])
    assert parcial.loc[corte, "level"] == full.loc[corte, "level"]


def test_latest_payload_claves_gauge_y_serializable():
    df = daily.compute_indicator(*_datos())
    p = daily.latest_payload(df)
    json.dumps(p, allow_nan=False)
    assert p["status"] == "EXPERIMENTAL" and p["disclaimer"]
    assert 0.0 <= p["gauge"] <= 100.0
    assert p["gauge"] == pytest.approx(round(min(max(p["score"], 0.0), 5.0) / 5.0 * 100.0, 1), abs=0.11)
    assert p["level_name"] == daily.LEVEL_NAMES[p["level"]]
    assert set(p["dimensions"]) == {"trend", "vol", "correlation", "credit", "breadth", "drawdown_velocity"}
    assert set(p["dimension_gauges"]) == set(p["dimensions"])
    assert p["params"] == {"weights": "equal", "theta": 1.0, "k": 3, "m": 10}
    assert p["data_through"] == str(df["score"].dropna().index[-1].date())


def test_latest_payload_sin_datos():
    idx = pd.bdate_range("2020-01-01", periods=50)
    df = daily.compute_indicator(*(_datos("2003-04-30", crash=False)))  # muy poca historia -> sin score
    assert df["score"].notna().sum() == 0
    p = daily.latest_payload(df)
    assert p["status"] == "SIN_DATOS" and p["data_through"] is None
    json.dumps(p, allow_nan=False)
    assert idx is not None


def test_history_payload_orden_y_formato():
    df = daily.compute_indicator(*_datos())
    h = daily.history_payload(df)
    assert len(h) == int(df["score"].notna().sum())
    assert [x["d"] for x in h] == sorted(x["d"] for x in h)
    assert set(h[0]) == {"d", "s", "l"} and isinstance(h[0]["l"], int)
    json.dumps(h, allow_nan=False)


def test_run_escribe_los_dos_json_con_fetchers_falsos(tmp_path):
    spy, vix, baa, rsp, sect = _datos()
    tablas = {"SPY": spy, "RSP": rsp, "^VIX": vix, **{s: sect[s] for s in SECTORES}}

    def fy(simbolo):
        return pd.DataFrame({"adj_close": tablas[simbolo]})

    def ff(serie):
        assert serie == "BAA10Y"
        return pd.DataFrame({"value": baa})

    out = tmp_path / "emergency"
    p = daily.run(out, fy, ff)
    assert json.loads((out / "latest.json").read_text())["data_through"] == p["data_through"]
    assert isinstance(json.loads((out / "history.json").read_text()), list)
    # determinista
    antes = (out / "latest.json").read_text()
    daily.run(out, fy, ff)
    assert (out / "latest.json").read_text() == antes

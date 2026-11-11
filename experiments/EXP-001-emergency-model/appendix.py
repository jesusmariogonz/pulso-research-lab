"""Apéndice EXPLORATORIO de EXP-001 (post-hoc: NO está en el pre-registro).

Re-ejecuta el mismo pipeline de `prl.emergency.exp001` sobre los datos congelados y calcula
diagnósticos adicionales para el reporte técnico: rendimientos por año, drawdowns, estadística
de exposición, sensibilidad de las 162 variantes, bootstraps pareados adicionales, prueba placebo
por desplazamiento circular, componentes del Deflated Sharpe, diagnóstico de dimensiones y curvas.

    python experiments/EXP-001-emergency-model/appendix.py <inputs_dir> <out_dir>

Determinista (semillas fijas). Verifica primero que reproduce EXACTAMENTE las métricas
publicadas en results.json; si no coincide, aborta (no publica nada inconsistente).
Toda cifra de este archivo la produce código; ningún modelo de lenguaje interviene.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from prl.emergency import exp001
from prl.emergency.backtest import metrics, run_backtest
from prl.emergency.evaluation import block_bootstrap_ci, deflated_sharpe_ratio, walk_forward_select
from prl.emergency.features import (breadth_stress, composite_score, correlation_stress, credit_stress,
                                    drawdown_velocity_stress, trend_stress, vol_stress)
from prl.emergency.grid import build_grid, destination_weights, dimension_weights
from prl.emergency.inputs import build_cash_index, common_start, sma200_exposure
from prl.emergency.state_machine import assign_levels, exposure_for_level

SEED = 0
N_BOOT = 2000
N_PLACEBO = 1000
FIRST_TEST_YEAR = 2004
RESULTS = Path(__file__).parent / "results_published.json"


def _f(x):
    x = float(x)
    return x if math.isfinite(x) else None


def construir(inputs: Path):
    ps, fs = exp001._price_series, exp001._fred_series
    spy, vix, rsp, tlt, bil = (ps(inputs, n) for n in ["SPY", "VIX", "RSP", "TLT", "BIL"])
    baa, dtb3 = fs(inputs, "BAA10Y"), fs(inputs, "DTB3")
    idx = spy.index
    sect = pd.DataFrame({n: ps(inputs, n).reindex(idx) for n in exp001.SECTORS}, index=idx)
    dims = pd.DataFrame(index=idx)
    dims["trend"] = trend_stress(spy)
    dims["vol"] = vol_stress(vix.reindex(idx))
    dims["credit"] = credit_stress(baa.reindex(idx).ffill())
    dims["breadth"] = breadth_stress(rsp.reindex(idx), spy)
    dims["drawdown_velocity"] = drawdown_velocity_stress(spy)
    dims["correlation"] = correlation_stress(sect / sect.shift(1) - 1.0)
    cash = build_cash_index(dtb3, bil).reindex(idx).ffill()
    tl = tlt.reindex(idx)
    allp = pd.DataFrame({"SPY": spy, "TLT": tl, "CASH": cash}, index=idx)
    prices = allp.loc[allp.index >= common_start({"SPY": spy, "TLT": tl, "CASH": cash})].copy()
    var = {}
    for v in build_grid():
        sc = composite_score(dims, dimension_weights(v["weights"]))
        lv = assign_levels(sc, float(v["theta"]), int(v["k"]), int(v["m"]))
        ex = lv.map(exposure_for_level)
        bt = run_backtest(prices, ex, "SPY", destination_weights(v["destination"]), 0.001)
        var[v["variant_id"]] = dict(v=v, ret=bt["ret"], level=lv, expo_decided=ex, applied=bt["exposure_applied"], cost=bt["cost"])
    return dict(spy=spy, dims=dims, prices=prices, var=var)


def _underwater(ret):
    eq = (1 + ret).cumprod()
    return eq, eq / eq.cummax() - 1.0


def drawdown_table(ret, top=5):
    eq, uw = _underwater(ret)
    out, i, n = [], 0, len(eq)
    idxs = eq.index
    peak_val = eq.iloc[0]
    peak_i = 0
    in_dd = False
    for i in range(n):
        v = eq.iloc[i]
        if v >= peak_val:
            if in_dd:
                seg = uw.iloc[peak_i:i]
                t = int(seg.values.argmin()) + peak_i
                out.append(dict(peak=str(idxs[peak_i].date()), trough=str(idxs[t].date()), recovery=str(idxs[i].date()),
                                depth=_f(uw.iloc[t]), days_to_trough=(idxs[t] - idxs[peak_i]).days,
                                days_to_recover=(idxs[i] - idxs[peak_i]).days))
                in_dd = False
            peak_val, peak_i = v, i
        else:
            in_dd = True
    if in_dd:
        seg = uw.iloc[peak_i:]
        t = int(seg.values.argmin()) + peak_i
        out.append(dict(peak=str(idxs[peak_i].date()), trough=str(idxs[t].date()), recovery=None,
                        depth=_f(uw.iloc[t]), days_to_trough=(idxs[t] - idxs[peak_i]).days, days_to_recover=None))
    return sorted(out, key=lambda d: d["depth"])[:top]


def annual(rets):
    out = []
    for y in sorted(set(rets["model"].index.year)):
        row = {"year": int(y)}
        for k, r in rets.items():
            seg = r[r.index.year == y]
            row[k] = _f((1 + seg).prod() - 1)
        row["n_days"] = int((rets["model"].index.year == y).sum())
        out.append(row)
    return out


def exposure_stats(applied, cost):
    a = applied.to_numpy()
    ch = int((np.abs(np.diff(a)) > 1e-12).sum())
    yrs = (applied.index[-1] - applied.index[0]).days / 365.25
    vals, cnt = np.unique(np.round(a, 4), return_counts=True)
    return dict(mean_exposure=_f(a.mean()), share_fully_invested=_f((a >= 1 - 1e-12).mean()),
                share_zero_equity=_f((a <= 1e-12).mean()), n_exposure_changes=ch,
                changes_per_year=_f(ch / yrs), total_cost_drag=_f(cost.sum()),
                cost_drag_per_year=_f(cost.sum() / yrs),
                days_by_exposure={str(v): int(c) for v, c in zip(vals, cnt)})


def sensibilidad(var, oos_idx, bh_m, sma_m):
    rows = []
    for vid, d in var.items():
        m = metrics(d["ret"].reindex(oos_idx))
        rows.append(dict(id=vid, **d["v"], cagr=m["cagr"], maxdd=m["max_drawdown"], calmar=m["calmar"], sharpe=m["sharpe"]))
    df = pd.DataFrame(rows)

    def agg(g):
        return dict(n=int(len(g)), calmar_median=_f(g.calmar.median()), calmar_q25=_f(g.calmar.quantile(.25)),
                    calmar_q75=_f(g.calmar.quantile(.75)), calmar_min=_f(g.calmar.min()), calmar_max=_f(g.calmar.max()),
                    maxdd_median=_f(g.maxdd.median()), cagr_median=_f(g.cagr.median()),
                    share_maxdd_better_than_bh=_f((g.maxdd.abs() < abs(bh_m["max_drawdown"])).mean()),
                    share_calmar_above_sma200=_f((g.calmar > sma_m["calmar"]).mean()),
                    share_calmar_above_bh=_f((g.calmar > bh_m["calmar"]).mean()))
    out = {"all": agg(df)}
    for col in ["destination", "theta", "k", "m", "weights"]:
        out[col] = {str(k): agg(g) for k, g in df.groupby(col)}
    best, worst = df.loc[df.calmar.idxmax()], df.loc[df.calmar.idxmin()]
    out["best_variant"] = dict(id=best["id"], calmar=_f(best.calmar), maxdd=_f(best.maxdd), cagr=_f(best.cagr))
    out["worst_variant"] = dict(id=worst["id"], calmar=_f(worst.calmar), maxdd=_f(worst.maxdd), cagr=_f(worst.cagr))
    return out


def bootstraps(model, bh, sma):
    def cagr_d(a, b): return metrics(a)["cagr"] - metrics(b)["cagr"]
    def dd_d(a, b): return metrics(a)["max_drawdown"] - metrics(b)["max_drawdown"]
    def sh_d(a, b): return metrics(a)["sharpe"] - metrics(b)["sharpe"]
    def ca_d(a, b): return metrics(a)["calmar"] - metrics(b)["calmar"]
    spec = [("cagr_model_minus_buyhold", model, bh, cagr_d), ("maxdd_model_minus_buyhold", model, bh, dd_d),
            ("sharpe_model_minus_buyhold", model, bh, sh_d), ("calmar_model_minus_buyhold", model, bh, ca_d),
            ("sharpe_model_minus_sma200", model, sma, sh_d), ("cagr_model_minus_sma200", model, sma, cagr_d),
            ("maxdd_model_minus_sma200", model, sma, dd_d)]
    out = {}
    for name, a, b, fn in spec:
        lo, hi = block_bootstrap_ci(a, b, fn, block=20, n_boot=N_BOOT, seed=SEED)
        out[name] = dict(point=_f(fn(a, b)), ci_lo=_f(lo), ci_hi=_f(hi), n_boot=N_BOOT, block=20)
    return out


def placebo(data, vid, oos_idx):
    d = data["var"][vid]
    prices, ex = data["prices"], d["expo_decided"]
    dest = destination_weights(d["v"]["destination"])
    obs = metrics(d["ret"].reindex(oos_idx))
    rng = np.random.default_rng(SEED)
    n = len(ex)
    cal, dds = [], []
    vals = ex.to_numpy()
    for _ in range(N_PLACEBO):
        s = int(rng.integers(252, n - 252))
        bt = run_backtest(prices, pd.Series(np.roll(vals, s), index=ex.index), "SPY", dest, 0.001)
        m = metrics(bt["ret"].reindex(oos_idx))
        cal.append(m["calmar"]); dds.append(m["max_drawdown"])
    cal, dds = np.array(cal), np.array(dds)
    q = lambda a: {k: _f(np.percentile(a, p)) for k, p in [("p05", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95)]}
    return dict(variant=vid, n_placebo=N_PLACEBO, method="desplazamiento circular de la serie de exposición decidida (conserva ocupación de niveles y persistencia; rompe la alineación con el mercado)",
                observed_calmar=_f(obs["calmar"]), observed_maxdd=_f(obs["max_drawdown"]), observed_cagr=_f(obs["cagr"]),
                placebo_calmar=q(cal), placebo_maxdd=q(dds),
                p_value_calmar=_f((1 + (cal >= obs["calmar"]).sum()) / (1 + N_PLACEBO)),
                p_value_maxdd=_f((1 + (np.abs(dds) <= abs(obs["max_drawdown"])).sum()) / (1 + N_PLACEBO)))


def dsr_components(r, n_trials=162):
    n = len(r); sr = float(r.mean() / r.std(ddof=1)); g3 = float(r.skew()); g4 = float(r.kurt() + 3.0)
    sr_std = math.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (n - 1))
    from scipy.stats import norm
    gam = 0.5772156649015329
    sr0 = sr_std * ((1 - gam) * norm.ppf(1 - 1 / n_trials) + gam * norm.ppf(1 - 1 / (n_trials * math.e)))
    return dict(n=n, sr_daily=_f(sr), sr_annualized=_f(sr * math.sqrt(252)), skew=_f(g3), kurtosis=_f(g4),
                sr_std=_f(sr_std), sr0=_f(sr0), sr0_annualized=_f(sr0 * math.sqrt(252)), n_trials=n_trials,
                dsr=_f(deflated_sharpe_ratio(r, n_trials)), psr_vs_zero=_f(deflated_sharpe_ratio(r, 1)))


def dims_diag(dims, oos_idx, episodes, spy):
    d = dims.reindex(oos_idx)
    d = d.assign(score=composite_score(dims, dimension_weights("equal")).reindex(oos_idx))
    corr = d.dropna().corr()
    out = dict(n_rows=int(d.dropna().shape[0]), correlation={a: {b: _f(corr.loc[a, b]) for b in corr.columns} for a in corr.index},
               mean=d.mean().map(_f).to_dict(), std=d.std().map(_f).to_dict(),
               share_above_1=d.apply(lambda s: _f((s.dropna() > 1).mean())).to_dict(), pre_crisis=[])
    for e in episodes:
        pk = pd.Timestamp(e["peak"]); close = spy.reindex(oos_idx)
        if pk not in close.index:  # episodio anterior a la muestra fuera de muestra (dot-com)
            continue
        after = close[close.index > pk]; hit = after[after / close.loc[pk] - 1 <= -0.20]
        if hit.empty: continue
        cx = hit.index[0]; w = d[(d.index >= pk - pd.Timedelta(days=90)) & (d.index <= cx)]
        out["pre_crisis"].append(dict(name=e["name"], window=[str(w.index[0].date()), str(cx.date())], n_days=int(len(w)),
                                      mean_in_window=w.mean().map(_f).to_dict()))
    return out


def curves(rets):
    out = {}
    for k, r in rets.items():
        eq, uw = _underwater(r)
        wk = eq.resample("W-FRI").last().dropna(); uwk = uw.resample("W-FRI").min().dropna()
        out[k] = dict(dates=[str(x.date()) for x in wk.index], equity=[round(float(x), 4) for x in wk.values],
                      underwater=[round(float(x), 4) for x in uwk.values])
    return out


def main(inputs_dir, out_dir):
    inputs, out_dir = Path(inputs_dir), Path(out_dir)
    pub = json.loads(RESULTS.read_text())
    data = construir(inputs)
    var, prices = data["var"], data["prices"]
    oos, chosen = walk_forward_select({k: v["ret"] for k, v in var.items()}, FIRST_TEST_YEAR, "calmar")
    mm = metrics(oos)
    for k in ["cagr", "max_drawdown", "calmar", "sharpe", "sortino"]:
        assert abs(mm[k] - pub["metrics"]["model"][k]) < 1e-12, f"no reproduce {k}: {mm[k]} vs {pub['metrics']['model'][k]}"
    assert {str(k): v for k, v in chosen.items()} == pub["chosen_by_year"], "chosen_by_year no coincide"
    oi = oos.index
    bh = run_backtest(prices, pd.Series(1.0, index=prices.index), "SPY", {"CASH": 1.0}, 0.001)["ret"].reindex(oi)
    sm = run_backtest(prices, sma200_exposure(prices["SPY"]), "SPY", {"CASH": 1.0}, 0.001)["ret"].reindex(oi)
    sf = run_backtest(prices, pd.Series(0.6, index=prices.index), "SPY", {"TLT": 1.0}, 0.001)["ret"].reindex(oi)
    for k, r in [("buy_hold", bh), ("sma200", sm), ("sixty_forty", sf)]:
        assert abs(metrics(r)["calmar"] - pub["metrics"][k]["calmar"]) < 1e-12, f"no reproduce {k}"
    rets = {"model": oos, "buy_hold": bh, "sma200": sm, "sixty_forty": sf}

    # exposición/costos del modelo OOS (unión de la variante elegida cada año)
    ap, co = [], []
    for y, vid in sorted(chosen.items()):
        m = oi.year == y
        ap.append(var[vid]["applied"].reindex(oi[m])); co.append(var[vid]["cost"].reindex(oi[m]))
    applied, cost = pd.concat(ap).sort_index(), pd.concat(co).sort_index()

    freq = pd.Series(list(chosen.values())).value_counts()
    top_vid = freq.index[0]
    ep = exp001.DEFAULT_EPISODES
    res = dict(
        meta=dict(note="Apéndice EXPLORATORIO: análisis post-hoc, no pre-registrado. Reproduce exactamente results.json antes de calcular.",
                  seed=SEED, n_boot=N_BOOT, n_placebo=N_PLACEBO, first_test_year=FIRST_TEST_YEAR,
                  oos_start=str(oi[0].date()), oos_end=str(oi[-1].date()), n_oos_days=int(len(oi)),
                  training_days_before_first_test_year=int((var[next(iter(var))]["ret"].index < pd.Timestamp(f"{FIRST_TEST_YEAR}-01-01")).sum()),
                  sample_start=str(prices.index[0].date())),
        annual=annual(rets),
        drawdowns={k: drawdown_table(r) for k, r in rets.items() if k != "sixty_forty"},
        exposure=exposure_stats(applied, cost),
        chosen_frequency={k: int(v) for k, v in freq.items()},
        sensitivity=sensibilidad(var, oi, metrics(bh), metrics(sm)),
        bootstrap=bootstraps(oos, bh, sm),
        placebo=placebo(data, top_vid, oi),
        dsr=dsr_components(oos),
        dims=dims_diag(data["dims"], oi, ep, data["spy"]),
        curves=curves(rets),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "appendix.json").write_text(json.dumps(res, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    print("OK: reproduce results.json; apéndice escrito en", out_dir / "appendix.json")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

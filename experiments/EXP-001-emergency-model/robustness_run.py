"""EXP-001 · pruebas de robustez EXPLORATORIAS (post-hoc; no cambian la etiqueta).
Usa prl.emergency.robustness (escrito por DeepSeek) sobre los datos congelados.
Uso: python robustness_run.py <raw_dir> <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import appendix as A  # noqa: E402
from prl.emergency.backtest import metrics, run_backtest  # noqa: E402
from prl.emergency.evaluation import walk_forward_select  # noqa: E402
from prl.emergency.grid import destination_weights  # noqa: E402
from prl.emergency.inputs import sma200_exposure  # noqa: E402
from prl.emergency.robustness import (cost_sensitivity, exclude_window, reality_check,  # noqa: E402
                                      required_sample_size, subperiod_metrics)

COSTS = [0, 5, 10, 25, 50]
WINDOWS = {"2004-2009": ("2004-01-01", "2009-12-31"), "2010-2019": ("2010-01-01", "2019-12-31"),
           "2020-2026": ("2020-01-01", "2026-12-31")}
CRISIS = ("2007-10-01", "2009-12-31")


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    return o


def main(raw, out):
    data = A.construir(Path(raw))
    var, prices = data["var"], data["prices"]
    oos, chosen = walk_forward_select({k: v["ret"] for k, v in var.items()}, A.FIRST_TEST_YEAR, "calmar")
    oi = oos.index
    bh = run_backtest(prices, pd.Series(1.0, index=prices.index), "SPY", {"CASH": 1.0}, 0.001)["ret"].reindex(oi)
    sm = run_backtest(prices, sma200_exposure(prices["SPY"]), "SPY", {"CASH": 1.0}, 0.001)["ret"].reindex(oi)

    # 1) costos: se mantiene la variante elegida por año (seleccionada con costo 10 pb)
    cs = {}
    for c in COSTS:
        parts = []
        for y, vid in sorted(chosen.items()):
            v = var[vid]["v"]
            bt = run_backtest(prices, var[vid]["expo_decided"], "SPY", destination_weights(v["destination"]), c / 10000)
            parts.append(bt["ret"].reindex(oi[oi.year == y]))
        m = metrics(pd.concat(parts).sort_index())
        cs[c] = {k: m[k] for k in ["cagr", "max_drawdown", "calmar", "sharpe"]}
    smc = cost_sensitivity(prices, sma200_exposure(prices["SPY"]), "SPY", {"CASH": 1.0}, COSTS)
    # verificación cruzada con el módulo de DeepSeek (mismo cálculo, estrategia SMA200)
    assert abs(smc.loc[10, "cagr"] - metrics(run_backtest(prices, sma200_exposure(prices["SPY"]), "SPY", {"CASH": 1.0}, 0.001)["ret"])["cagr"]) < 1e-12

    # 2) subperíodos y exclusión de la crisis 2007-09
    sub = {n: subperiod_metrics(r, WINDOWS).to_dict("index") for n, r in [("model", oos), ("buy_hold", bh), ("sma200", sm)]}
    exc = {n: {k: metrics(exclude_window(r, *CRISIS))[k] for k in ["cagr", "max_drawdown", "calmar", "sharpe"]}
           for n, r in [("model", oos), ("buy_hold", bh), ("sma200", sm)]}

    # 3) Reality Check sobre las 162 variantes (retornos OOS de cada una, sin selección walk-forward)
    R = pd.DataFrame({k: v["ret"].reindex(oi) for k, v in var.items()})
    rc = {"vs_buy_hold": reality_check(R, bh, n_boot=2000, block=20, seed=0),
          "vs_sma200": reality_check(R, sm, n_boot=2000, block=20, seed=0)}

    # 4) potencia: exceso anual del modelo (walk-forward) sobre SMA200 y buy&hold
    def anual(r): return (1 + r).groupby(r.index.year).prod() - 1
    pw = {}
    for n, b in [("sma200", sm), ("buy_hold", bh)]:
        d = (anual(oos) - anual(b)).dropna()
        eff, sd = float(d.mean()), float(d.std(ddof=1))
        pw[n] = dict(n_years=int(len(d)), mean_excess_annual=eff, sd_excess_annual=sd,
                     t_stat=eff / (sd / np.sqrt(len(d))),
                     years_needed_80pct_power=(required_sample_size(eff, sd) if eff > 0 else None))
    res = clean(dict(meta=dict(note="EXPLORATORIO post-hoc; no cambia la etiqueta. Módulo robustness.py escrito por DeepSeek.",
                               costs_bps=COSTS, crisis_excluded=CRISIS),
                     cost_sensitivity=dict(model=cs, sma200=smc.to_dict("index")),
                     subperiods=sub, excluding_crisis=exc, reality_check=rc, power=pw))
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "robustness.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, allow_nan=False))
    print(json.dumps(res, indent=1)[:3500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

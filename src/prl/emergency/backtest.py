from __future__ import annotations

import math
from typing import Mapping

import numpy as np
import pandas as pd


def run_backtest(
    prices: pd.DataFrame,
    exposure: pd.Series,
    risk_asset: str,
    safe_weights: Mapping[str, float],
    cost_per_side: float = 0.001,
) -> pd.DataFrame:
    """Ejecuta la política de exposición con costos de rebalanceo.

    La exposición decidida al cierre de ``t`` se aplica en ``t+1``. El retorno
    de la primera fila es cero y no genera coste.
    """
    idx = prices.index

    if len(prices) == 0:
        return pd.DataFrame(
            index=idx,
            columns=["ret", "equity", "exposure_applied", "cost"],
            dtype=float,
        )

    exp = exposure.astype(float).reindex(idx)

    # Exposición aplicada en t: e_{t-1}. En la primera fila se usa e_0.
    applied = exp.shift(1)
    applied.iloc[0] = exp.iloc[0]

    # Coste en t: 2 * cost_per_side * |e_{t-1} - e_{t-2}|.
    cost = 2.0 * cost_per_side * applied.diff().abs().fillna(0.0)

    risk_ret = prices[risk_asset].pct_change()

    safe_ret = pd.Series(0.0, index=idx, dtype=float)
    for asset, weight in safe_weights.items():
        safe_ret = safe_ret + float(weight) * prices[asset].pct_change()

    ret = pd.Series(0.0, index=idx, dtype=float)
    if len(idx) > 1:
        ret.iloc[1:] = (
            applied.iloc[1:] * risk_ret.iloc[1:]
            + (1.0 - applied.iloc[1:]) * safe_ret.iloc[1:]
            - cost.iloc[1:]
        )

    equity = (1.0 + ret).cumprod()

    return pd.DataFrame(
        {
            "ret": ret,
            "equity": equity,
            "exposure_applied": applied,
            "cost": cost,
        },
        index=idx,
    )


def metrics(returns: pd.Series) -> dict[str, float]:
    """Calcula métricas básicas de una serie de retornos diarios."""
    r = pd.Series(returns, dtype=float)
    n_days = int(len(r))

    if n_days == 0:
        return {
            "cagr": np.nan,
            "max_drawdown": np.nan,
            "calmar": np.nan,
            "sharpe": np.nan,
            "sortino": np.nan,
            "n_days": 0,
        }

    equity = (1.0 + r).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())

    if isinstance(r.index, pd.DatetimeIndex) and n_days > 1:
        years = (r.index[-1] - r.index[0]).days / 365.25
    else:
        years = (n_days - 1) / 252.0

    final_equity = float(equity.iloc[-1])
    if years > 0.0 and final_equity > 0.0:
        cagr = final_equity ** (1.0 / years) - 1.0
    else:
        cagr = np.nan

    if max_drawdown != 0.0 and not math.isnan(cagr):
        calmar = cagr / abs(max_drawdown)
    else:
        calmar = np.nan

    mean_ret = float(r.mean())
    std_ret = float(r.std(ddof=1))
    if n_days > 1 and std_ret > 0.0:
        sharpe = mean_ret / std_ret * math.sqrt(252.0)
    else:
        sharpe = np.nan

    downside = np.minimum(r.to_numpy(dtype=float), 0.0)
    downside_dev = float(np.sqrt(np.mean(np.square(downside))))
    if downside_dev > 0.0:
        sortino = mean_ret / downside_dev * math.sqrt(252.0)
    elif mean_ret > 0.0:
        sortino = np.inf
    else:
        sortino = np.nan

    return {
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "sharpe": sharpe,
        "sortino": sortino,
        "n_days": n_days,
    }

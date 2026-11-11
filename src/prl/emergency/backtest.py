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
    """Run a long/refuge backtest with daily rebalancing and exposure costs."""
    if not isinstance(prices, pd.DataFrame):
        raise ValueError("prices must be a pandas DataFrame")
    if not isinstance(exposure, pd.Series):
        raise ValueError("exposure must be a pandas Series")
    if not hasattr(safe_weights, "items"):
        raise ValueError("safe_weights must be a mapping")

    safe_items = list(safe_weights.items())
    total_safe_weight = sum(float(weight) for _, weight in safe_items)
    if not math.isclose(total_safe_weight, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("safe_weights must sum to 1 within 1e-9")

    used_assets = {risk_asset} | {asset for asset, _ in safe_items}
    missing = [asset for asset in used_assets if asset not in prices.columns]
    if missing:
        raise ValueError(f"missing price columns: {missing}")

    for asset in used_assets:
        if prices[asset].isna().any():
            raise ValueError(f"price column {asset!r} contains NaN")

    aligned_exposure = exposure.reindex(prices.index)
    if aligned_exposure.isna().any():
        raise ValueError("exposure contains NaN after alignment to prices index")

    exp_values = aligned_exposure.to_numpy(dtype=float)
    if np.any(exp_values < 0.0) or np.any(exp_values > 1.0):
        raise ValueError("exposure must be within [0, 1]")

    aligned_exposure = aligned_exposure.astype(float)

    n = len(prices.index)
    if n == 0:
        return pd.DataFrame(
            columns=["ret", "equity", "exposure_applied", "cost"],
            index=prices.index,
            dtype=float,
        )

    risk_ret = prices[risk_asset].pct_change()

    safe_ret = pd.Series(0.0, index=prices.index, dtype=float)
    for asset, weight in safe_items:
        safe_ret = safe_ret + float(weight) * prices[asset].pct_change()

    # Exposure applied on row t is the exposure decided at the close of t-1.
    applied = aligned_exposure.shift(1)
    applied.iloc[0] = aligned_exposure.iloc[0]

    cost = 2.0 * float(cost_per_side) * applied.diff().abs().fillna(0.0)

    ret = applied * risk_ret + (1.0 - applied) * safe_ret - cost
    ret.iloc[0] = 0.0

    equity = (1.0 + ret).cumprod()

    return pd.DataFrame(
        {
            "ret": ret,
            "equity": equity,
            "exposure_applied": applied,
            "cost": cost,
        },
        index=prices.index,
    )


def metrics(returns: pd.Series) -> dict[str, float | int]:
    """Compute standard performance metrics from a daily return series."""
    r = returns.astype(float)
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

    values = r.to_numpy(dtype=float)
    wealth = np.concatenate(([1.0], np.cumprod(1.0 + values)))
    final_wealth = float(wealth[-1])

    if isinstance(r.index, pd.DatetimeIndex) and n_days >= 2:
        years = (r.index[-1] - r.index[0]).days / 365.25
    else:
        years = n_days / 252.0

    if years > 0.0 and final_wealth > 0.0:
        cagr = final_wealth ** (1.0 / years) - 1.0
    elif years > 0.0 and final_wealth == 0.0:
        cagr = -1.0
    else:
        cagr = np.nan

    running_max = np.maximum.accumulate(wealth)
    drawdowns = wealth / running_max - 1.0
    max_drawdown = float(np.min(drawdowns))

    mean_ret = float(np.mean(values))

    if n_days >= 2:
        std_ret = float(np.std(values, ddof=1))
        sharpe = mean_ret / std_ret * math.sqrt(252.0) if std_ret > 0.0 else np.nan
    else:
        sharpe = np.nan

    downside = np.minimum(values, 0.0)
    downside_dev = float(np.sqrt(np.mean(downside**2)))
    if downside_dev > 0.0:
        sortino = mean_ret / downside_dev * math.sqrt(252.0)
    else:
        sortino = np.inf if mean_ret > 0.0 else 0.0

    calmar = cagr / abs(max_drawdown) if max_drawdown < 0.0 else np.nan

    return {
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "sharpe": sharpe,
        "sortino": sortino,
        "n_days": n_days,
    }

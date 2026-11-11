from __future__ import annotations

from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm

from prl.emergency.backtest import metrics, run_backtest


_METRIC_COLS = ["cagr", "max_drawdown", "calmar", "sharpe"]


def cost_sensitivity(
    prices: pd.DataFrame,
    exposure: pd.Series,
    risk_asset: str,
    safe_weights: Mapping[str, float],
    costs_bps: Sequence[float],
) -> pd.DataFrame:
    """Run the backtest for several per-side cost levels in basis points."""
    rows: list[dict[str, float]] = []
    for bps in costs_bps:
        result = run_backtest(
            prices,
            exposure,
            risk_asset,
            dict(safe_weights),
            cost_per_side=float(bps) / 10000.0,
        )
        m = metrics(result["ret"])
        rows.append({col: float(m[col]) for col in _METRIC_COLS})

    index = pd.Index(list(costs_bps), name="cost_bps")
    return pd.DataFrame(rows, index=index, columns=_METRIC_COLS)


def subperiod_metrics(
    ret: pd.Series,
    windows: Mapping[str, tuple[str, str]],
) -> pd.DataFrame:
    """Compute summary metrics for each inclusive date window."""
    rows: list[dict[str, float | int]] = []
    names: list[str] = []

    for name, (start, end) in windows.items():
        names.append(name)
        piece = ret.loc[start:end]
        if piece.empty:
            rows.append(
                {
                    "cagr": np.nan,
                    "max_drawdown": np.nan,
                    "calmar": np.nan,
                    "sharpe": np.nan,
                    "n_days": 0,
                }
            )
        else:
            m = metrics(piece)
            rows.append(
                {
                    "cagr": float(m["cagr"]),
                    "max_drawdown": float(m["max_drawdown"]),
                    "calmar": float(m["calmar"]),
                    "sharpe": float(m["sharpe"]),
                    "n_days": int(m["n_days"]),
                }
            )

    return pd.DataFrame(
        rows,
        index=pd.Index(names),
        columns=["cagr", "max_drawdown", "calmar", "sharpe", "n_days"],
    )


def exclude_window(ret: pd.Series, inicio: str, fin: str) -> pd.Series:
    """Return the series excluding dates in the inclusive [inicio, fin] window."""
    start = pd.Timestamp(inicio)
    end = pd.Timestamp(fin)
    mask = (ret.index >= start) & (ret.index <= end)
    return ret.loc[~mask].copy()


def reality_check(
    returns: pd.DataFrame,
    benchmark: pd.Series,
    n_boot: int = 1000,
    block: int = 20,
    seed: int = 0,
) -> dict:
    """White's reality-check test using a moving-block bootstrap."""
    if not returns.index.equals(benchmark.index):
        raise ValueError("returns and benchmark must have identical indices")
    if returns.isna().any().any() or benchmark.isna().any():
        raise ValueError("returns and benchmark must not contain NaN values")
    if block <= 0:
        raise ValueError("block must be positive")
    if n_boot <= 0:
        raise ValueError("n_boot must be positive")

    n = len(returns)
    if n == 0:
        raise ValueError("returns must not be empty")
    if n < block:
        raise ValueError("block cannot exceed the number of observations")

    d = returns.sub(benchmark, axis=0)
    d_values = d.to_numpy(dtype=float)
    means = d_values.mean(axis=0)
    sqrt_n = np.sqrt(float(n))
    statistic = float(np.max(sqrt_n * means))

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    max_start = n - block
    boot_stats = np.empty(int(n_boot), dtype=float)

    for b in range(int(n_boot)):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = np.concatenate(
            [np.arange(start, start + block, dtype=int) for start in starts]
        )[:n]
        sample = d_values[idx, :]
        sample_means = sample.mean(axis=0)
        boot_stats[b] = np.max(sqrt_n * (sample_means - means))

    p_value = float(np.mean(boot_stats >= statistic))
    best_variant = str(d.mean(axis=0).idxmax())

    return {
        "statistic": statistic,
        "p_value": p_value,
        "best_variant": best_variant,
        "n_boot": int(n_boot),
    }


def required_sample_size(
    effect: float,
    sd: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """Minimum sample size for a one-sided z-test of a mean effect."""
    if effect <= 0:
        raise ValueError("effect must be positive")
    if sd <= 0:
        raise ValueError("sd must be positive")

    z_alpha = float(norm.ppf(1.0 - alpha))
    z_power = float(norm.ppf(power))
    return float(((z_alpha + z_power) * sd / effect) ** 2)

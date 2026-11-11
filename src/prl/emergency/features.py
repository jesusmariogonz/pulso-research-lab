from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def expanding_zscore(s: pd.Series, min_periods: int = 252) -> pd.Series:
    """Z-score expansivo usando solo observaciones hasta t inclusive."""
    mean = s.expanding(min_periods=min_periods).mean()
    std = s.expanding(min_periods=min_periods).std(ddof=1)
    return (s - mean) / std


def trend_stress(close: pd.Series) -> pd.Series:
    """Estrés de tendencia: caída del precio respecto a su SMA200."""
    sma200 = close.rolling(window=200, min_periods=200).mean()
    raw = -(close / sma200 - 1.0)
    return expanding_zscore(raw)


def vol_stress(vix: pd.Series) -> pd.Series:
    """Estrés de volatilidad: nivel y cambio a 5 días del VIX."""
    log_vix = np.log(vix)
    level = expanding_zscore(log_vix)
    change = expanding_zscore(np.log(vix / vix.shift(5)))
    return pd.concat([level, change], axis=1).mean(axis=1)


def credit_stress(spread: pd.Series) -> pd.Series:
    """Estrés de crédito: z-score expansivo del spread."""
    return expanding_zscore(spread)


def drawdown_velocity_stress(close: pd.Series) -> pd.Series:
    """Estrés por velocidad de caída a 10 días."""
    raw = -(close / close.shift(10) - 1.0)
    return expanding_zscore(raw)


def breadth_stress(rsp: pd.Series, spy: pd.Series) -> pd.Series:
    """Estrés de amplitud: deterioro relativo de RSP frente a SPY."""
    log_ratio = np.log(rsp / spy)
    raw = -(log_ratio - log_ratio.shift(60))
    return expanding_zscore(raw)


def correlation_stress(returns: pd.DataFrame, window: int = 60) -> pd.Series:
    """Estrés de correlación: correlación media por pares en ventana móvil."""
    raw = pd.Series(np.nan, index=returns.index, dtype=float)

    n_cols = returns.shape[1]
    if window < 2 or n_cols < 2:
        return expanding_zscore(raw)

    mask = np.triu(np.ones((n_cols, n_cols), dtype=bool), k=1)

    for t in range(window - 1, len(returns)):
        win = returns.iloc[t - window + 1 : t + 1]
        corr = win.corr().to_numpy()
        pair_values = corr[mask]
        valid = pair_values[np.isfinite(pair_values)]
        if valid.size > 0:
            raw.iloc[t] = float(valid.mean())

    return expanding_zscore(raw)


def composite_score(dims: pd.DataFrame, weights: Mapping[str, float]) -> pd.Series:
    """Promedio ponderado por fila de las dimensiones disponibles."""
    cols = [c for c in weights if c in dims.columns]
    if not cols:
        return pd.Series(np.nan, index=dims.index, dtype=float)

    w = pd.Series({c: float(weights[c]) for c in cols}, dtype=float)
    sub = dims[cols].astype(float)

    numerator = sub.mul(w, axis=1).sum(axis=1, skipna=True)
    denominator = sub.notna().mul(w, axis=1).sum(axis=1)

    return numerator / denominator

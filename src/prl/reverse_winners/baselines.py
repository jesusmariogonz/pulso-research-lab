from __future__ import annotations

import pandas as pd


def baseline_momentum_simple(
    features_percentil: pd.DataFrame, pct: float = 0.20
) -> pd.Series:
    """Selecciona el top ``pct`` por percentil de ``mom_20d``."""
    condicion = features_percentil["mom_20d"] >= (1.0 - pct)
    return condicion.fillna(False).astype(bool)


def baseline_buy_hold(simbolos_elegibles: list[str]) -> pd.Series:
    """Selecciona todos los símbolos elegibles (buy & hold)."""
    return pd.Series(True, index=simbolos_elegibles, dtype=bool)


def baseline_rsi_simple(
    features_percentil: pd.DataFrame, pct: float = 0.10
) -> pd.Series:
    """Selecciona el bottom ``pct`` por percentil de ``rsi14``."""
    condicion = features_percentil["rsi14"] <= pct
    return condicion.fillna(False).astype(bool)


def baseline_combo_ingenuo(features_crudas: pd.DataFrame) -> pd.Series:
    """Combina umbrales fijos sobre valores crudos de tres features."""
    condicion = (
        (features_crudas["mom_20d"] > 0)
        & (features_crudas["dist_sma50"] > 0)
        & (features_crudas["vol_relativo_20d"] > 1.2)
    )
    return condicion.fillna(False).astype(bool)

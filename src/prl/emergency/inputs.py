from __future__ import annotations

import pandas as pd


def build_cash_index(dtb3: pd.Series, bil: pd.Series) -> pd.Series:
    """Construye un índice de efectivo sintético y lo empalma con BIL desde su primera fecha."""
    dtb3 = pd.Series(dtb3, dtype="float64").copy()
    bil = pd.Series(bil, dtype="float64").copy()

    all_idx = dtb3.index.union(bil.index).sort_values()
    if len(all_idx) == 0:
        return pd.Series(dtype="float64")

    # La tasa DTB3 se propaga hacia adelante sobre la unión de fechas.
    dtb3_ff = dtb3.reindex(all_idx).ffill()

    # Índice sintético: empieza en 1.0 y usa la tasa del día anterior.
    values = [1.0]
    for i in range(1, len(all_idx)):
        prev_rate = dtb3_ff.iloc[i - 1]
        growth = 1.0 if pd.isna(prev_rate) else 1.0 + float(prev_rate) / 100.0 / 252.0
        values.append(values[-1] * growth)

    synthetic = pd.Series(values, index=all_idx, dtype="float64")

    # Si BIL tiene datos, empalmamos desde su primera fecha válida.
    bil_valid = bil.dropna()
    if bil_valid.empty:
        return synthetic

    t0 = bil_valid.index.min()
    if t0 not in synthetic.index:
        return synthetic

    bil_ff = bil.reindex(all_idx).ffill()
    base = synthetic.loc[t0]

    result = synthetic.copy()
    mask = all_idx >= t0
    result.loc[mask] = base * bil_ff.loc[mask] / bil_ff.loc[t0]
    return result


def sma200_exposure(close: pd.Series) -> pd.Series:
    """Exposición 1.0 si el precio está sobre su SMA200; 1.0 durante el calentamiento."""
    close = pd.Series(close, dtype="float64")
    sma = close.rolling(window=200, min_periods=200).mean()
    exposure = (close > sma).astype("float64")
    exposure = exposure.where(sma.notna(), 1.0)
    return exposure


def common_start(series: dict[str, pd.Series]) -> pd.Timestamp:
    """Devuelve la más tardía de las primeras fechas con dato válido de cada serie."""
    if not series:
        raise ValueError("series no puede estar vacío")

    starts: list[pd.Timestamp] = []
    for name, s in series.items():
        first = pd.Series(s).first_valid_index()
        if first is None:
            raise ValueError(f"La serie {name!r} no tiene valores válidos")
        starts.append(pd.Timestamp(first))

    return max(starts)

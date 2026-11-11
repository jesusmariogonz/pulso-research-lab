from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

LEVEL_NAMES = ["NORMAL", "VIGILANCIA", "DEFENSIVO", "EMERGENCIA", "CRISIS"]

_DIM_COLS = [
    "trend",
    "vol",
    "correlation",
    "credit",
    "breadth",
    "drawdown_velocity",
]

_SECTOR_COLS = ["XLK", "XLE", "XLF", "XLV", "XLP", "XLU", "XLY", "XLI", "XLB"]

_LEVEL_EXPOSURE: dict[int, float] = {
    0: 1.0,
    1: 0.75,
    2: 0.5,
    3: 0.25,
    4: 0.0,
}

_PARAMS = {"weights": "equal", "theta": 1.0, "k": 3, "m": 10}

_DISCLAIMER = (
    "Indicador informativo y EXPERIMENTAL. No es asesoría financiera ni una "
    "recomendación de inversión, y no representa la política validada del "
    "experimento EXP-001."
)


# ---------------------------------------------------------------------------
# Helpers: dimensiones de estrés (misma lógica que EXP-001)
# ---------------------------------------------------------------------------


def _expanding_zscore(s: pd.Series, min_periods: int = 252) -> pd.Series:
    """Z-score expansivo usando el historial disponible hasta cada fecha."""
    s = pd.Series(s, dtype="float64")
    mean = s.expanding(min_periods=min_periods).mean()
    std = s.expanding(min_periods=min_periods).std(ddof=1)
    return (s - mean) / std


def _trend_stress(close: pd.Series) -> pd.Series:
    sma200 = close.rolling(window=200, min_periods=200).mean()
    raw = -(close / sma200 - 1.0)
    return _expanding_zscore(raw)


def _vol_stress(vix: pd.Series) -> pd.Series:
    vix = pd.Series(vix, dtype="float64")
    level = np.log(vix.where(vix > 0))
    change = np.log((vix / vix.shift(5)).where(lambda x: x > 0))
    z_level = _expanding_zscore(level)
    z_change = _expanding_zscore(change)
    return pd.concat([z_level, z_change], axis=1).mean(axis=1, skipna=True)


def _credit_stress(spread: pd.Series) -> pd.Series:
    return _expanding_zscore(spread)


def _breadth_stress(rsp: pd.Series, spy: pd.Series) -> pd.Series:
    ratio = (rsp / spy).where(lambda x: x > 0)
    log_ratio = np.log(ratio)
    raw = -(log_ratio - log_ratio.shift(60))
    return _expanding_zscore(raw)


def _drawdown_velocity_stress(close: pd.Series) -> pd.Series:
    raw = -(close / close.shift(10) - 1.0)
    return _expanding_zscore(raw)


def _correlation_stress(returns: pd.DataFrame, window: int = 60) -> pd.Series:
    returns = returns.astype("float64")
    cols = list(returns.columns)
    if len(cols) < 2:
        return pd.Series(np.nan, index=returns.index, dtype="float64")

    pair_corrs: list[pd.Series] = []
    for i, col_i in enumerate(cols):
        for col_j in cols[i + 1 :]:
            pair_corrs.append(
                returns[col_i].rolling(window=window, min_periods=window).corr(
                    returns[col_j]
                )
            )

    raw = pd.concat(pair_corrs, axis=1).mean(axis=1, skipna=True)
    return _expanding_zscore(raw)


def _composite_score(dims: pd.DataFrame, weights: Mapping[str, float]) -> pd.Series:
    cols = [c for c in weights if c in dims.columns]
    if not cols:
        return pd.Series(np.nan, index=dims.index, dtype="float64")

    w = np.asarray([float(weights[c]) for c in cols], dtype="float64")
    vals = dims[cols].to_numpy(dtype="float64")
    mask = ~np.isnan(vals)
    w_mat = np.where(mask, w, 0.0)
    vals_filled = np.where(mask, vals, 0.0)

    numerator = np.sum(vals_filled * w_mat, axis=1)
    denominator = np.sum(w_mat, axis=1)

    out = np.full(len(dims), np.nan, dtype="float64")
    valid = denominator != 0.0
    out[valid] = numerator[valid] / denominator[valid]
    return pd.Series(out, index=dims.index)


# ---------------------------------------------------------------------------
# Helpers: niveles de emergencia (misma lógica que EXP-001)
# ---------------------------------------------------------------------------


def _raw_levels(score: pd.Series, theta: float) -> np.ndarray:
    arr = pd.Series(score, dtype="float64").to_numpy(dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = np.floor(arr / float(theta))
    keep = np.isfinite(arr) & (arr > 0.0)
    raw = np.where(keep, raw, 0.0)
    raw = np.clip(raw, 0.0, 4.0)
    return raw.astype(int)


def _assign_levels(score: pd.Series, theta: float, k: int, m: int) -> pd.Series:
    raw = _raw_levels(score, theta)
    n = len(raw)
    k = max(1, int(k))
    m = max(1, int(m))

    out = np.zeros(n, dtype=int)
    level = 0

    for t in range(n):
        # Subir: toda la ventana de k días debe superar el nivel actual.
        if t + 1 >= k:
            candidate_up = int(raw[t - k + 1 : t + 1].min())
            if candidate_up > level:
                level = candidate_up
                out[t] = level
                continue

        # Bajar: solo si no subió y toda la ventana de m días está por debajo.
        if t + 1 >= m:
            candidate_down = int(raw[t - m + 1 : t + 1].max())
            if candidate_down < level:
                level = candidate_down

        out[t] = level

    return pd.Series(out, index=score.index, dtype=int)


def _exposure_for_level(level: int) -> float:
    return float(_LEVEL_EXPOSURE[int(level)])


# ---------------------------------------------------------------------------
# Indicador diario
# ---------------------------------------------------------------------------


def compute_indicator(
    spy: pd.Series,
    vix: pd.Series,
    baa10y: pd.Series,
    rsp: pd.Series,
    sectors: pd.DataFrame,
    theta: float = 1.0,
    k: int = 3,
    m: int = 10,
) -> pd.DataFrame:
    """Calcula el indicador diario EXPERIMENTAL sobre el índice de SPY."""
    spy = pd.Series(spy, dtype="float64")
    idx = spy.index

    vix_aligned = pd.Series(vix).reindex(idx).ffill()
    baa_aligned = pd.Series(baa10y).reindex(idx).ffill()
    rsp_aligned = pd.Series(rsp).reindex(idx).ffill()

    sector_returns = sectors.pct_change().reindex(idx)

    dims = pd.DataFrame(index=idx)
    dims["trend"] = _trend_stress(spy)
    dims["vol"] = _vol_stress(vix_aligned)
    dims["correlation"] = _correlation_stress(sector_returns)
    dims["credit"] = _credit_stress(baa_aligned)
    dims["breadth"] = _breadth_stress(rsp_aligned, spy)
    dims["drawdown_velocity"] = _drawdown_velocity_stress(spy)

    weights = {col: 1.0 for col in _DIM_COLS}
    score = _composite_score(dims, weights)
    level = _assign_levels(score, theta=theta, k=k, m=m)
    exposure = level.map(_exposure_for_level).astype("float64")

    result = dims.copy()
    result["score"] = score
    result["level"] = level
    result["exposure"] = exposure
    return result


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _round_or_none(value: Any, ndigits: int) -> float | None:
    f = _safe_float(value)
    if f is None:
        return None
    return round(f, ndigits)


def _gauge_from_score(score: float | None) -> float | None:
    if score is None:
        return None
    f = max(0.0, min(float(score), 5.0))
    return round(f / 5.0 * 100.0, 1)


def _empty_latest() -> dict[str, Any]:
    return {
        "data_through": None,
        "score": None,
        "gauge": None,
        "level": None,
        "level_name": None,
        "exposure_target": None,
        "dimensions": {col: None for col in _DIM_COLS},
        "dimension_gauges": {col: None for col in _DIM_COLS},
        "params": dict(_PARAMS),
        "status": "SIN_DATOS",
        "disclaimer": _DISCLAIMER,
    }


def latest_payload(df: pd.DataFrame) -> dict[str, Any]:
    """Payload JSON determinista con la última observación válida del indicador."""
    if df is None or len(df) == 0 or "score" not in df.columns:
        return _empty_latest()

    scores_numeric = pd.to_numeric(df["score"], errors="coerce")
    score_arr = scores_numeric.to_numpy(dtype="float64")
    valid = np.isfinite(score_arr)
    positions = np.flatnonzero(valid)

    if len(positions) == 0:
        return _empty_latest()

    pos = int(positions[-1])
    row = df.iloc[pos]
    last_idx = df.index[pos]
    score_value = float(score_arr[pos])

    score_rounded = round(score_value, 3)
    gauge = _gauge_from_score(score_rounded)

    level_raw = row.get("level", 0)
    try:
        level = int(level_raw)
    except (TypeError, ValueError):
        level = 0

    if 0 <= level < len(LEVEL_NAMES):
        level_name = LEVEL_NAMES[level]
    else:
        level_name = None

    dimensions: dict[str, float | None] = {}
    dimension_gauges: dict[str, float | None] = {}
    for col in _DIM_COLS:
        value = _round_or_none(row.get(col), 3)
        dimensions[col] = value
        dimension_gauges[col] = _gauge_from_score(value)

    exposure_target = _safe_float(row.get("exposure"))

    return {
        "data_through": str(pd.Timestamp(last_idx).date()),
        "score": score_rounded,
        "gauge": gauge,
        "level": level,
        "level_name": level_name,
        "exposure_target": exposure_target,
        "dimensions": dimensions,
        "dimension_gauges": dimension_gauges,
        "params": dict(_PARAMS),
        "status": "EXPERIMENTAL",
        "disclaimer": _DISCLAIMER,
    }


def history_payload(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Historial JSON determinista de filas con score disponible."""
    if df is None or len(df) == 0 or "score" not in df.columns:
        return []

    work = df.loc[df["score"].notna()].sort_index()
    out: list[dict[str, Any]] = []

    for idx, row in work.iterrows():
        score = _round_or_none(row.get("score"), 3)
        if score is None:
            continue

        try:
            level = int(row.get("level", 0))
        except (TypeError, ValueError):
            level = 0

        out.append(
            {
                "d": str(pd.Timestamp(idx).date()),
                "s": score,
                "l": level,
            }
        )

    return out


def run(
    out_dir: str | Path,
    fetch_yahoo: Callable[[str], pd.DataFrame],
    fetch_fred: Callable[[str], pd.DataFrame],
) -> dict[str, Any]:
    """Descarga datos, calcula el indicador y escribe latest.json/history.json."""

    def _yahoo_series(symbol: str) -> pd.Series:
        frame = fetch_yahoo(symbol)
        if "adj_close" not in frame.columns:
            raise ValueError(f"Yahoo no devolvió 'adj_close' para {symbol!r}")
        return frame["adj_close"].copy()

    spy = _yahoo_series("SPY")
    rsp = _yahoo_series("RSP")
    vix = _yahoo_series("^VIX")

    sectors = pd.DataFrame({symbol: _yahoo_series(symbol) for symbol in _SECTOR_COLS})

    fred_frame = fetch_fred("BAA10Y")
    if "value" not in fred_frame.columns:
        raise ValueError("FRED no devolvió 'value' para 'BAA10Y'")
    baa10y = fred_frame["value"].copy()

    indicator = compute_indicator(spy, vix, baa10y, rsp, sectors)
    latest = latest_payload(indicator)
    history = history_payload(indicator)

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    (out_path / "latest.json").write_text(
        json.dumps(latest, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    (out_path / "history.json").write_text(
        json.dumps(history, allow_nan=False),
        encoding="utf-8",
    )

    return latest


def main() -> None:
    """Ejecuta el indicador con los fetchers reales del paquete."""
    from prl.data.build import descargar_fred, descargar_yahoo

    run(Path("public/emergency"), descargar_yahoo, descargar_fred)


if __name__ == "__main__":
    main()

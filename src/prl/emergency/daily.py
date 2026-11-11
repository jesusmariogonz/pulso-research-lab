from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from prl.emergency import features
from prl.emergency.grid import dimension_weights
from prl.emergency.state_machine import assign_levels, exposure_for_level


LEVEL_NAMES: list[str] = [
    "NORMAL",
    "VIGILANCIA",
    "DEFENSIVO",
    "EMERGENCIA",
    "CRISIS",
]

_DIMENSION_COLUMNS: tuple[str, ...] = (
    "trend",
    "vol",
    "correlation",
    "credit",
    "breadth",
    "drawdown_velocity",
)

_SECTORS: tuple[str, ...] = (
    "XLK",
    "XLE",
    "XLF",
    "XLV",
    "XLP",
    "XLU",
    "XLY",
    "XLI",
    "XLB",
)

_PARAMS: dict[str, Any] = {
    "weights": "equal",
    "theta": 1.0,
    "k": 3,
    "m": 10,
}

_DISCLAIMER = (
    "Indicador informativo y EXPERIMENTAL. No es asesoría financiera ni la "
    "política de inversión validada."
)


def _date_str(value: Any) -> str:
    """Devuelve una fecha ISO YYYY-MM-DD de forma determinista."""
    return value.strftime("%Y-%m-%d")


def _round_or_none(value: Any, ndigits: int) -> float | None:
    """Redondea un escalar y convierte NaN/inf a None para JSON."""
    if value is None or pd.isna(value):
        return None
    v = float(value)
    if not math.isfinite(v):
        return None
    return round(v, ndigits)


def _gauge_from_value(value: Any) -> float | None:
    """Convierte un z-score al gauge 0-100 recortando a [0, 5]."""
    if value is None or pd.isna(value):
        return None
    v = float(value)
    if not math.isfinite(v):
        return None
    v = min(max(v, 0.0), 5.0)
    return round(v / 5.0 * 100.0, 1)


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
    """Calcula el indicador diario alineado al índice de SPY.

    Usa exclusivamente los módulos revisados de features y state_machine, sin
    reimplementar la lógica del modelo.
    """
    idx = spy.index

    vix_aligned = vix.reindex(idx).ffill()
    baa10y_aligned = baa10y.reindex(idx).ffill()
    rsp_aligned = rsp.reindex(idx).ffill()

    sector_returns = sectors.pct_change().reindex(idx)

    dims = pd.DataFrame(
        {
            "trend": features.trend_stress(spy),
            "vol": features.vol_stress(vix_aligned),
            "correlation": features.correlation_stress(sector_returns),
            "credit": features.credit_stress(baa10y_aligned),
            "breadth": features.breadth_stress(rsp_aligned, spy),
            "drawdown_velocity": features.drawdown_velocity_stress(spy),
        },
        index=idx,
    )

    score = features.composite_score(dims, dimension_weights("equal"))
    levels = assign_levels(score, theta=theta, k=k, m=m).astype(int)
    exposure = levels.map(exposure_for_level).astype(float)

    out = dims.copy()
    out["score"] = score
    out["level"] = levels
    out["exposure"] = exposure
    return out


def latest_payload(df: pd.DataFrame) -> dict[str, Any]:
    """Construye el payload JSON de la última observación con score válido."""
    if "score" not in df.columns:
        valid = pd.Series(dtype=float)
    else:
        valid = df["score"].dropna()

    if valid.empty:
        return {
            "data_through": None,
            "score": None,
            "gauge": None,
            "level": None,
            "level_name": None,
            "exposure_target": None,
            "dimensions": {name: None for name in _DIMENSION_COLUMNS},
            "dimension_gauges": {name: None for name in _DIMENSION_COLUMNS},
            "params": dict(_PARAMS),
            "status": "SIN_DATOS",
            "disclaimer": _DISCLAIMER,
        }

    last_ts = valid.index[-1]
    row = df.loc[last_ts]

    score_raw = row.get("score")
    score = _round_or_none(score_raw, 3)

    level_raw = row.get("level")
    level = int(level_raw) if not pd.isna(level_raw) else 0

    exposure_raw = row.get("exposure")
    if pd.isna(exposure_raw):
        exposure_target = float(exposure_for_level(level))
    else:
        exposure_target = float(exposure_raw)

    dimensions: dict[str, float | None] = {}
    dimension_gauges: dict[str, float | None] = {}
    for name in _DIMENSION_COLUMNS:
        value = row.get(name)
        dimensions[name] = _round_or_none(value, 3)
        dimension_gauges[name] = _gauge_from_value(value)

    return {
        "data_through": _date_str(last_ts),
        "score": score,
        "gauge": _gauge_from_value(score_raw),
        "level": level,
        "level_name": LEVEL_NAMES[level],
        "exposure_target": exposure_target,
        "dimensions": dimensions,
        "dimension_gauges": dimension_gauges,
        "params": dict(_PARAMS),
        "status": "EXPERIMENTAL",
        "disclaimer": _DISCLAIMER,
    }


def history_payload(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Devuelve el historial compacto de score y nivel, en orden cronológico."""
    if "score" not in df.columns:
        return []

    sub = df.loc[df["score"].notna()].sort_index()
    out: list[dict[str, Any]] = []
    for ts, row in sub.iterrows():
        out.append(
            {
                "d": _date_str(ts),
                "s": _round_or_none(row.get("score"), 3),
                "l": int(row.get("level")),
            }
        )
    return out


def run(
    out_dir: str | Path,
    fetch_yahoo: Callable[[str], pd.DataFrame],
    fetch_fred: Callable[[str], pd.DataFrame],
) -> dict[str, Any]:
    """Descarga datos, calcula el indicador y escribe latest.json/history.json."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    yahoo_symbols = ["SPY", "RSP", "^VIX", *_SECTORS]
    prices: dict[str, pd.Series] = {}
    for symbol in yahoo_symbols:
        frame = fetch_yahoo(symbol)
        prices[symbol] = frame["adj_close"]

    baa_frame = fetch_fred("BAA10Y")
    baa10y = baa_frame["value"]

    spy = prices["SPY"]
    vix = prices["^VIX"]
    rsp = prices["RSP"]
    sectors = pd.DataFrame({symbol: prices[symbol] for symbol in _SECTORS})

    indicator = compute_indicator(spy, vix, baa10y, rsp, sectors)
    latest = latest_payload(indicator)
    history = history_payload(indicator)

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
    """Punto de entrada: descarga datos reales y escribe public/emergency."""
    from prl.data.build import descargar_fred, descargar_yahoo

    run(Path("public/emergency"), descargar_yahoo, descargar_fred)

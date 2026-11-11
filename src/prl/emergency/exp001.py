from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from prl.emergency.backtest import metrics, run_backtest
from prl.emergency.evaluation import (
    block_bootstrap_ci,
    deflated_sharpe_ratio,
    episode_report,
    label_result,
    non_episode_shortfall,
    walk_forward_select,
)
from prl.emergency.features import (
    breadth_stress,
    composite_score,
    correlation_stress,
    credit_stress,
    drawdown_velocity_stress,
    trend_stress,
    vol_stress,
)
from prl.emergency.grid import build_grid, destination_weights, dimension_weights
from prl.emergency.inputs import build_cash_index, common_start, sma200_exposure
from prl.emergency.state_machine import assign_levels, exposure_for_level


SECTORS: tuple[str, ...] = (
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

DEFAULT_EPISODES: list[dict[str, str]] = [
    {"name": "dot-com", "peak": "2000-03-24", "trough": "2002-10-09"},
    {"name": "crisis financiera", "peak": "2007-10-09", "trough": "2009-03-09"},
    {"name": "COVID", "peak": "2020-02-19", "trough": "2020-03-23"},
    {"name": "2022", "peak": "2022-01-03", "trough": "2022-10-12"},
]


def _read_parquet(inputs_dir: Path, name: str) -> pd.DataFrame:
    """Lee un parquet requerido de ``inputs_dir`` y falla con claridad si falta."""
    path = inputs_dir / f"{name}.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo requerido: {path}")
    df = pd.read_parquet(path)
    if not isinstance(df, pd.DataFrame):
        raise ValueError(f"{path} no contiene un DataFrame")
    return df


def _price_series(inputs_dir: Path, name: str) -> pd.Series:
    """Carga una serie de precios con columna ``adj_close``."""
    df = _read_parquet(inputs_dir, name)
    if "adj_close" not in df.columns:
        raise ValueError(f"{name}.parquet no contiene la columna 'adj_close'")
    s = df["adj_close"].copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s.name = name
    return s


def _fred_series(inputs_dir: Path, name: str) -> pd.Series:
    """Carga una serie FRED con columna ``value``."""
    df = _read_parquet(inputs_dir, name)
    if "value" not in df.columns:
        raise ValueError(f"{name}.parquet no contiene la columna 'value'")
    s = df["value"].copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s.name = name
    return s


def _json_safe(obj: Any) -> Any:
    """Convierte recursivamente a tipos JSON, reemplazando NaN/inf por ``None``."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if obj is None or obj is pd.NaT:
        return None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        value = float(obj)
        return value if math.isfinite(value) else None
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (pd.Timestamp, _dt.datetime, _dt.date)):
        return obj.strftime("%Y-%m-%d")
    return obj


def _calmar_diff(a: pd.Series, b: pd.Series) -> float:
    """Diferencia de Calmar entre dos series de retornos."""
    return float(metrics(a)["calmar"] - metrics(b)["calmar"])


def run(
    inputs_dir: str | Path,
    run_dir: str | Path,
    first_test_year: int = 2003,
    n_boot: int = 500,
    episodes: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Ejecuta EXP-001, escribe ``results.json`` y devuelve el resultado."""
    inputs_path = Path(inputs_dir)
    output_path = Path(run_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 1. Entradas
    spy = _price_series(inputs_path, "SPY")
    vix = _price_series(inputs_path, "VIX")
    baa10y = _fred_series(inputs_path, "BAA10Y")
    rsp = _price_series(inputs_path, "RSP")
    tlt = _price_series(inputs_path, "TLT")
    bil = _price_series(inputs_path, "BIL")
    dtb3 = _fred_series(inputs_path, "DTB3")

    sector_prices = pd.DataFrame(
        {name: _price_series(inputs_path, name).reindex(spy.index) for name in SECTORS},
        index=spy.index,
    )

    # 2. Dimensiones de estrés alineadas a SPY
    vix_aligned = vix.reindex(spy.index)
    rsp_aligned = rsp.reindex(spy.index)
    baa10y_aligned = baa10y.reindex(spy.index).ffill()

    sector_returns = sector_prices / sector_prices.shift(1) - 1.0

    dims = pd.DataFrame(index=spy.index)
    dims["trend"] = trend_stress(spy).reindex(spy.index)
    dims["vol"] = vol_stress(vix_aligned).reindex(spy.index)
    dims["credit"] = credit_stress(baa10y_aligned).reindex(spy.index)
    dims["breadth"] = breadth_stress(rsp_aligned, spy).reindex(spy.index)
    dims["drawdown_velocity"] = drawdown_velocity_stress(spy).reindex(spy.index)
    dims["correlation"] = correlation_stress(sector_returns).reindex(spy.index)

    # 3. Índice de efectivo y precios del backtest
    cash = build_cash_index(dtb3, bil).reindex(spy.index).ffill()

    tlt_aligned = tlt.reindex(spy.index)
    prices_all = pd.DataFrame(
        {"SPY": spy, "TLT": tlt_aligned, "CASH": cash},
        index=spy.index,
    )

    start = common_start({"SPY": spy, "TLT": tlt_aligned, "CASH": cash})
    prices = prices_all.loc[prices_all.index >= start].copy()

    # 4. Variantes
    grid = build_grid()

    variant_returns: dict[str, pd.Series] = {}
    variant_levels: dict[str, pd.Series] = {}
    variant_exposures: dict[str, pd.Series] = {}
    variant_costs: dict[str, pd.Series] = {}

    for variant in grid:
        variant_id = str(variant["variant_id"])
        weights = dimension_weights(str(variant["weights"]))

        score = composite_score(dims, weights)
        level = assign_levels(
            score,
            float(variant["theta"]),
            int(variant["k"]),
            int(variant["m"]),
        )
        exposure = level.map(exposure_for_level)

        bt = run_backtest(
            prices,
            exposure,
            "SPY",
            destination_weights(str(variant["destination"])),
            0.001,
        )

        variant_returns[variant_id] = bt["ret"]
        variant_levels[variant_id] = level
        variant_exposures[variant_id] = bt["exposure_applied"]
        variant_costs[variant_id] = bt["cost"]

    # 5. Selección walk-forward y estados fuera de muestra
    oos_ret, chosen_by_year = walk_forward_select(
        variant_returns,
        first_test_year,
        criterion="calmar",
    )
    oos_ret = oos_ret.sort_index()

    oos_level_float = pd.Series(np.nan, index=oos_ret.index, dtype="float64")
    oos_exposure = pd.Series(np.nan, index=oos_ret.index, dtype="float64")
    oos_cost = pd.Series(np.nan, index=oos_ret.index, dtype="float64")

    for year, variant_id in sorted(chosen_by_year.items(), key=lambda kv: int(kv[0])):
        year_int = int(year)
        mask = oos_ret.index.year == year_int
        if not bool(mask.any()):
            continue

        idx = oos_ret.index[mask]
        vid = str(variant_id)

        oos_level_float.loc[idx] = variant_levels[vid].reindex(idx).astype(float)
        oos_exposure.loc[idx] = variant_exposures[vid].reindex(idx)
        oos_cost.loc[idx] = variant_costs[vid].reindex(idx)

    if oos_level_float.isna().any():
        raise ValueError("Hay fechas OOS sin nivel asignado")
    if oos_exposure.isna().any():
        raise ValueError("Hay fechas OOS sin exposición aplicada")
    if oos_cost.isna().any():
        raise ValueError("Hay fechas OOS sin costo")

    oos_level = oos_level_float.astype(int)

    # 6. Benchmarks sobre las mismas fechas OOS
    buy_hold_exposure = pd.Series(1.0, index=prices.index)
    sma_exposure = sma200_exposure(prices["SPY"])
    sixty_forty_exposure = pd.Series(0.6, index=prices.index)

    buy_hold_bt = run_backtest(
        prices,
        buy_hold_exposure,
        "SPY",
        {"CASH": 1.0},
        0.001,
    )
    sma200_bt = run_backtest(
        prices,
        sma_exposure,
        "SPY",
        {"CASH": 1.0},
        0.001,
    )
    sixty_forty_bt = run_backtest(
        prices,
        sixty_forty_exposure,
        "SPY",
        {"TLT": 1.0},
        0.001,
    )

    buy_hold_ret = buy_hold_bt["ret"].reindex(oos_ret.index)
    sma200_ret = sma200_bt["ret"].reindex(oos_ret.index)
    sixty_forty_ret = sixty_forty_bt["ret"].reindex(oos_ret.index)

    for name, series in (
        ("buy_hold", buy_hold_ret),
        ("sma200", sma200_ret),
        ("sixty_forty", sixty_forty_ret),
    ):
        if series.isna().any():
            raise ValueError(f"El benchmark {name} tiene NaN en el período OOS")

    # 7. Métricas e intervalo bootstrap
    model_metrics = metrics(oos_ret)
    buy_hold_metrics = metrics(buy_hold_ret)
    sma200_metrics = metrics(sma200_ret)
    sixty_forty_metrics = metrics(sixty_forty_ret)

    ci_lo, ci_hi = block_bootstrap_ci(
        oos_ret,
        sma200_ret,
        _calmar_diff,
        block=20,
        n_boot=int(n_boot),
        seed=0,
    )

    # 8. Episodios y métricas específicas
    episodes_used = DEFAULT_EPISODES if episodes is None else list(episodes)
    oos_start_ts = oos_ret.index.min()

    evaluable_episodes: list[dict[str, str]] = []
    excluded_episodes: list[str] = []

    for episode in episodes_used:
        peak = pd.Timestamp(episode["peak"])
        if peak >= oos_start_ts:
            evaluable_episodes.append(episode)
        else:
            excluded_episodes.append(str(episode["name"]))

    spy_oos = prices["SPY"].reindex(oos_level.index)
    episode_out = episode_report(spy_oos, oos_level, evaluable_episodes)
    shortfall = non_episode_shortfall(oos_ret, buy_hold_ret, evaluable_episodes)
    deflated_sharpe = float(deflated_sharpe_ratio(oos_ret, n_trials=162))

    # 9. Etiqueta
    label = label_result(
        {
            "maxdd_model": model_metrics["max_drawdown"],
            "maxdd_bh": buy_hold_metrics["max_drawdown"],
            "cagr_model": model_metrics["cagr"],
            "cagr_bh": buy_hold_metrics["cagr"],
            "calmar_model": model_metrics["calmar"],
            "calmar_sma": sma200_metrics["calmar"],
            "calmar_diff_ci_lo": ci_lo,
        }
    )

    # 10. Resultado
    n_oos_days = int(len(oos_ret))
    level_counts = oos_level.value_counts()
    level_fractions = {
        str(level): float(level_counts.get(level, 0)) / float(n_oos_days)
        for level in range(5)
    }

    turnover = float(oos_exposure.diff().abs().sum(skipna=True))
    costs_paid = float(oos_cost.sum(skipna=True))

    results: dict[str, Any] = {
        "experiment": "EXP-001",
        "first_test_year": int(first_test_year),
        "oos_start": oos_ret.index.min().strftime("%Y-%m-%d"),
        "oos_end": oos_ret.index.max().strftime("%Y-%m-%d"),
        "n_variants": int(len(grid)),
        "n_oos_days": n_oos_days,
        "metrics": {
            "model": model_metrics,
            "buy_hold": buy_hold_metrics,
            "sma200": sma200_metrics,
            "sixty_forty": sixty_forty_metrics,
        },
        "calmar_diff_vs_sma200": {
            "value": float(model_metrics["calmar"] - sma200_metrics["calmar"]),
            "ci_lo": float(ci_lo),
            "ci_hi": float(ci_hi),
            "n_boot": int(n_boot),
            "block": 20,
        },
        "episodes": episode_out,
        "episodes_excluded_not_oos": excluded_episodes,
        "non_episode_shortfall": float(shortfall),
        "deflated_sharpe": deflated_sharpe,
        "chosen_by_year": {
            str(year): str(variant_id)
            for year, variant_id in sorted(
                chosen_by_year.items(),
                key=lambda kv: int(kv[0]),
            )
        },
        "level_fractions": level_fractions,
        "turnover": turnover,
        "costs_paid": costs_paid,
        "label": label,
        "notes": [
            "Rebalanceo diario del refugio sin costo de transacción.",
            "Crédito medido solo con BAA10Y; sin HYG/LQD en v0.",
            "Amplitud medida solo con proxies (RSP/SPY y sectores).",
            "Pocos eventos independientes para evaluar la regla.",
            "Los episodios previos al primer año de prueba no se evalúan fuera de muestra.",
        ],
    }

    safe_results = _json_safe(results)
    text = json.dumps(safe_results, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    (output_path / "results.json").write_text(text, encoding="utf-8")

    return safe_results

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

__all__ = [
    "walk_forward_select",
    "block_bootstrap_ci",
    "deflated_sharpe_ratio",
    "episode_report",
    "non_episode_shortfall",
    "label_result",
]


def _fmt_date(value: Any) -> str | None:
    """Formatea una fecha como YYYY-MM-DD; None/NaT -> None."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    return ts.date().isoformat()


def walk_forward_select(
    variant_returns: Mapping[str, pd.Series],
    first_test_year: int,
    criterion: str = "calmar",
) -> Tuple[pd.Series, Dict[int, str]]:
    """Selecciona variantes con walk-forward anual sin mirar el año de prueba."""
    from prl.emergency.backtest import metrics

    if not variant_returns:
        return pd.Series(dtype=float), {}

    series_list = list(variant_returns.values())
    non_empty = [s for s in series_list if len(s) > 0]
    if not non_empty:
        return pd.Series(dtype=float), {}

    last_year = max(int(s.index.max().year) for s in non_empty)
    if last_year < first_test_year:
        return pd.Series(dtype=float), {}

    reference = non_empty[0]
    chosen_by_year: Dict[int, str] = {}
    pieces: list[pd.Series] = []

    for year in range(int(first_test_year), last_year + 1):
        year_start = pd.Timestamp(year=year, month=1, day=1)

        train_reference = reference.loc[reference.index < year_start]
        if len(train_reference) < 252:
            raise ValueError(
                f"Entrenamiento previo a {year} con {len(train_reference)} retornos; "
                "se exigen al menos 252."
            )

        best_id: str | None = None
        best_value = -np.inf

        for variant_id, ret in variant_returns.items():
            train = ret.loc[ret.index < year_start]
            m = metrics(train)
            value = m.get(criterion, np.nan)
            try:
                value_float = float(value)
            except (TypeError, ValueError):
                value_float = np.nan

            if not np.isfinite(value_float):
                value_float = -np.inf

            if best_id is None or value_float > best_value:
                best_id = variant_id
                best_value = value_float

        assert best_id is not None
        chosen_by_year[year] = best_id

        chosen_ret = variant_returns[best_id]
        year_ret = chosen_ret.loc[chosen_ret.index.year == year]
        if len(year_ret) > 0:
            pieces.append(year_ret)

    if pieces:
        oos = pd.concat(pieces).sort_index()
        oos.name = None
    else:
        oos = pd.Series(dtype=float)

    return oos, chosen_by_year


def block_bootstrap_ci(
    r_a: pd.Series,
    r_b: pd.Series,
    statistic: Callable[[pd.Series, pd.Series], float],
    block: int = 20,
    n_boot: int = 500,
    alpha: float = 0.05,
    seed: int = 0,
) -> Tuple[float, float]:
    """Block bootstrap pareado con bloques consecutivos y percentiles."""
    n = len(r_a)
    if len(r_b) != n:
        raise ValueError("r_a y r_b deben tener la misma longitud.")
    if n < block:
        raise ValueError("n debe ser mayor o igual que block.")
    if n_boot <= 0:
        raise ValueError("n_boot debe ser positivo.")

    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    max_start = n - block

    a_values = np.asarray(r_a, dtype=float)
    b_values = np.asarray(r_b, dtype=float)
    original_index = r_a.index

    boot_stats: list[float] = []
    for _ in range(int(n_boot)):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        positions = np.concatenate(
            [np.arange(start, start + block, dtype=int) for start in starts]
        )[:n]

        sample_a = pd.Series(a_values[positions], index=original_index)
        sample_b = pd.Series(b_values[positions], index=original_index)
        boot_stats.append(float(statistic(sample_a, sample_b)))

    lo, hi = np.percentile(
        boot_stats,
        [100.0 * alpha / 2.0, 100.0 * (1.0 - alpha / 2.0)],
    )
    return float(lo), float(hi)


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float:
    """Deflated Sharpe ratio diario según el contrato EXP-001."""
    r = pd.Series(returns, dtype=float)
    n = len(r)
    if n < 2:
        return float("nan")

    sr = float(r.mean() / r.std(ddof=1))
    g3 = float(r.skew())
    g4 = float(r.kurt() + 3.0)

    variance = (1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr) / float(n - 1)
    if variance < 0.0 and variance > -1e-15:
        variance = 0.0
    if not np.isfinite(variance) or variance < 0.0:
        return float("nan")

    sr_std = math.sqrt(float(variance))
    if sr_std == 0.0:
        if sr > 0.0:
            return 1.0
        if sr < 0.0:
            return 0.0
        return 0.5

    if int(n_trials) <= 1:
        sr0 = 0.0
    else:
        n_trials_float = float(n_trials)
        gamma = 0.5772156649015329
        sr0 = sr_std * (
            (1.0 - gamma) * norm.ppf(1.0 - 1.0 / n_trials_float)
            + gamma * norm.ppf(1.0 - 1.0 / (n_trials_float * math.e))
        )

    return float(norm.cdf((sr - sr0) / sr_std))


def episode_report(
    close: pd.Series,
    level: pd.Series,
    episodes: Sequence[Mapping[str, Any]],
) -> dict:
    """Evalúa detección de episodios y falsas alarmas de nivel 4."""
    close = pd.Series(close, dtype=float)
    level_aligned = level.reindex(close.index)

    episode_rows: list[dict] = []
    for ep in episodes:
        name = ep["name"]
        peak = pd.Timestamp(ep["peak"])
        trough = pd.Timestamp(ep["trough"])

        if peak in close.index:
            peak_price = close.loc[peak]
        else:
            prior = close.loc[close.index <= peak]
            peak_price = prior.iloc[-1] if len(prior) > 0 else np.nan

        cross20: pd.Timestamp | None = None
        if pd.notna(peak_price) and float(peak_price) != 0.0:
            crossed = (
                (close.index > peak)
                & ((close / float(peak_price) - 1.0) <= -0.20)
            )
            if bool(crossed.any()):
                cross20 = close.index[crossed][0]

        detection_date: pd.Timestamp | None = None
        if cross20 is not None:
            lower = peak - pd.Timedelta(days=90)
            window_mask = (close.index >= lower) & (close.index <= cross20)
            window_index = close.index[window_mask]
            if len(window_index) > 0:
                window_levels = level_aligned.reindex(window_index)
                hits = window_levels[window_levels >= 2]
                if len(hits) > 0:
                    detection_date = hits.index[0]

        lead_days = (
            int((cross20 - detection_date).days)
            if cross20 is not None and detection_date is not None
            else None
        )

        episode_rows.append(
            {
                "name": name,
                "peak": _fmt_date(peak),
                "trough": _fmt_date(trough),
                "cross20": _fmt_date(cross20),
                "detection_date": _fmt_date(detection_date),
                "lead_days": lead_days,
                "detected": detection_date is not None,
            }
        )

    levels = level_aligned.fillna(0).to_numpy()
    is_alarm = levels == 4

    start_positions: list[int] = []
    in_run = False
    for i, flag in enumerate(is_alarm):
        if flag and not in_run:
            start_positions.append(i)
            in_run = True
        elif not flag:
            in_run = False

    close_values = close.to_numpy(dtype=float)
    n_false = 0
    n_unevaluable = 0
    false_dates: list[str] = []

    for pos in start_positions:
        after = close_values[pos + 1 : pos + 61]
        base = close_values[pos]

        if len(after) < 60 or not np.isfinite(base) or base == 0.0:
            n_unevaluable += 1
            continue

        relative = after / base - 1.0
        if np.isnan(relative).all():
            n_unevaluable += 1
            continue

        if float(np.nanmin(relative)) > -0.10:
            n_false += 1
            date = _fmt_date(close.index[pos])
            if date is not None:
                false_dates.append(date)

    return {
        "episodes": episode_rows,
        "alarms": {
            "n_alarms": len(start_positions),
            "n_false": n_false,
            "n_unevaluable": n_unevaluable,
            "false_dates": false_dates,
        },
    }


def non_episode_shortfall(
    model_returns: pd.Series,
    bench_returns: pd.Series,
    episodes: Sequence[Mapping[str, Any]],
) -> float:
    """Diferencia de retorno acumulado fuera de episodios: benchmark - modelo."""
    index = model_returns.index.intersection(bench_returns.index).sort_values()
    keep = pd.Series(True, index=index, dtype=bool)

    for ep in episodes:
        peak = pd.Timestamp(ep["peak"])
        trough = pd.Timestamp(ep["trough"])
        keep &= ~((index >= peak) & (index <= trough))

    model = model_returns.reindex(index).loc[keep]
    bench = bench_returns.reindex(index).loc[keep]

    model_total = float((1.0 + model).prod())
    bench_total = float((1.0 + bench).prod())
    return bench_total - model_total


def label_result(m: Mapping[str, Any]) -> str:
    """Etiqueta final VALIDATED / REJECTED / INCONCLUSIVE según el contrato."""
    required = [
        "maxdd_model",
        "maxdd_bh",
        "cagr_model",
        "cagr_bh",
        "calmar_model",
        "calmar_sma",
        "calmar_diff_ci_lo",
    ]

    values: dict[str, float] = {}
    for key in required:
        if key not in m:
            return "INCONCLUSIVE"
        try:
            value = float(m[key])
        except (TypeError, ValueError):
            return "INCONCLUSIVE"
        if not math.isfinite(value):
            return "INCONCLUSIVE"
        values[key] = value

    maxdd_model = values["maxdd_model"]
    maxdd_bh = values["maxdd_bh"]
    cagr_model = values["cagr_model"]
    cagr_bh = values["cagr_bh"]
    calmar_model = values["calmar_model"]
    calmar_sma = values["calmar_sma"]
    calmar_diff_ci_lo = values["calmar_diff_ci_lo"]

    if calmar_model <= calmar_sma or abs(maxdd_model) >= abs(maxdd_bh):
        return "REJECTED"

    if (
        abs(maxdd_model) <= 0.70 * abs(maxdd_bh)
        and cagr_model >= 0.90 * cagr_bh
        and calmar_diff_ci_lo > 0.0
    ):
        return "VALIDATED"

    return "INCONCLUSIVE"

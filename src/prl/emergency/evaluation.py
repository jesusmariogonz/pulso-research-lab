from __future__ import annotations

import math
from typing import Callable, Mapping

import numpy as np
import pandas as pd
from scipy.stats import norm

from prl.emergency.backtest import metrics


def walk_forward_select(
    variant_returns: Mapping[str, pd.Series],
    first_test_year: int,
    criterion: str = "calmar",
) -> tuple[pd.Series, dict[int, str]]:
    """Selecciona variantes año a año usando solo información previa al año de prueba."""
    if not variant_returns:
        raise ValueError("variant_returns está vacío")

    first_series = next(iter(variant_returns.values()))
    if len(first_series) == 0:
        raise ValueError("las series de retornos están vacías")

    all_years = sorted(
        {int(year) for series in variant_returns.values() for year in series.index.year}
    )
    test_years = [year for year in all_years if year >= int(first_test_year)]

    oos_parts: list[pd.Series] = []
    chosen_by_year: dict[int, str] = {}

    for year in test_years:
        train_len = int((first_series.index.year < year).sum())
        if train_len < 252:
            raise ValueError(
                f"entrenamiento insuficiente para {year}: {train_len} < 252"
            )

        best_id: str | None = None
        best_value = -np.inf

        for variant_id, series in variant_returns.items():
            train = series[series.index.year < year]
            if len(train) < 252:
                raise ValueError(
                    f"entrenamiento insuficiente para {variant_id} en {year}: "
                    f"{len(train)} < 252"
                )

            result = metrics(train)
            value = result.get(criterion, np.nan)
            try:
                fvalue = float(value)
            except (TypeError, ValueError):
                fvalue = -np.inf

            if not math.isfinite(fvalue):
                fvalue = -np.inf

            if best_id is None or fvalue > best_value:
                best_id = variant_id
                best_value = fvalue

        if best_id is None:
            raise ValueError(f"no se pudo seleccionar variante para {year}")

        chosen_by_year[year] = best_id
        test_part = variant_returns[best_id]
        test_part = test_part[test_part.index.year == year]
        if len(test_part) > 0:
            oos_parts.append(test_part)

    if oos_parts:
        oos = pd.concat(oos_parts).sort_index()
    else:
        oos = pd.Series(dtype=float, index=pd.DatetimeIndex([]))

    return oos, chosen_by_year


def block_bootstrap_ci(
    r_a: pd.Series,
    r_b: pd.Series,
    statistic: Callable[[pd.Series, pd.Series], float],
    block: int = 20,
    n_boot: int = 500,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    """Intervalo de confianza bootstrap por bloques pareados para statistic(r_a, r_b)."""
    n = len(r_a)
    if len(r_b) != n:
        raise ValueError("r_a y r_b deben tener la misma longitud")
    if block <= 0:
        raise ValueError("block debe ser positivo")
    if n < block:
        raise ValueError(f"n={n} es menor que block={block}")
    if n_boot <= 0:
        raise ValueError("n_boot debe ser positivo")

    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    stats: list[float] = []

    for _ in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        rows: list[int] = []
        for start in starts:
            rows.extend(range(int(start), int(start) + block))
        selected = np.asarray(rows[:n], dtype=int)

        a = r_a.iloc[selected]
        b = r_b.iloc[selected]
        stats.append(float(statistic(a, b)))

    lo, hi = np.percentile(
        stats,
        [100.0 * alpha / 2.0, 100.0 * (1.0 - alpha / 2.0)],
    )
    return float(lo), float(hi)


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float:
    """Deflated Sharpe Ratio según el número de intentos/pruebas."""
    n = len(returns)
    if n < 2:
        raise ValueError("se necesitan al menos 2 retornos")

    sr = float(returns.mean() / returns.std(ddof=1))
    g3 = float(returns.skew())
    g4 = float(returns.kurt() + 3.0)

    sr_std = math.sqrt(
        (1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr**2) / (n - 1)
    )

    if n_trials <= 1:
        sr0 = 0.0
    else:
        gamma = 0.5772156649015329
        n_trials_f = float(n_trials)
        sr0 = sr_std * (
            (1.0 - gamma) * norm.ppf(1.0 - 1.0 / n_trials_f)
            + gamma * norm.ppf(1.0 - 1.0 / (n_trials_f * math.e))
        )

    return float(norm.cdf((sr - sr0) / sr_std))


def episode_report(
    close: pd.Series,
    level: pd.Series,
    episodes: list[dict],
) -> dict:
    """Reporte de detección de episodios y de falsas alarmas de nivel 4."""
    close = close.sort_index()
    level_aligned = level.reindex(close.index)

    episode_output: list[dict] = []

    for episode in episodes:
        peak_ts = pd.Timestamp(episode["peak"])
        trough_ts = pd.Timestamp(episode["trough"])

        base_price = close.loc[peak_ts]
        ratio = close / base_price - 1.0
        posterior = close.index > peak_ts
        cross_mask = posterior & (ratio <= -0.20)

        if cross_mask.any():
            cross20_ts: pd.Timestamp | None = close.index[cross_mask][0]
        else:
            cross20_ts = None

        detection_ts: pd.Timestamp | None = None
        if cross20_ts is not None:
            window_mask = (
                (close.index >= peak_ts - pd.Timedelta(days=90))
                & (close.index <= cross20_ts)
            )
            level_values = level_aligned.fillna(-np.inf).to_numpy()
            detection_mask = window_mask & (level_values >= 2)
            if detection_mask.any():
                detection_ts = close.index[detection_mask][0]

        if cross20_ts is not None and detection_ts is not None:
            lead_days: int | None = int((cross20_ts - detection_ts).days)
        else:
            lead_days = None

        episode_output.append(
            {
                "name": episode["name"],
                "peak": peak_ts.strftime("%Y-%m-%d"),
                "trough": trough_ts.strftime("%Y-%m-%d"),
                "cross20": (
                    cross20_ts.strftime("%Y-%m-%d")
                    if cross20_ts is not None
                    else None
                ),
                "detection_date": (
                    detection_ts.strftime("%Y-%m-%d")
                    if detection_ts is not None
                    else None
                ),
                "lead_days": lead_days,
                "detected": detection_ts is not None,
            }
        )

    level_values = level_aligned.fillna(-1).to_numpy()
    is_alarm = level_values == 4

    alarm_starts: list[int] = []
    i = 0
    while i < len(is_alarm):
        if is_alarm[i]:
            alarm_starts.append(i)
            while i + 1 < len(is_alarm) and is_alarm[i + 1]:
                i += 1
        i += 1

    n_false = 0
    n_unevaluable = 0
    false_dates: list[str] = []

    for pos in alarm_starts:
        if pos + 60 >= len(close):
            n_unevaluable += 1
            continue

        base_price = close.iloc[pos]
        future = close.iloc[pos + 1 : pos + 61]
        min_return = float((future / base_price - 1.0).min())

        if min_return > -0.10:
            n_false += 1
            false_dates.append(close.index[pos].strftime("%Y-%m-%d"))

    return {
        "episodes": episode_output,
        "alarms": {
            "n_alarms": len(alarm_starts),
            "n_false": n_false,
            "n_unevaluable": n_unevaluable,
            "false_dates": false_dates,
        },
    }


def non_episode_shortfall(
    model_returns: pd.Series,
    bench_returns: pd.Series,
    episodes: list[dict],
) -> float:
    """Retorno acumulado del benchmark menos el del modelo fuera de episodios."""
    common_index = model_returns.index.intersection(bench_returns.index).sort_values()
    keep = np.ones(len(common_index), dtype=bool)

    for episode in episodes:
        peak_ts = pd.Timestamp(episode["peak"])
        trough_ts = pd.Timestamp(episode["trough"])
        in_episode = (common_index >= peak_ts) & (common_index <= trough_ts)
        keep &= ~in_episode

    model = model_returns.reindex(common_index)[keep]
    bench = bench_returns.reindex(common_index)[keep]

    model_total = float(np.prod(1.0 + model.to_numpy()))
    bench_total = float(np.prod(1.0 + bench.to_numpy()))
    return bench_total - model_total


def label_result(m: dict) -> str:
    """Etiqueta final VALIDATED / REJECTED / INCONCLUSIVE."""
    required_keys = [
        "maxdd_model",
        "maxdd_bh",
        "cagr_model",
        "cagr_bh",
        "calmar_model",
        "calmar_sma",
        "calmar_diff_ci_lo",
    ]

    try:
        values = {key: float(m[key]) for key in required_keys}
    except (KeyError, TypeError, ValueError):
        return "INCONCLUSIVE"

    if any(math.isnan(value) for value in values.values()):
        return "INCONCLUSIVE"

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


__all__ = [
    "walk_forward_select",
    "block_bootstrap_ci",
    "deflated_sharpe_ratio",
    "episode_report",
    "non_episode_shortfall",
    "label_result",
]

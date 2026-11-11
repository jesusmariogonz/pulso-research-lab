from __future__ import annotations

import numpy as np
import pandas as pd


_EXPOSURE_BY_LEVEL: dict[int, float] = {
    0: 1.0,
    1: 0.75,
    2: 0.5,
    3: 0.25,
    4: 0.0,
}


def exposure_for_level(level: int) -> float:
    """Devuelve la exposición objetivo asociada a un nivel de emergencia."""
    return _EXPOSURE_BY_LEVEL[int(level)]


def raw_levels(score: pd.Series, theta: float) -> pd.Series:
    """Convierte un score de estrés en niveles crudos enteros 0–4."""
    values = score.to_numpy(dtype=float)
    scaled = np.floor(values / float(theta))
    scaled = np.where(np.isnan(scaled) | (values < 0.0), 0.0, scaled)
    scaled = np.clip(scaled, 0.0, 4.0)
    return pd.Series(
        scaled.astype(int),
        index=score.index,
        name=score.name,
    )


def assign_levels(
    score: pd.Series,
    theta: float,
    k: int,
    m: int,
) -> pd.Series:
    """Aplica persistencia y histéresis a los niveles crudos de estrés."""
    raw = raw_levels(score, theta)
    n = len(raw)
    if n == 0:
        return pd.Series([], index=score.index, dtype=int, name=score.name)

    raw_values = raw.to_numpy(dtype=int)

    up_candidates = (
        raw.rolling(window=k, min_periods=k).min().to_numpy(dtype=float)
    )
    down_candidates = (
        raw.rolling(window=m, min_periods=m).max().to_numpy(dtype=float)
    )

    levels = np.zeros(n, dtype=int)
    current = 0

    for t in range(n):
        rose = False

        candidate_up = up_candidates[t]
        if not np.isnan(candidate_up):
            candidate_up_int = int(candidate_up)
            if candidate_up_int > current:
                current = candidate_up_int
                rose = True

        if not rose:
            candidate_down = down_candidates[t]
            if not np.isnan(candidate_down):
                candidate_down_int = int(candidate_down)
                if candidate_down_int < current:
                    current = candidate_down_int

        levels[t] = current

    return pd.Series(levels, index=score.index, dtype=int, name=score.name)

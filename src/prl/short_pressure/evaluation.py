from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy.stats import norm, rankdata


# --------------------------------------------------------------------------- #
# Utilidades internas (comparaciones a prueba de NaN / None)
# --------------------------------------------------------------------------- #


def _es_numero(valor: Any) -> bool:
    """True si ``valor`` se puede convertir a float finito."""
    if valor is None:
        return False
    try:
        return math.isfinite(float(valor))
    except (TypeError, ValueError):
        return False


def _cmp_le(a: Any, b: float) -> bool:
    return _es_numero(a) and float(a) <= b


def _cmp_lt(a: Any, b: float) -> bool:
    return _es_numero(a) and float(a) < b


def _cmp_ge(a: Any, b: float) -> bool:
    return _es_numero(a) and float(a) >= b


def _cmp_gt(a: Any, b: float) -> bool:
    return _es_numero(a) and float(a) > b


# --------------------------------------------------------------------------- #
# bootstrap_bloques
# --------------------------------------------------------------------------- #


def bootstrap_bloques(
    retornos: pd.DataFrame,
    tamano_bloque: int,
    n_replicas: int,
    seed: int,
) -> np.ndarray:
    """Block bootstrap de filas.

    Devuelve un array de forma ``(n_replicas, n, n_columnas)`` donde cada
    réplica es una remuestreo por bloques contiguos (con reemplazo) de las
    filas de ``retornos``, truncado a ``n = len(retornos)`` filas.
    """
    if tamano_bloque < 1:
        raise ValueError("tamano_bloque debe ser >= 1")
    n = len(retornos)
    if n < tamano_bloque:
        raise ValueError(
            f"n ({n}) debe ser >= tamano_bloque ({tamano_bloque})"
        )
    valores = retornos.to_numpy(dtype=float)
    if valores.ndim == 1:
        valores = valores.reshape(-1, 1)
    n_cols = valores.shape[1]
    n_bloques = int(math.ceil(n / tamano_bloque))
    posibles_inicios = n - tamano_bloque + 1
    rng = np.random.default_rng(seed)
    out = np.empty((n_replicas, n, n_cols), dtype=float)
    for r in range(n_replicas):
        inicios = rng.integers(0, posibles_inicios, size=n_bloques)
        indices = np.concatenate(
            [np.arange(s, s + tamano_bloque) for s in inicios]
        )[:n]
        out[r] = valores[indices]
    return out


# --------------------------------------------------------------------------- #
# comparacion_bootstrap
# --------------------------------------------------------------------------- #


def comparacion_bootstrap(
    ret_bucket: pd.Series,
    ret_baseline: pd.Series,
    tamano_bloque: int = 2,
    n_replicas: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict:
    """Bootstrap pareado de la diferencia ``ret_bucket - ret_baseline``."""
    if not ret_bucket.index.equals(ret_baseline.index):
        raise ValueError(
            "Los índices de ret_bucket y ret_baseline deben coincidir"
        )

    dif = ret_bucket - ret_baseline
    n = len(dif)
    if n == 0:
        return {
            "frac_supera_baseline": float("nan"),
            "media_bucket": float("nan"),
            "media_baseline": float("nan"),
            "media_dif": float("nan"),
            "ic_inferior": float("nan"),
            "ic_superior": float("nan"),
            "n_observaciones": 0,
            "n_replicas": int(n_replicas),
            "tamano_bloque": int(tamano_bloque),
        }

    bloque_efectivo = int(tamano_bloque)
    if bloque_efectivo > n:
        bloque_efectivo = n
    if bloque_efectivo < 1:
        bloque_efectivo = 1

    df_dif = pd.DataFrame({"dif": dif.to_numpy(dtype=float)})
    muestras = bootstrap_bloques(
        df_dif, bloque_efectivo, n_replicas, seed
    )
    medias = muestras[:, :, 0].mean(axis=1)
    frac = float(np.mean(medias > 0.0))
    ic_inf = float(np.quantile(medias, alpha / 2.0))
    ic_sup = float(np.quantile(medias, 1.0 - alpha / 2.0))

    return {
        "frac_supera_baseline": frac,
        "media_bucket": float(ret_bucket.mean()),
        "media_baseline": float(ret_baseline.mean()),
        "media_dif": float(dif.mean()),
        "ic_inferior": ic_inf,
        "ic_superior": ic_sup,
        "n_observaciones": int(n),
        "n_replicas": int(n_replicas),
        "tamano_bloque": int(bloque_efectivo),
    }


# --------------------------------------------------------------------------- #
# deflated_sharpe_ratio (Bailey & López de Prado)
# --------------------------------------------------------------------------- #


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float:
    serie = returns.dropna()
    T = len(serie)
    if T < 2:
        return float("nan")

    mu = float(serie.mean())
    sd = float(serie.std(ddof=1))
    if not np.isfinite(sd) or sd == 0.0:
        return float("nan")

    sr = mu / sd
    skew = float(serie.skew())
    kurt = float(serie.kurt()) + 3.0

    var_sr = (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2) / (T - 1)
    if not np.isfinite(var_sr) or var_sr <= 0.0:
        var_sr = 1.0 / (T - 1)
    sigma_sr = math.sqrt(var_sr)

    if n_trials is None or n_trials <= 1:
        sr0 = 0.0
    else:
        gamma = 0.5772156649015329  # constante de Euler-Mascheroni
        z1 = float(norm.ppf(1.0 - 1.0 / float(n_trials)))
        z2 = float(norm.ppf(1.0 - 1.0 / (float(n_trials) * math.e)))
        sr0 = sigma_sr * ((1.0 - gamma) * z1 + gamma * z2)

    z = (sr - sr0) / sigma_sr
    return float(norm.cdf(z))


# --------------------------------------------------------------------------- #
# probabilidad_backtest_overfitting (CSCV)
# --------------------------------------------------------------------------- #


def probabilidad_backtest_overfitting(
    matriz_desempeno: pd.DataFrame,
    n_particiones: int = 10,
) -> float:
    if n_particiones is None or n_particiones < 2 or n_particiones % 2 != 0:
        raise ValueError("n_particiones debe ser un entero par >= 2")

    T, N = matriz_desempeno.shape
    if T < n_particiones or N < 2:
        return float("nan")

    valores = matriz_desempeno.to_numpy(dtype=float)
    particiones = np.array_split(np.arange(T), n_particiones)
    mitad = n_particiones // 2
    combos = list(combinations(range(n_particiones), mitad))

    n_inferiores = 0
    n_total = 0

    for combo in combos:
        conjunto = set(combo)
        train_idx = np.concatenate([particiones[i] for i in combo])
        test_idx = np.concatenate(
            [
                particiones[i]
                for i in range(n_particiones)
                if i not in conjunto
            ]
        )
        if len(train_idx) == 0 or len(test_idx) == 0:
            continue

        train_means = valores[train_idx].mean(axis=0)
        test_means = valores[test_idx].mean(axis=0)

        mejor = int(np.argmax(train_means))
        ranks = rankdata(test_means, method="average")
        r = float(ranks[mejor])

        denom = float(N) - r + 1.0
        if r <= 0.0 or denom <= 0.0:
            continue

        logit = math.log(r / denom)
        n_total += 1
        if logit < 0.0:
            n_inferiores += 1

    if n_total == 0:
        return float("nan")
    return float(n_inferiores / n_total)


# --------------------------------------------------------------------------- #
# concentracion_maxima
# --------------------------------------------------------------------------- #


def concentracion_maxima(senales: pd.DataFrame) -> dict:
    if len(senales) == 0:
        return {"frac_max_ticker": 0.0, "ticker_max": None}

    valores = senales["ticker"].value_counts()
    max_count = int(valores.max())
    empatados = sorted(
        [str(t) for t, c in valores.items() if int(c) == max_count]
    )
    ticker_max = empatados[0] if empatados else None
    frac = float(max_count / len(senales))
    return {"frac_max_ticker": frac, "ticker_max": ticker_max}


# --------------------------------------------------------------------------- #
# leave_one_ticker_out_signo
# --------------------------------------------------------------------------- #


def leave_one_ticker_out_signo(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_10d",
) -> dict:
    if len(senales) == 0:
        return {
            "signo_original": 0,
            "revierte_con_algun_ticker": False,
            "reversiones": 0,
            "detalle": {},
        }

    serie = senales[columna_retorno]
    media_original = float(serie.mean())
    signo_original = int(np.sign(media_original))

    tickers = senales["ticker"].unique()
    reversiones = 0
    detalle: dict = {}

    for ticker in tickers:
        sub = senales[senales["ticker"] != ticker]
        if len(sub) == 0:
            detalle[str(ticker)] = 0
            continue
        signo_sub = int(np.sign(float(sub[columna_retorno].mean())))
        detalle[str(ticker)] = signo_sub
        if (
            signo_original != 0
            and signo_sub != 0
            and signo_sub != signo_original
        ):
            reversiones += 1

    return {
        "signo_original": signo_original,
        "revierte_con_algun_ticker": bool(reversiones > 0),
        "reversiones": int(reversiones),
        "detalle": detalle,
    }


# --------------------------------------------------------------------------- #
# placebo_aleatorio / percentil_real_vs_placebo
# --------------------------------------------------------------------------- #


def placebo_aleatorio(
    pool_retornos: pd.Series,
    n_senales: int,
    n_placebos: int = 1000,
    seed: int = 0,
) -> np.ndarray:
    valores = np.asarray(pool_retornos, dtype=float)
    n = len(valores)
    if n_senales <= 0:
        raise ValueError("n_senales debe ser >= 1")
    if n_senales > n:
        raise ValueError(
            f"n_senales ({n_senales}) no puede superar el tamaño del pool ({n})"
        )

    rng = np.random.default_rng(seed)
    out = np.empty(int(n_placebos), dtype=float)
    for i in range(int(n_placebos)):
        muestra = rng.choice(valores, size=n_senales, replace=False)
        out[i] = float(muestra.mean())
    return out


def percentil_real_vs_placebo(valor_real: float, placebos: np.ndarray) -> float:
    arr = np.asarray(placebos, dtype=float)
    if arr.size == 0:
        return float("nan")
    return float(np.mean(arr <= float(valor_real)))


# --------------------------------------------------------------------------- #
# etiqueta (EXP-004: multi-horizonte, 5 baselines)
# --------------------------------------------------------------------------- #


def etiqueta(
    n_horizontes_superados: int,
    mejor_frac_bootstrap: float,
    dsr: float,
    n_senales_locked: int,
    frac_max_ticker: float,
    vecino_revierte_signo: bool,
    vecino_destruye_mas_50pct: bool,
    placebo_distingue: Optional[bool],
) -> str:
    # --- Reglas de REJECTED ------------------------------------------------
    if n_horizontes_superados == 0:
        return "REJECTED"
    if _cmp_le(dsr, 0.5):
        return "REJECTED"
    if _cmp_gt(frac_max_ticker, 0.20):
        return "REJECTED"
    if placebo_distingue is not None and not bool(placebo_distingue):
        return "REJECTED"

    # --- Reglas de VALIDATED -----------------------------------------------
    if (
        _cmp_ge(n_horizontes_superados, 2)
        and _cmp_ge(mejor_frac_bootstrap, 0.80)
        and _cmp_gt(dsr, 0.95)
        and not vecino_revierte_signo
        and not vecino_destruye_mas_50pct
        and _cmp_le(frac_max_ticker, 0.20)
        and _cmp_ge(n_senales_locked, 20)
    ):
        return "VALIDATED"

    return "INCONCLUSIVE"

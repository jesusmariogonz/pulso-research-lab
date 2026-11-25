from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm


# --------------------------------------------------------------------------- #
# Bootstrap de bloques
# --------------------------------------------------------------------------- #


def bootstrap_bloques(
    retornos: pd.DataFrame,
    tamano_bloque: int,
    n_replicas: int,
    seed: int,
) -> np.ndarray:
    """Bootstrap de bloques móviles sobre las filas de ``retornos``.

    Devuelve un array de forma ``(n_replicas, n_observaciones, n_columnas)``.
    Cada réplica conserva la relación fila a fila entre columnas.
    """
    if tamano_bloque <= 0:
        raise ValueError("tamano_bloque debe ser positivo")

    arr = retornos.to_numpy(dtype=float)
    n = arr.shape[0]

    if n < tamano_bloque:
        raise ValueError("n de observaciones menor que tamano_bloque")

    n_bloques = int(math.ceil(n / tamano_bloque))
    max_start = n - tamano_bloque

    rng = np.random.default_rng(seed)
    inicios = rng.integers(
        low=0,
        high=max_start + 1,
        size=(n_replicas, n_bloques),
    )

    salida = np.empty((n_replicas, n, arr.shape[1]), dtype=float)

    for r in range(n_replicas):
        partes = [
            arr[inicio : inicio + tamano_bloque]
            for inicio in inicios[r]
        ]
        salida[r] = np.concatenate(partes, axis=0)[:n]

    return salida


def comparacion_bootstrap(
    ret_bucket: pd.Series,
    ret_baseline: pd.Series,
    tamano_bloque: int = 2,
    n_replicas: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Compara la media de ``ret_bucket`` contra ``ret_baseline`` por bootstrap.

    Requiere que ambas series compartan exactamente el mismo índice.
    """
    if not ret_bucket.index.equals(ret_baseline.index):
        raise ValueError("ret_bucket y ret_baseline deben tener el mismo índice")

    df = pd.DataFrame(
        {
            "bucket": ret_bucket.to_numpy(dtype=float),
            "baseline": ret_baseline.to_numpy(dtype=float),
        },
        index=ret_bucket.index,
    )

    muestras = bootstrap_bloques(
        df,
        tamano_bloque=tamano_bloque,
        n_replicas=n_replicas,
        seed=seed,
    )

    diferencias = muestras[:, :, 0] - muestras[:, :, 1]
    medias_diferencias = np.nanmean(diferencias, axis=1)

    if medias_diferencias.size == 0:
        frac_supera = float("nan")
        ic_inferior = float("nan")
        ic_superior = float("nan")
        media_diferencia = float("nan")
    else:
        frac_supera = float(np.mean(medias_diferencias > 0.0))
        ic_inferior = float(np.nanquantile(medias_diferencias, alpha / 2.0))
        ic_superior = float(np.nanquantile(medias_diferencias, 1.0 - alpha / 2.0))
        media_diferencia = float(np.nanmean(medias_diferencias))

    return {
        "frac_supera_baseline": frac_supera,
        "media_bucket": float(np.nanmean(ret_bucket.to_numpy(dtype=float))),
        "media_baseline": float(np.nanmean(ret_baseline.to_numpy(dtype=float))),
        "media_diferencia": media_diferencia,
        "ic_inferior": ic_inferior,
        "ic_superior": ic_superior,
        "n_replicas": int(n_replicas),
        "alpha": float(alpha),
    }


# --------------------------------------------------------------------------- #
# Deflated Sharpe Ratio
# --------------------------------------------------------------------------- #


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float:
    """Deflated Sharpe Ratio de Bailey & López de Prado."""
    r = returns.dropna().to_numpy(dtype=float)
    n = r.size

    if n < 2:
        return float("nan")

    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1))

    if sd == 0.0 or not np.isfinite(sd):
        return float("nan")

    sr = mu / sd

    serie = pd.Series(r)
    g3 = float(serie.skew())
    g4 = float(serie.kurt()) + 3.0

    var_sr = (
        1.0
        - g3 * sr
        + (g4 - 1.0) / 4.0 * sr**2
    ) / (n - 1)

    if var_sr <= 0.0 or not np.isfinite(var_sr):
        return float("nan")

    sr_std = math.sqrt(var_sr)

    if n_trials <= 1:
        return float(norm.cdf(sr / sr_std))

    euler = 0.5772156649015329
    n_trials_f = float(n_trials)

    z1 = float(norm.ppf(1.0 - 1.0 / n_trials_f))
    z2 = float(norm.ppf(1.0 - 1.0 / (n_trials_f * math.e)))

    sr0 = sr_std * ((1.0 - euler) * z1 + euler * z2)

    return float(norm.cdf((sr - sr0) / sr_std))


# --------------------------------------------------------------------------- #
# Probability of Backtest Overfitting (CSCV)
# --------------------------------------------------------------------------- #


def probabilidad_backtest_overfitting(
    matriz_desempeno: pd.DataFrame,
    n_particiones: int = 10,
) -> float:
    """CSCV de Bailey et al. (2014).

    ``matriz_desempeno`` tiene una fila por observación temporal y una
    columna por estrategia/variante.
    """
    if n_particiones < 2 or n_particiones % 2 != 0:
        raise ValueError("n_particiones debe ser par y mayor o igual que 2")

    arr = matriz_desempeno.to_numpy(dtype=float)
    n_obs, n_estrategias = arr.shape

    if n_obs < n_particiones:
        raise ValueError("n de observaciones menor que n_particiones")

    if n_estrategias < 2:
        return 0.0

    bloques = np.array_split(np.arange(n_obs), n_particiones)
    indices = list(range(n_particiones))
    mitad = n_particiones // 2

    n_overfit = 0
    n_splits = 0

    for indices_is in itertools.combinations(indices, mitad):
        indices_oos = [i for i in indices if i not in indices_is]

        idx_is = np.concatenate([bloques[i] for i in indices_is])
        idx_oos = np.concatenate([bloques[i] for i in indices_oos])

        desempeno_is = np.nanmean(arr[idx_is, :], axis=0)

        if np.all(np.isnan(desempeno_is)):
            continue

        mejor_is = int(np.nanargmax(desempeno_is))

        desempeno_oos = np.nanmean(arr[idx_oos, :], axis=0)
        ranks_oos = (
            pd.Series(desempeno_oos)
            .rank(method="average", ascending=False)
            .to_numpy()
        )

        rank_mejor = ranks_oos[mejor_is]

        # rank 1 = mejor. El ganador IS es overfit si queda en la mitad
        # inferior (o peor) del ranking OOS.
        if rank_mejor >= (n_estrategias + 1) / 2.0:
            n_overfit += 1

        n_splits += 1

    if n_splits == 0:
        return 0.0

    return float(n_overfit / n_splits)


# --------------------------------------------------------------------------- #
# Concentración y robustez por ticker
# --------------------------------------------------------------------------- #


def concentracion_maxima(senales: pd.DataFrame) -> dict[str, Any]:
    """Fracción de señales del ticker más frecuente."""
    if senales is None or len(senales) == 0:
        return {"frac_max_ticker": 0.0, "ticker_max": None}

    tickers = senales["ticker"].dropna()
    if len(tickers) == 0:
        return {"frac_max_ticker": 0.0, "ticker_max": None}

    conteos = tickers.value_counts()
    max_conteo = int(conteos.max())

    candidatos = conteos[conteos == max_conteo].index.tolist()
    ticker_max = sorted(candidatos, key=lambda x: str(x))[0]

    return {
        "frac_max_ticker": float(max_conteo / len(senales)),
        "ticker_max": ticker_max,
    }


def _signo(valor: float) -> int:
    if valor > 0:
        return 1
    if valor < 0:
        return -1
    return 0


def leave_one_ticker_out_signo(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_10d",
) -> dict[str, Any]:
    """Reversión del signo de la media al excluir cada ticker."""
    if senales is None or len(senales) == 0:
        return {
            "signo_original": 0,
            "revierte_con_algun_ticker": False,
            "reversiones": 0,
            "detalle": {},
        }

    media_original = float(senales[columna_retorno].mean())
    signo_original = _signo(media_original)

    detalle: dict[str, Any] = {}
    reversiones = 0

    for ticker in senales["ticker"].dropna().unique():
        resto = senales[senales["ticker"] != ticker]
        if len(resto) == 0:
            continue

        media_resto = float(resto[columna_retorno].mean())
        signo_resto = _signo(media_resto)

        revierte = (
            signo_original != 0
            and signo_resto != 0
            and signo_resto != signo_original
        )

        if revierte:
            reversiones += 1

        detalle[str(ticker)] = {
            "media_sin_ticker": media_resto,
            "signo_sin_ticker": signo_resto,
            "revierte": bool(revierte),
        }

    return {
        "signo_original": signo_original,
        "revierte_con_algun_ticker": bool(reversiones > 0),
        "reversiones": int(reversiones),
        "detalle": detalle,
    }


# --------------------------------------------------------------------------- #
# Placebo
# --------------------------------------------------------------------------- #


def placebo_aleatorio(
    pool_retornos: pd.Series,
    n_senales: int,
    n_placebos: int = 1000,
    seed: int = 0,
) -> np.ndarray:
    """Genera medias de señales placebo muestreadas sin reemplazo del pool."""
    if n_senales <= 0:
        raise ValueError("n_senales debe ser positivo")

    pool = pool_retornos.dropna().to_numpy(dtype=float)

    if len(pool) < n_senales:
        raise ValueError("n_senales mayor que el tamaño del pool")

    if n_placebos <= 0:
        return np.empty(0, dtype=float)

    rng = np.random.default_rng(seed)
    salida = np.empty(n_placebos, dtype=float)

    for i in range(n_placebos):
        muestra = rng.choice(pool, size=n_senales, replace=False)
        salida[i] = float(np.mean(muestra))

    return salida


def percentil_real_vs_placebo(valor_real: float, placebos: np.ndarray) -> float:
    """Percentil del valor real dentro de la distribución placebo."""
    arr = np.asarray(placebos, dtype=float)
    if arr.size == 0:
        return float("nan")
    return float(np.mean(arr <= valor_real))


# --------------------------------------------------------------------------- #
# Etiqueta final
# --------------------------------------------------------------------------- #


def _le(a: Any, b: Any) -> bool:
    try:
        return bool(a <= b)
    except (TypeError, ValueError):
        return False


def _gt(a: Any, b: Any) -> bool:
    try:
        return bool(a > b)
    except (TypeError, ValueError):
        return False


def _ge(a: Any, b: Any) -> bool:
    try:
        return bool(a >= b)
    except (TypeError, ValueError):
        return False


def etiqueta(
    n_horizontes_superados: int,
    mejor_frac_bootstrap: float,
    dsr: float,
    n_senales_locked: int,
    frac_max_ticker: float,
    vecino_revierte_signo: bool,
    vecino_destruye_mas_50pct: bool,
    placebo_distingue: bool | None,
) -> str:
    """Etiqueta final de EXP-004."""
    # 1) Rechazo.
    if (
        n_horizontes_superados == 0
        or _le(dsr, 0.5)
        or _gt(frac_max_ticker, 0.20)
        or placebo_distingue is False
    ):
        return "REJECTED"

    # 2) Validación.
    if (
        _ge(n_horizontes_superados, 2)
        and _ge(mejor_frac_bootstrap, 0.80)
        and _gt(dsr, 0.95)
        and not bool(vecino_revierte_signo)
        and not bool(vecino_destruye_mas_50pct)
        and _le(frac_max_ticker, 0.20)
        and _ge(n_senales_locked, 20)
    ):
        return "VALIDATED"

    # 3) Resto.
    return "INCONCLUSIVE"

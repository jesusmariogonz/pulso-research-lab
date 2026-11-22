from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
from scipy.stats import norm


def bootstrap_bloques(
    retornos: pd.DataFrame,
    tamano_bloque: int,
    n_replicas: int,
    seed: int,
) -> np.ndarray:
    """Bootstrap de bloques pareado entre columnas de un DataFrame."""
    if tamano_bloque <= 0:
        raise ValueError("tamano_bloque debe ser positivo")

    valores = retornos.to_numpy()
    n, n_columnas = valores.shape

    if n < tamano_bloque:
        raise ValueError("n debe ser mayor o igual que tamano_bloque")

    n_bloques = int(math.ceil(n / tamano_bloque))
    rng = np.random.default_rng(seed)
    max_inicio = n - tamano_bloque

    salida = np.empty((n_replicas, n, n_columnas), dtype=valores.dtype)
    for replica in range(n_replicas):
        inicios = rng.integers(0, max_inicio + 1, size=n_bloques)
        filas = np.concatenate(
            [np.arange(inicio, inicio + tamano_bloque) for inicio in inicios]
        )[:n]
        salida[replica] = valores[filas]

    return salida


def comparacion_bootstrap(
    ret_bucket: pd.Series,
    ret_baseline: pd.Series,
    tamano_bloque: int = 2,
    n_replicas: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict:
    """Compara un bucket contra un baseline mediante bootstrap de bloques."""
    if not ret_bucket.index.equals(ret_baseline.index):
        raise ValueError("ret_bucket y ret_baseline deben compartir el mismo índice")

    datos = pd.DataFrame(
        {
            "bucket": ret_bucket.to_numpy(),
            "baseline": ret_baseline.to_numpy(),
        }
    )
    replicas = bootstrap_bloques(
        datos,
        tamano_bloque=tamano_bloque,
        n_replicas=n_replicas,
        seed=seed,
    )

    if n_replicas == 0:
        return {
            "ci_media_bucket": (float("nan"), float("nan")),
            "frac_supera_baseline": 0.0,
        }

    medias = replicas.mean(axis=1)
    media_bucket = medias[:, 0]
    media_baseline = medias[:, 1]

    ci = np.quantile(media_bucket, [alpha / 2.0, 1.0 - alpha / 2.0])
    frac = float(np.mean(media_bucket > media_baseline))

    return {
        "ci_media_bucket": (float(ci[0]), float(ci[1])),
        "frac_supera_baseline": frac,
    }


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float:
    """Calcula el Deflated Sharpe Ratio de una serie de retornos."""
    n = len(returns)

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
        n_trials_float = float(n_trials)
        sr0 = sr_std * (
            (1.0 - gamma) * float(norm.ppf(1.0 - 1.0 / n_trials_float))
            + gamma * float(norm.ppf(1.0 - 1.0 / (n_trials_float * math.e)))
        )

    return float(norm.cdf((sr - sr0) / sr_std))


def probabilidad_backtest_overfitting(
    matriz_desempeno: pd.DataFrame,
    n_particiones: int = 10,
) -> float:
    """Calcula el PBO mediante CSCV determinista."""
    if n_particiones < 2 or n_particiones % 2 != 0:
        raise ValueError("n_particiones debe ser par y mayor o igual que 2")

    n = len(matriz_desempeno)
    if n < n_particiones:
        raise ValueError("matriz_desempeno debe tener al menos n_particiones filas")

    df = matriz_desempeno.loc[:, sorted(matriz_desempeno.columns)]
    n_variantes = df.shape[1]
    if n_variantes == 0:
        raise ValueError("matriz_desempeno debe tener al menos una columna")

    tam = n // n_particiones
    bloques = [
        np.arange(i * tam, (i + 1) * tam) for i in range(n_particiones)
    ]

    epsilon = 1.0 / (2.0 * n_variantes)
    sobreajuste = 0
    n_combinaciones = 0

    for seleccion in itertools.combinations(
        range(n_particiones), n_particiones // 2
    ):
        filas_is = np.concatenate([bloques[i] for i in seleccion])
        filas_oos = np.concatenate(
            [bloques[i] for i in range(n_particiones) if i not in seleccion]
        )

        desempeno_is = df.iloc[filas_is].mean(axis=0)
        variante_elegida = desempeno_is.idxmax()

        desempeno_oos = df.iloc[filas_oos].mean(axis=0)
        rho = float(desempeno_oos.rank(pct=True).loc[variante_elegida])
        rho = min(max(rho, epsilon), 1.0 - epsilon)

        logit = math.log(rho / (1.0 - rho))
        if logit <= 0.0:
            sobreajuste += 1

        n_combinaciones += 1

    return float(sobreajuste / n_combinaciones)


def concentracion_maxima(senales: pd.DataFrame) -> dict:
    """Devuelve la concentración del ticker más frecuente en las señales."""
    if senales.empty:
        return {"frac_max_ticker": 0.0, "ticker_max": None}

    conteos = senales["ticker"].value_counts()
    maximo = int(conteos.max())
    candidatos = conteos[conteos == maximo].index
    ticker_max = min(candidatos)

    return {
        "frac_max_ticker": float(maximo / len(senales)),
        "ticker_max": str(ticker_max),
    }


def _signo(valor: float) -> int:
    if valor > 0:
        return 1
    if valor < 0:
        return -1
    return 0


def leave_one_ticker_out_signo(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_30d",
) -> dict:
    """Evalúa si el signo del retorno medio revierte al excluir un ticker."""
    signo_original = _signo(float(senales[columna_retorno].mean()))
    tickers = list(senales["ticker"].unique())

    reversiones = 0
    for ticker in tickers:
        retornos_sin_ticker = senales.loc[
            senales["ticker"] != ticker, columna_retorno
        ]
        signo_sin_ticker = _signo(float(retornos_sin_ticker.mean()))

        if (
            signo_original != 0
            and signo_sin_ticker != 0
            and signo_sin_ticker == -signo_original
        ):
            reversiones += 1

    return {
        "signo_original": int(signo_original),
        "n_tickers": int(len(tickers)),
        "reversiones": int(reversiones),
        "revierte_con_algun_ticker": bool(reversiones > 0),
    }


def placebo_aleatorio(
    pool_retornos: pd.Series,
    n_senales: int,
    n_placebos: int = 1000,
    seed: int = 0,
) -> np.ndarray:
    """Genera medias placebo muestreando señales sin reemplazo del pool."""
    if n_senales <= 0:
        raise ValueError("n_senales debe ser positivo")
    if n_senales > len(pool_retornos):
        raise ValueError("n_senales no puede superar el tamaño del pool")

    rng = np.random.default_rng(seed)
    valores = pool_retornos.to_numpy()
    salida = np.empty(n_placebos, dtype=float)

    for i in range(n_placebos):
        muestra = rng.choice(valores, size=n_senales, replace=False)
        salida[i] = float(np.mean(muestra))

    return salida


def percentil_real_vs_placebo(
    valor_real: float,
    placebos: np.ndarray,
) -> float:
    """Fracción de placebos menores o iguales al valor real."""
    placebos_arr = np.asarray(placebos)
    if placebos_arr.size == 0:
        return 0.0
    return float(np.mean(placebos_arr <= valor_real))


def etiqueta(
    supera_los_4_baselines: bool,
    frac_bootstrap_vs_baseline1: float,
    dsr: float,
    n_senales_locked: int,
    frac_max_ticker: float,
    vecino_revierte_signo: bool,
    vecino_destruye_mas_50pct: bool,
    placebo_distingue: bool | None,
) -> str:
    """Aplica el orden de prioridad de los criterios de éxito del pre-registro."""
    if (
        frac_bootstrap_vs_baseline1 <= 0.5
        or dsr <= 0.5
        or frac_max_ticker > 0.20
        or placebo_distingue is False
    ):
        return "REJECTED"

    if (
        bool(supera_los_4_baselines)
        and frac_bootstrap_vs_baseline1 >= 0.80
        and dsr > 0.95
        and not vecino_revierte_signo
        and not vecino_destruye_mas_50pct
        and frac_max_ticker <= 0.20
        and n_senales_locked >= 20
    ):
        return "VALIDATED"

    return "INCONCLUSIVE"

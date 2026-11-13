"""Evaluación estadística para EXP-002 (growth max).

Implementa la sección *Validación* y el *Criterio de selección* del
pre-registro, con la aclaración de implementación v1.4.

Reglas: solo pandas / numpy / scipy / typing. Sin red, sin archivos, sin
variables de entorno. Funciones puras. No importa otros módulos de
`prl.growth_max` ni `prl.emergency` (las fórmulas compartidas se
reimplementan aquí).
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm


# ---------------------------------------------------------------------------
# Métricas básicas
# ---------------------------------------------------------------------------


def tasa_crecimiento_geometrica(retornos: pd.Series) -> float:
    """CAGR anualizado: ``equity_final ** (365.25 / dias_calendario) - 1``.

    Devuelve ``NaN`` si no hay días de calendario entre extremos o si la
    base no es positiva (evita ``inf``/complejos en silencio).
    """
    if len(retornos) == 0:
        return float("nan")
    equity = (1.0 + retornos.astype(float)).cumprod()
    equity_final = float(equity.iloc[-1])
    dias_calendario = (retornos.index[-1] - retornos.index[0]).days
    if dias_calendario == 0 or equity_final <= 0.0:
        return float("nan")
    return float(equity_final ** (365.25 / dias_calendario) - 1.0)


# ---------------------------------------------------------------------------
# Block bootstrap pareado
# ---------------------------------------------------------------------------


def posiciones_bootstrap_bloques(
    n: int, tamano_bloque: int, n_replicas: int, seed: int
) -> np.ndarray:
    """Matriz de posiciones ``(n_replicas, n)`` para un block bootstrap.

    Misma regla que ``bootstrap_bloques_retornos``: en cada réplica se
    concatenan ``ceil(n / tamano_bloque)`` bloques de ``tamano_bloque``
    filas consecutivas (inicio uniforme en ``[0, n - tamano_bloque]``),
    recortando a ``n``. Depende solo de ``(n, tamano_bloque, n_replicas,
    seed)``: reutilizable para remuestrear varias series con esas mismas
    dimensiones sin volver a generar números aleatorios.

    Lanza ``ValueError`` si ``n < tamano_bloque``.
    """
    if n < tamano_bloque:
        raise ValueError(
            f"n ({n}) < tamaño de bloque ({tamano_bloque}): imposible remuestrear"
        )
    rng = np.random.default_rng(seed)
    n_bloques = int(math.ceil(n / tamano_bloque))
    max_start = n - tamano_bloque

    # Mismo orden de extracción del RNG que la versión por-réplica/por-bloque
    # (réplica-mayor, bloque-menor), pero vectorizado: sin loops de Python.
    starts = rng.integers(0, max_start + 1, size=(n_replicas, n_bloques))
    offsets = np.arange(tamano_bloque)
    pos = (starts[:, :, None] + offsets[None, None, :]).reshape(n_replicas, n_bloques * tamano_bloque)
    return pos[:, :n]


def bootstrap_bloques_retornos(
    retornos: pd.DataFrame,
    tamano_bloque: int,
    n_replicas: int,
    seed: int,
) -> np.ndarray:
    """Block bootstrap pareado de las columnas de ``retornos``.

    La **misma** selección de bloques se aplica a todas las columnas
    (bootstrap pareado). Devuelve un arreglo ``(n_replicas, n, n_columnas)``.

    Lanza ``ValueError`` si ``n < tamano_bloque``.
    """
    pos = posiciones_bootstrap_bloques(len(retornos), tamano_bloque, n_replicas, seed)
    return retornos.to_numpy()[pos]


def _max_drawdowns_por_replica(valores: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """Máximo drawdown (negativo) de cada réplica, dado un vector 1D y posiciones."""
    rep = valores[pos]
    equity = np.cumprod(1.0 + rep, axis=1)
    picos = np.maximum.accumulate(equity, axis=1)
    dd = equity / picos - 1.0
    return dd.min(axis=1)


def probabilidades_perdida_con_posiciones(
    valores: np.ndarray, pos: np.ndarray, umbrales: Sequence[float]
) -> dict[float, float]:
    """Como ``probabilidad_perdida``, para varios umbrales a la vez.

    Reutiliza una matriz ``pos`` ya calculada con ``posiciones_bootstrap_bloques``
    (misma ``n``, mismo ``seed``) en vez de volver a generarla: pensada para
    evaluar muchas series distintas (p. ej. variantes de un grid) con el
    mismo tamaño de ventana y la misma semilla sin repetir el muestreo.
    """
    max_dd = _max_drawdowns_por_replica(np.asarray(valores, dtype=float), pos)
    abs_dd = np.abs(max_dd)
    n_replicas = pos.shape[0]
    return {float(u): float(np.sum(abs_dd >= u)) / n_replicas for u in umbrales}


def probabilidades_perdida(
    retornos: pd.Series,
    umbrales: Sequence[float],
    tamano_bloque: int = 20,
    n_replicas: int = 10000,
    seed: int = 0,
) -> dict[float, float]:
    """Como ``probabilidad_perdida``, para varios umbrales con un solo bootstrap."""
    pos = posiciones_bootstrap_bloques(len(retornos), tamano_bloque, n_replicas, seed)
    return probabilidades_perdida_con_posiciones(retornos.to_numpy(), pos, umbrales)


def probabilidad_perdida(
    retornos: pd.Series,
    umbral: float,
    tamano_bloque: int = 20,
    n_replicas: int = 10000,
    seed: int = 0,
) -> float:
    """Fracción de réplicas de bootstrap con max-drawdown ``|dd| >= umbral``."""
    return probabilidades_perdida(retornos, [umbral], tamano_bloque, n_replicas, seed)[
        float(umbral)
    ]


def comparacion_bootstrap(
    ret_modelo: pd.Series,
    ret_benchmark: pd.Series,
    tamano_bloque: int = 20,
    n_replicas: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict:
    """Compara CAGR de modelo vs benchmark vía bootstrap pareado.

    Devuelve ``{"ci_cagr_modelo": (lo, hi), "frac_supera_benchmark": float}``.
    """
    idx = ret_modelo.index
    df = pd.DataFrame(
        {"modelo": ret_modelo.to_numpy(), "benchmark": ret_benchmark.to_numpy()},
        index=idx,
    )
    boot = bootstrap_bloques_retornos(df, tamano_bloque, n_replicas, seed)

    cagr_modelo = np.empty(n_replicas, dtype=float)
    cagr_bench = np.empty(n_replicas, dtype=float)
    for r in range(n_replicas):
        cagr_modelo[r] = tasa_crecimiento_geometrica(
            pd.Series(boot[r, :, 0], index=idx)
        )
        cagr_bench[r] = tasa_crecimiento_geometrica(
            pd.Series(boot[r, :, 1], index=idx)
        )

    lo = float(np.percentile(cagr_modelo, (alpha / 2.0) * 100.0))
    hi = float(np.percentile(cagr_modelo, (1.0 - alpha / 2.0) * 100.0))
    frac = float(np.mean(cagr_modelo > cagr_bench))
    return {"ci_cagr_modelo": (lo, hi), "frac_supera_benchmark": frac}


# ---------------------------------------------------------------------------
# Deflated Sharpe Ratio
# ---------------------------------------------------------------------------


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado), fórmula de EXP-001.

    Sharpe diario sin anualizar; corrige por asimetría, curtosis y número
    de intentos ``n_trials``.
    """
    x = returns.to_numpy(dtype=float)
    n = len(x)
    mu = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    sr = mu / sd
    g3 = float(returns.skew())
    g4 = float(returns.kurt()) + 3.0
    sr_std = math.sqrt((1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr ** 2) / (n - 1))

    if n_trials <= 1:
        sr0 = 0.0
    else:
        N = float(n_trials)
        gamma = 0.5772156649015329
        sr0 = sr_std * (
            (1.0 - gamma) * float(norm.ppf(1.0 - 1.0 / N))
            + gamma * float(norm.ppf(1.0 - 1.0 / (N * math.e)))
        )
    return float(norm.cdf((sr - sr0) / sr_std))


# ---------------------------------------------------------------------------
# Selección de variante
# ---------------------------------------------------------------------------


def _mejor(candidatos: Sequence[str], log_wealth: Mapping[str, float]) -> str | None:
    """Devuelve la variante con mayor log-wealth; empate → primera en orden."""
    mejor: str | None = None
    mejor_val = -math.inf
    for v in candidatos:
        val = log_wealth[v]
        if val > mejor_val:
            mejor_val = val
            mejor = v
    return mejor


def elegir_variante(
    log_wealth_validation: dict[str, float],
    prob_perdida_50: dict[str, float],
    prob_perdida_75: dict[str, float],
) -> tuple[str | None, str]:
    """Aplica el criterio de selección con filtros de ruina 50 % / 75 %."""
    cands_50 = [v for v in log_wealth_validation if prob_perdida_50[v] < 0.20]
    if cands_50:
        return _mejor(cands_50, log_wealth_validation), "filtro_50"

    cands_75 = [v for v in log_wealth_validation if prob_perdida_75[v] < 0.20]
    if cands_75:
        return _mejor(cands_75, log_wealth_validation), "filtro_75_relajado"

    return None, "ninguna_variante_pasa_el_filtro_de_ruina"


# ---------------------------------------------------------------------------
# Placebo circular
# ---------------------------------------------------------------------------


def placebo_circular(
    retornos: pd.Series,
    n_placebos: int = 1000,
    seed: int = 0,
) -> np.ndarray:
    """Placebo por desplazamiento circular uniforme en ``[1, n-1]``.

    Devuelve un arreglo ``(n_placebos,)`` de tasas de crecimiento
    geométrico. Lanza ``ValueError`` si ``len(retornos) < 2``.
    """
    n = len(retornos)
    if n < 2:
        raise ValueError("se requieren al menos 2 observaciones para el placebo")
    rng = np.random.default_rng(seed)
    arr = retornos.to_numpy()
    idx = retornos.index
    out = np.empty(n_placebos, dtype=float)
    for i in range(n_placebos):
        shift = int(rng.integers(1, n))  # [1, n-1], nunca 0
        rolled = np.roll(arr, shift)
        out[i] = tasa_crecimiento_geometrica(pd.Series(rolled, index=idx))
    return out


def percentil_real_vs_placebo(valor_real: float, placebos: np.ndarray) -> float:
    """Fracción de ``placebos`` que son ``<= valor_real`` (incluye empates)."""
    arr = np.asarray(placebos, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr <= valor_real))


# ---------------------------------------------------------------------------
# Etiqueta final (aclaración v1.4)
# ---------------------------------------------------------------------------


def etiqueta(
    ci_cagr_modelo: tuple[float, float],
    frac_supera_benchmark: float,
    prob_ruina_75: float,
    n_dias_locked_test: int,
) -> str:
    """Clasifica el resultado siguiendo el orden de prioridad de v1.4.

    Un ``NaN`` en cualquier argumento numérico hace que la comparación
    correspondiente no se cumpla (ni ``REJECTED`` ni ``VALIDATED`` por esa
    condición), cayendo hacia ``INCONCLUSIVE`` si ninguna otra aplica.
    """
    if n_dias_locked_test < 756:
        return "INCONCLUSIVE"
    if frac_supera_benchmark <= 0.50 or prob_ruina_75 > 0.20:
        return "REJECTED"
    if ci_cagr_modelo[0] > 0.0 and frac_supera_benchmark >= 0.80:
        return "VALIDATED"
    return "INCONCLUSIVE"

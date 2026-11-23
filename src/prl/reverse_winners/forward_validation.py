"""EXP-005 — Forward validation.

Métricas y desgloses de la sección 3 de ``FORWARD_VALIDATION.md``.

Funciones puras sobre ``pandas``/``numpy``. La convención de entrada ``senales``
es un ``DataFrame`` con una fila por señal (fecha×ticker elegida por el bucket),
columnas mínimas ``["fecha", "ticker", "retorno_30d"]``.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Serie por fecha de corte
# --------------------------------------------------------------------------- #


def serie_por_fecha(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_30d",
) -> pd.Series:
    """Media de ``columna_retorno`` por fecha, ordenada cronológicamente."""
    if senales.empty:
        return pd.Series(dtype=float)
    serie = senales.groupby("fecha")[columna_retorno].mean()
    return serie.sort_index().astype(float)


# --------------------------------------------------------------------------- #
# Métricas sobre una serie por fecha
# --------------------------------------------------------------------------- #


def retorno_acumulado(serie: pd.Series) -> float:
    """Producto compuesto de ``(1 + r)``.

    Compone los retornos de fechas de corte consecutivas como si fueran
    periodos secuenciales (las ventanas de 30 días se solapan con paso de 10
    sesiones: limitación declarada de autocorrelación serial, no corregida
    aquí).
    """
    if len(serie) == 0:
        return float("nan")
    return float((1.0 + serie).prod() - 1.0)


def volatilidad(serie: pd.Series) -> float:
    """Desvío estándar muestral (``ddof=1``); ``NaN`` si hay menos de 2 datos."""
    if len(serie) < 2:
        return float("nan")
    return float(serie.std(ddof=1))


def sharpe(serie: pd.Series, periodos_por_anio: float = 25.2) -> float:
    """Sharpe anualizado de la serie de retornos por fecha de corte."""
    if len(serie) < 2:
        return float("nan")
    std = serie.std(ddof=1)
    if pd.isna(std) or std == 0:
        return float("nan")
    return float(serie.mean() / std * math.sqrt(periodos_por_anio))


def max_drawdown(serie: pd.Series) -> float:
    """Máxima caída sobre la curva de equity compuesta."""
    if len(serie) == 0:
        return float("nan")
    equity = (1.0 + serie).cumprod()
    drawdown = (equity / equity.cummax() - 1.0).min()
    return float(drawdown)


# --------------------------------------------------------------------------- #
# Métricas sobre señales individuales
# --------------------------------------------------------------------------- #


def hit_rate(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_30d",
) -> float:
    """Fracción de señales con retorno no negativo (sobre las no-``NaN``)."""
    valores = senales[columna_retorno].dropna()
    if len(valores) == 0:
        return float("nan")
    return float((valores >= 0).mean())


def turnover_por_fecha(
    composiciones: dict[pd.Timestamp, set[str]],
) -> pd.Series:
    """Turnover por fecha a partir de la segunda composición.

    Para cada fecha ``t`` (desde la segunda): nombres nuevos respecto de la
    composición anterior, sobre el tamaño anterior. La primera fecha no
    aparece en el resultado. ``NaN`` si la composición anterior está vacía.
    """
    fechas = list(composiciones.keys())
    valores: dict[pd.Timestamp, float] = {}
    for i in range(1, len(fechas)):
        previos = composiciones[fechas[i - 1]]
        actuales = composiciones[fechas[i]]
        if len(previos) == 0:
            valores[fechas[i]] = float("nan")
        else:
            entradas = actuales.difference(previos)
            valores[fechas[i]] = len(entradas) / len(previos)
    return pd.Series(valores, dtype=float)


def concentracion_del_efecto(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_30d",
    top_n: int = 5,
) -> dict:
    """Mide si el resultado positivo depende de un puñado de señales extremas."""
    media_total = senales[columna_retorno].mean()

    if len(senales) <= top_n:
        return {
            "media_total": float(media_total),
            "media_sin_top_n": float("nan"),
            "depende_de_pocas_senales": False,
        }

    indices_top = senales.nlargest(top_n, columna_retorno).index
    resto = senales.drop(index=indices_top)
    media_sin_top_n = resto[columna_retorno].mean()

    depende = bool(media_sin_top_n <= 0 and media_total > 0)
    return {
        "media_total": float(media_total),
        "media_sin_top_n": float(media_sin_top_n),
        "depende_de_pocas_senales": depende,
    }


# --------------------------------------------------------------------------- #
# Comparación contra benchmark
# --------------------------------------------------------------------------- #


def exceso_vs_benchmark(
    serie_bucket: pd.Series,
    serie_benchmark: pd.Series,
) -> pd.Series:
    """Exceso por fecha: resta alineada por índice (``NaN`` donde falta un lado)."""
    return serie_bucket.sub(serie_benchmark)


# --------------------------------------------------------------------------- #
# Desgloses
# --------------------------------------------------------------------------- #

_COLUMNAS_DESGLOSE = ["media", "mediana", "hit_rate", "n"]


def _fila_desglose(grupo: pd.DataFrame, columna_retorno: str) -> dict:
    valores = grupo[columna_retorno]
    return {
        "media": float(valores.mean()),
        "mediana": float(valores.median()),
        "hit_rate": hit_rate(grupo, columna_retorno),
        "n": int(len(grupo)),
    }


def _fila_desglose_vacia() -> dict:
    return {
        "media": float("nan"),
        "mediana": float("nan"),
        "hit_rate": float("nan"),
        "n": 0,
    }


def desglose_por_periodo(
    senales: pd.DataFrame,
    columna_fecha: str = "fecha",
    columna_retorno: str = "retorno_30d",
    frecuencia: str = "Q",
) -> pd.DataFrame:
    """Desglose por periodo calendario (``frecuencia`` es alias de ``Period``)."""
    if len(senales) == 0:
        return pd.DataFrame(columns=_COLUMNAS_DESGLOSE)

    periodos = pd.PeriodIndex(senales[columna_fecha], freq=frecuencia)

    filas: list[tuple[pd.Period, dict]] = []
    for periodo, grupo in senales.groupby(periodos):
        filas.append((periodo, _fila_desglose(grupo, columna_retorno)))

    filas.sort(key=lambda par: par[0])
    indice = [str(periodo) for periodo, _ in filas]
    return pd.DataFrame(
        [fila for _, fila in filas],
        index=indice,
        columns=_COLUMNAS_DESGLOSE,
    )


def desglose_por_regimen_vix(
    senales: pd.DataFrame,
    vix_por_fecha: pd.Series,
    columna_fecha: str = "fecha",
    columna_retorno: str = "retorno_30d",
) -> pd.DataFrame:
    """Desglose por tercil de VIX calculado sobre las fechas presentes en señales."""
    orden = ["bajo", "medio", "alto", "sin_dato"]

    fechas_unicas = pd.Index(senales[columna_fecha].unique())
    vix_valores = vix_por_fecha.reindex(fechas_unicas)
    percentil = vix_valores.rank(pct=True)

    etiqueta_por_fecha = pd.Series("sin_dato", index=vix_valores.index, dtype=object)
    tiene_dato = vix_valores.notna()
    etiqueta_por_fecha[tiene_dato & (percentil < 1.0 / 3.0)] = "bajo"
    etiqueta_por_fecha[tiene_dato & (percentil >= 1.0 / 3.0) & (percentil < 2.0 / 3.0)] = "medio"
    etiqueta_por_fecha[tiene_dato & (percentil >= 2.0 / 3.0)] = "alto"

    etiquetas_senal = senales[columna_fecha].map(etiqueta_por_fecha)

    filas: dict[str, dict] = {}
    for regimen in orden:
        subconjunto = senales[etiquetas_senal == regimen]
        if len(subconjunto) == 0:
            filas[regimen] = _fila_desglose_vacia()
        else:
            filas[regimen] = _fila_desglose(subconjunto, columna_retorno)

    return pd.DataFrame.from_dict(filas, orient="index")[_COLUMNAS_DESGLOSE]


def desglose_por_volatilidad(
    senales: pd.DataFrame,
    columna_vol: str = "vol_realizada_20d_cruda",
    columna_retorno: str = "retorno_30d",
) -> pd.DataFrame:
    """Desglose por tercil de volatilidad cruda (filas ``NaN`` excluidas)."""
    orden = ["bajo", "medio", "alto"]

    subconjunto = senales[senales[columna_vol].notna()]
    percentil = subconjunto[columna_vol].rank(pct=True)

    etiquetas = pd.Series(index=subconjunto.index, dtype=object)
    etiquetas[percentil < 1.0 / 3.0] = "bajo"
    etiquetas[(percentil >= 1.0 / 3.0) & (percentil < 2.0 / 3.0)] = "medio"
    etiquetas[percentil >= 2.0 / 3.0] = "alto"

    filas: dict[str, dict] = {}
    for regimen in orden:
        sub = subconjunto[etiquetas == regimen]
        if len(sub) == 0:
            filas[regimen] = _fila_desglose_vacia()
        else:
            filas[regimen] = _fila_desglose(sub, columna_retorno)

    return pd.DataFrame.from_dict(filas, orient="index")[_COLUMNAS_DESGLOSE]


# --------------------------------------------------------------------------- #
# Etiqueta final
# --------------------------------------------------------------------------- #


def etiqueta_forward(
    n_fechas_acumuladas: int,
    supera_los_5_benchmarks: bool,
    depende_de_pocas_senales: bool,
) -> str:
    """Etiqueta final fijada en ``FORWARD_VALIDATION.md`` (prioridad fija)."""
    if n_fechas_acumuladas < 10:
        return "inconclusa"
    if not supera_los_5_benchmarks:
        return "negativa"
    if depende_de_pocas_senales:
        return "inconclusa"
    return "favorable"

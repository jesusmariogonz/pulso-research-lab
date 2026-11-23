from __future__ import annotations

import math
from typing import Any

import pandas as pd


_COLUMNAS_DESGLOSE = ["media", "mediana", "hit_rate", "n"]


def serie_por_fecha(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_30d",
) -> pd.Series:
    """Media del retorno por fecha de corte, ordenada cronológicamente."""
    if senales.empty:
        return pd.Series(dtype=float)
    return senales.groupby("fecha")[columna_retorno].mean().sort_index()


def retorno_acumulado(serie: pd.Series) -> float:
    """Retorno compuesto de una serie de retornos por fecha de corte."""
    if len(serie) == 0:
        return float("nan")
    return float((1.0 + serie).prod() - 1.0)


def volatilidad(serie: pd.Series) -> float:
    """Desviación estándar muestral de la serie por fecha."""
    if len(serie) < 2:
        return float("nan")
    return float(serie.std(ddof=1))


def sharpe(serie: pd.Series, periodos_por_anio: float = 25.2) -> float:
    """Sharpe anualizado de la serie por fecha de corte."""
    if len(serie) < 2:
        return float("nan")

    desvio = float(serie.std(ddof=1))
    if math.isnan(desvio) or desvio == 0.0:
        return float("nan")

    return float(serie.mean() / desvio * math.sqrt(periodos_por_anio))


def max_drawdown(serie: pd.Series) -> float:
    """Máximo drawdown sobre la curva de equity compuesta."""
    if len(serie) == 0:
        return float("nan")

    equity = (1.0 + serie).cumprod()
    return float((equity / equity.cummax() - 1.0).min())


def hit_rate(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_30d",
) -> float:
    """Fracción de señales con retorno estrictamente positivo."""
    validos = senales[columna_retorno].dropna()
    if len(validos) == 0:
        return float("nan")
    return float((validos > 0).sum() / len(validos))


def turnover_por_fecha(
    composiciones: dict[pd.Timestamp, set[str]],
) -> pd.Series:
    """Turnover entre composiciones consecutivas.

    Se calcula como la mayor cantidad de nombres entrados o salidos respecto
    del tamaño de la composición anterior. La primera fecha no tiene valor.
    """
    items = list(composiciones.items())
    if len(items) < 2:
        return pd.Series(dtype=float)

    fechas: list[pd.Timestamp] = []
    valores: list[float] = []

    for (_, anteriores), (fecha_actual, actuales) in zip(items[:-1], items[1:]):
        fechas.append(fecha_actual)
        if len(anteriores) == 0:
            valores.append(float("nan"))
            continue

        entradas = len(actuales.difference(anteriores))
        salidas = len(anteriores.difference(actuales))
        valores.append(max(entradas, salidas) / len(anteriores))

    return pd.Series(valores, index=pd.Index(fechas), dtype=float)


def concentracion_del_efecto(
    senales: pd.DataFrame,
    columna_retorno: str = "retorno_30d",
    top_n: int = 5,
) -> dict[str, Any]:
    """Mide si el resultado agregado depende de pocas señales extremas."""
    valores = senales[columna_retorno].dropna()
    media_total = float(valores.mean()) if len(valores) > 0 else float("nan")

    if len(senales) <= top_n:
        return {
            "media_total": media_total,
            "media_sin_top_n": float("nan"),
            "depende_de_pocas_senales": False,
        }

    top = senales.nlargest(top_n, columna_retorno)
    restantes = senales.drop(index=top.index)[columna_retorno].dropna()
    media_sin_top_n = (
        float(restantes.mean()) if len(restantes) > 0 else float("nan")
    )

    depende = bool(media_sin_top_n <= 0.0 and media_total > 0.0)
    return {
        "media_total": media_total,
        "media_sin_top_n": media_sin_top_n,
        "depende_de_pocas_senales": depende,
    }


def exceso_vs_benchmark(
    serie_bucket: pd.Series,
    serie_benchmark: pd.Series,
) -> pd.Series:
    """Diferencia alineada por fecha entre bucket y benchmark."""
    return serie_bucket.sub(serie_benchmark)


def _metricas_grupo(
    grupo: pd.DataFrame,
    columna_retorno: str,
) -> dict[str, Any]:
    valores = grupo[columna_retorno]
    return {
        "media": float(valores.mean()),
        "mediana": float(valores.median()),
        "hit_rate": hit_rate(grupo, columna_retorno),
        "n": int(len(grupo)),
    }


def _tabla_por_etiquetas(
    datos: pd.DataFrame,
    etiquetas: pd.Series,
    orden: list[str],
    columna_retorno: str,
) -> pd.DataFrame:
    filas = []
    for etiqueta in orden:
        grupo = datos[etiquetas == etiqueta]
        filas.append(_metricas_grupo(grupo, columna_retorno))
    return pd.DataFrame(filas, index=orden, columns=_COLUMNAS_DESGLOSE)


def desglose_por_periodo(
    senales: pd.DataFrame,
    columna_fecha: str = "fecha",
    columna_retorno: str = "retorno_30d",
    frecuencia: str = "Q",
) -> pd.DataFrame:
    """Desglose de métricas por periodo calendario."""
    if senales.empty:
        return pd.DataFrame(columns=_COLUMNAS_DESGLOSE)

    periodos = pd.PeriodIndex(senales[columna_fecha], freq=frecuencia)
    marco = senales.copy()
    marco["_periodo"] = periodos

    filas: list[dict[str, Any]] = []
    indices: list[str] = []

    for periodo, grupo in marco.groupby("_periodo", sort=True):
        filas.append(_metricas_grupo(grupo, columna_retorno))
        indices.append(str(periodo))

    return pd.DataFrame(filas, index=indices, columns=_COLUMNAS_DESGLOSE)


def _etiqueta_tercil(rango: float) -> str:
    if rango < 1.0 / 3.0:
        return "bajo"
    if rango < 2.0 / 3.0:
        return "medio"
    return "alto"


def desglose_por_regimen_vix(
    senales: pd.DataFrame,
    vix_por_fecha: pd.Series,
    columna_fecha: str = "fecha",
    columna_retorno: str = "retorno_30d",
) -> pd.DataFrame:
    """Desglose por régimen de VIX, calculado sobre las fechas presentes."""
    orden = ["bajo", "medio", "alto", "sin_dato"]

    fechas_unicas = pd.Index(senales[columna_fecha].drop_duplicates())
    vix = vix_por_fecha.reindex(fechas_unicas)
    rangos = vix.rank(pct=True)

    mapa: dict[pd.Timestamp, str] = {}
    for fecha, valor, rango in zip(fechas_unicas, vix, rangos):
        if pd.isna(valor) or pd.isna(rango):
            mapa[fecha] = "sin_dato"
        else:
            mapa[fecha] = _etiqueta_tercil(float(rango))

    etiquetas = senales[columna_fecha].map(mapa)
    return _tabla_por_etiquetas(senales, etiquetas, orden, columna_retorno)


def desglose_por_volatilidad(
    senales: pd.DataFrame,
    columna_vol: str = "vol_realizada_20d_cruda",
    columna_retorno: str = "retorno_30d",
) -> pd.DataFrame:
    """Desglose por terciles de volatilidad realizada de la señal."""
    orden = ["bajo", "medio", "alto"]

    validas = senales.dropna(subset=[columna_vol]).copy()
    rangos = validas[columna_vol].rank(pct=True)
    etiquetas = pd.Series(
        [_etiqueta_tercil(float(rango)) for rango in rangos],
        index=validas.index,
        dtype=object,
    )

    return _tabla_por_etiquetas(validas, etiquetas, orden, columna_retorno)


def etiqueta_forward(
    n_fechas_acumuladas: int,
    supera_los_5_benchmarks: bool,
    depende_de_pocas_senales: bool,
) -> str:
    """Etiqueta final fijada por el protocolo de validación forward."""
    if n_fechas_acumuladas < 10:
        return "inconclusa"
    if not supera_los_5_benchmarks:
        return "negativa"
    if depende_de_pocas_senales:
        return "inconclusa"
    return "favorable"

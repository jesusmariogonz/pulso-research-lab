from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


_COLUMNAS_FEATURES: tuple[str, ...] = (
    "mom_5d",
    "mom_10d",
    "mom_20d",
    "dist_sma20",
    "dist_sma50",
    "dist_sma200",
    "golden_cross",
    "atr14",
    "vol_realizada_20d",
    "vol_relativo_20d",
    "volume_spike_z",
    "rsi14",
    "drawdown_60d",
    "gap",
    "fuerza_relativa_20d",
    "beta_60d",
    "sharpe_20d",
    "dist_max20",
    "dist_min20",
    "aceleracion",
)


def _sin_infinitos(serie: pd.Series) -> pd.Series:
    """Convierte infinitos en NaN, preservando el índice."""
    return serie.replace([np.inf, -np.inf], np.nan)


def _pct_change(serie: pd.Series) -> pd.Series:
    """Retornos diarios sin relleno implícito de NaN."""
    return _sin_infinitos(serie.pct_change(fill_method=None))


def momentum(precio: pd.Series, dias: int) -> pd.Series:
    """Momentum simple: precio / precio.shift(dias) - 1."""
    resultado = precio / precio.shift(dias) - 1.0
    return _sin_infinitos(resultado)


def distancia_sma(precio: pd.Series, ventana: int) -> pd.Series:
    """Distancia relativa del precio a su media móvil simple."""
    sma = precio.rolling(ventana, min_periods=ventana).mean()
    resultado = precio / sma - 1.0
    return _sin_infinitos(resultado)


def cruce_sma(
    precio: pd.Series, ventana_corta: int, ventana_larga: int
) -> pd.Series:
    """Estado golden/death cross entre dos medias móviles simples."""
    sma_corta = precio.rolling(ventana_corta, min_periods=ventana_corta).mean()
    sma_larga = precio.rolling(ventana_larga, min_periods=ventana_larga).mean()

    resultado = pd.Series(pd.NA, index=precio.index, dtype="boolean")
    completas = sma_corta.notna() & sma_larga.notna()
    if completas.any():
        resultado.loc[completas] = (
            sma_corta.loc[completas] > sma_larga.loc[completas]
        )
    return resultado


def atr(
    alto: pd.Series,
    bajo: pd.Series,
    cierre: pd.Series,
    ventana: int,
) -> pd.Series:
    """Average True Range simple usando media móvil de TR."""
    cierre_previo = cierre.shift(1)
    componentes = pd.concat(
        [
            alto - bajo,
            (alto - cierre_previo).abs(),
            (bajo - cierre_previo).abs(),
        ],
        axis=1,
    )
    rango_verdadero = componentes.max(axis=1, skipna=True)
    return rango_verdadero.rolling(ventana, min_periods=ventana).mean()


def volatilidad_realizada(precio: pd.Series, ventana: int) -> pd.Series:
    """Volatilidad realizada anualizada a partir de retornos diarios."""
    retornos = _pct_change(precio)
    std = retornos.rolling(ventana, min_periods=ventana).std(ddof=1)
    resultado = std * np.sqrt(252.0)
    return _sin_infinitos(resultado)


def volumen_relativo(volumen: pd.Series, ventana: int) -> pd.Series:
    """Volumen actual dividido por su media móvil."""
    media = volumen.rolling(ventana, min_periods=ventana).mean()
    resultado = volumen / media
    return _sin_infinitos(resultado)


def volume_spike_zscore(
    volumen: pd.Series, ventana_corta: int, ventana_larga: int
) -> pd.Series:
    """Z-score del volumen relativo entre media corta y media larga."""
    media_corta = volumen.rolling(
        ventana_corta, min_periods=ventana_corta
    ).mean()
    media_larga = volumen.rolling(
        ventana_larga, min_periods=ventana_larga
    ).mean()
    sd_larga = volumen.rolling(
        ventana_larga, min_periods=ventana_larga
    ).std(ddof=1)

    sd_segura = sd_larga.mask(sd_larga == 0.0)
    resultado = (media_corta - media_larga) / sd_segura
    return _sin_infinitos(resultado)


def rsi(precio: pd.Series, ventana: int) -> pd.Series:
    """RSI simple de medias móviles, con casos planos declarados."""
    diff = precio.diff()
    ganancia = diff.clip(lower=0.0)
    perdida = (-diff).clip(lower=0.0)

    media_ganancia = ganancia.rolling(
        ventana, min_periods=ventana
    ).mean()
    media_perdida = perdida.rolling(
        ventana, min_periods=ventana
    ).mean()

    resultado = pd.Series(np.nan, index=precio.index, dtype=float)
    validas = media_ganancia.notna() & media_perdida.notna()

    con_perdida = validas & (media_perdida > 0.0)
    if con_perdida.any():
        resultado.loc[con_perdida] = 100.0 - 100.0 / (
            1.0
            + media_ganancia.loc[con_perdida]
            / media_perdida.loc[con_perdida]
        )

    solo_ganancia = validas & (media_perdida == 0.0) & (
        media_ganancia > 0.0
    )
    if solo_ganancia.any():
        resultado.loc[solo_ganancia] = 100.0

    plano = validas & (media_perdida == 0.0) & (
        media_ganancia == 0.0
    )
    if plano.any():
        resultado.loc[plano] = 50.0

    return _sin_infinitos(resultado)


def drawdown_previo(precio: pd.Series, ventana: int) -> pd.Series:
    """Distancia relativa al máximo móvil previo."""
    maximo = precio.rolling(ventana, min_periods=ventana).max()
    resultado = precio / maximo - 1.0
    return _sin_infinitos(resultado)


def gap(apertura: pd.Series, cierre: pd.Series) -> pd.Series:
    """Gap de apertura contra el cierre anterior."""
    resultado = apertura / cierre.shift(1) - 1.0
    return _sin_infinitos(resultado)


def fuerza_relativa(
    precio: pd.Series, precio_benchmark: pd.Series, dias: int
) -> pd.Series:
    """Diferencia de momentum contra el benchmark ya alineado."""
    return momentum(precio, dias) - momentum(precio_benchmark, dias)


def beta(
    precio: pd.Series, precio_benchmark: pd.Series, ventana: int
) -> pd.Series:
    """Beta rodante contra el benchmark ya alineado."""
    r = _pct_change(precio)
    r_b = _pct_change(precio_benchmark)

    cov = r.rolling(ventana, min_periods=ventana).cov(r_b)
    var = r_b.rolling(ventana, min_periods=ventana).var(ddof=1)
    var_segura = var.mask(var == 0.0)

    resultado = cov / var_segura
    return _sin_infinitos(resultado)


def sharpe_reciente(precio: pd.Series, ventana: int) -> pd.Series:
    """Sharpe rodante anualizado de retornos diarios."""
    r = _pct_change(precio)
    media = r.rolling(ventana, min_periods=ventana).mean()
    sd = r.rolling(ventana, min_periods=ventana).std(ddof=1)
    sd_segura = sd.mask(sd == 0.0)

    resultado = media / sd_segura * np.sqrt(252.0)
    return _sin_infinitos(resultado)


def distancia_extremo(
    precio: pd.Series,
    ventana: int,
    tipo: Literal["max", "min"],
) -> pd.Series:
    """Distancia relativa al máximo o mínimo móvil."""
    if tipo == "max":
        extremo = precio.rolling(ventana, min_periods=ventana).max()
    elif tipo == "min":
        extremo = precio.rolling(ventana, min_periods=ventana).min()
    else:
        raise ValueError('tipo debe ser "max" o "min"')

    resultado = precio / extremo - 1.0
    return _sin_infinitos(resultado)


def aceleracion(
    precio: pd.Series, dias_corto: int, dias_largo: int
) -> pd.Series:
    """Diferencia entre momentum de corto y largo plazo."""
    return momentum(precio, dias_corto) - momentum(precio, dias_largo)


def calcular_features_simbolo(
    df: pd.DataFrame, df_benchmark: pd.DataFrame
) -> pd.DataFrame:
    """Calcula las 20 features nombradas del pre-registro para un símbolo."""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"]
    volume = df["volume"]
    bench_close = df_benchmark["close"]

    features = pd.DataFrame(
        {
            "mom_5d": momentum(close, 5),
            "mom_10d": momentum(close, 10),
            "mom_20d": momentum(close, 20),
            "dist_sma20": distancia_sma(close, 20),
            "dist_sma50": distancia_sma(close, 50),
            "dist_sma200": distancia_sma(close, 200),
            "golden_cross": cruce_sma(close, 50, 200),
            "atr14": atr(high, low, close, 14),
            "vol_realizada_20d": volatilidad_realizada(close, 20),
            "vol_relativo_20d": volumen_relativo(volume, 20),
            "volume_spike_z": volume_spike_zscore(volume, 5, 60),
            "rsi14": rsi(close, 14),
            "drawdown_60d": drawdown_previo(close, 60),
            "gap": gap(open_, close),
            "fuerza_relativa_20d": fuerza_relativa(
                close, bench_close, 20
            ),
            "beta_60d": beta(close, bench_close, 60),
            "sharpe_20d": sharpe_reciente(close, 20),
            "dist_max20": distancia_extremo(close, 20, "max"),
            "dist_min20": distancia_extremo(close, 20, "min"),
            "aceleracion": aceleracion(close, 5, 20),
        },
        index=df.index,
    )

    return features.loc[:, list(_COLUMNAS_FEATURES)]


def universo_elegible(
    universo: dict[str, pd.DataFrame],
    fecha: pd.Timestamp,
    min_historia: int = 252,
) -> list[str]:
    """Símbolos con al menos min_historia filas hasta fecha, ordenados."""
    elegibles: list[str] = []
    for simbolo, df in universo.items():
        filas_hasta_fecha = int((df.index <= fecha).sum())
        if filas_hasta_fecha >= min_historia:
            elegibles.append(simbolo)
    return sorted(elegibles)


def features_cross_sectional(
    universo: dict[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    fecha: pd.Timestamp,
    min_historia: int = 252,
) -> pd.DataFrame:
    """Calcula la última fila de features para cada símbolo elegible."""
    elegibles = universo_elegible(universo, fecha, min_historia)
    filas: list[dict[str, float | bool | pd._libs.missing.NAType]] = []

    for simbolo in elegibles:
        df = universo[simbolo]
        df_recortado = df.loc[df.index <= fecha].copy()
        benchmark_recortado = benchmark.reindex(df_recortado.index)
        features = calcular_features_simbolo(
            df_recortado, benchmark_recortado
        )
        filas.append(features.iloc[-1].to_dict())

    return pd.DataFrame(
        filas,
        index=elegibles,
        columns=list(_COLUMNAS_FEATURES),
    )


def normalizar_percentil_cross_sectional(
    features_crudas: pd.DataFrame,
) -> pd.DataFrame:
    """Ranking percentil por columna, ignorando NaN."""
    return features_crudas.rank(pct=True)


def discriminacion_features(
    features_crudas: pd.DataFrame,
    es_ganador: pd.Series,
) -> pd.DataFrame:
    """Diferencia de medianas y correlación punto-biserial por feature."""
    valores: list[list[float | int]] = []

    for columna in features_crudas.columns:
        datos = pd.DataFrame(
            {
                "x": features_crudas[columna],
                "ganador": es_ganador,
            }
        ).dropna()

        n_ganadores = int(datos["ganador"].sum())
        n_no_ganadores = int(len(datos) - n_ganadores)

        grupo_ganadores = datos.loc[datos["ganador"], "x"]
        grupo_no_ganadores = datos.loc[~datos["ganador"], "x"]

        if len(grupo_ganadores) >= 2 and len(grupo_no_ganadores) >= 2:
            diferencia = (
                grupo_ganadores.median() - grupo_no_ganadores.median()
            )
            correlacion = datos["ganador"].astype(float).corr(datos["x"])
        else:
            diferencia = np.nan
            correlacion = np.nan

        valores.append(
            [
                diferencia,
                correlacion,
                n_ganadores,
                n_no_ganadores,
            ]
        )

    resultado = pd.DataFrame(
        valores,
        index=features_crudas.columns,
        columns=[
            "diferencia_medianas",
            "correlacion_punto_biserial",
            "n_ganadores",
            "n_no_ganadores",
        ],
    )

    def _clave(nombre: str) -> tuple[int, float, str]:
        corr = resultado.at[nombre, "correlacion_punto_biserial"]
        if pd.isna(corr):
            return (1, 0.0, str(nombre))
        return (0, -abs(float(corr)), str(nombre))

    ordenados = sorted(resultado.index, key=_clave)
    return resultado.loc[ordenados]


def features_discriminantes(
    discriminacion: pd.DataFrame,
    umbral: float = 0.05,
    max_features: int = 5,
) -> list[str]:
    """Features con |correlación| sobre umbral, respetando el orden recibido."""
    seleccionadas: list[str] = []

    for nombre in discriminacion.index:
        corr = discriminacion.at[nombre, "correlacion_punto_biserial"]
        if pd.isna(corr):
            continue
        if abs(float(corr)) >= umbral:
            seleccionadas.append(nombre)

    return seleccionadas[:max_features]

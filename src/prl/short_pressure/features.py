from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Bloques base de precio
# ---------------------------------------------------------------------------


def momentum(precio: pd.Series, dias: int) -> pd.Series:
    """Retorno simple de ``dias`` sesiones."""
    return precio / precio.shift(dias) - 1.0


def distancia_sma(precio: pd.Series, ventana: int) -> pd.Series:
    """Distancia relativa del precio a su media móvil simple."""
    sma = precio.rolling(ventana, min_periods=ventana).mean()
    return precio / sma - 1.0


def rsi(precio: pd.Series, ventana: int) -> pd.Series:
    """RSI simple (no Wilder), con ventana completa obligatoria."""
    diff = precio.diff()
    ganancia = diff.clip(lower=0.0)
    perdida = (-diff).clip(lower=0.0)

    media_ganancia = ganancia.rolling(ventana, min_periods=ventana).mean()
    media_perdida = perdida.rolling(ventana, min_periods=ventana).mean()

    condiciones = [
        media_perdida > 0.0,
        (media_perdida == 0.0) & (media_ganancia > 0.0),
        (media_perdida == 0.0) & (media_ganancia == 0.0),
    ]
    valores = [
        100.0 - 100.0 / (1.0 + media_ganancia / media_perdida),
        100.0,
        50.0,
    ]
    resultado = np.select(condiciones, valores, default=np.nan)
    return pd.Series(resultado, index=precio.index, dtype=float)


def drawdown_previo(precio: pd.Series, ventana: int) -> pd.Series:
    """Drawdown respecto del máximo de la ventana anterior."""
    maximo = precio.rolling(ventana, min_periods=ventana).max()
    return precio / maximo - 1.0


def volatilidad_realizada(precio: pd.Series, ventana: int) -> pd.Series:
    """Volatilidad realizada anualizada de retornos diarios."""
    retornos = precio.pct_change()
    std = retornos.rolling(ventana, min_periods=ventana).std(ddof=1)
    return std * np.sqrt(252.0)


def volumen_relativo(volumen: pd.Series, ventana: int) -> pd.Series:
    """Volumen relativo al promedio de la ventana."""
    media = volumen.rolling(ventana, min_periods=ventana).mean()
    resultado = volumen / media
    return resultado.mask(media.isna() | (media == 0.0))


def zscore_retorno(
    precio: pd.Series,
    dias_retorno: int,
    ventana: int,
) -> pd.Series:
    """Z-score de un retorno contra su propia distribución rolling."""
    r = momentum(precio, dias_retorno)
    media = r.rolling(ventana, min_periods=ventana).mean()
    sd = r.rolling(ventana, min_periods=ventana).std(ddof=1)
    resultado = (r - media) / sd
    return resultado.mask(sd.isna() | (sd == 0.0))


def zscore_nivel(serie: pd.Series, ventana: int) -> pd.Series:
    """Z-score del nivel de una serie contra su distribución rolling."""
    media = serie.rolling(ventana, min_periods=ventana).mean()
    sd = serie.rolling(ventana, min_periods=ventana).std(ddof=1)
    resultado = (serie - media) / sd
    return resultado.mask(sd.isna() | (sd == 0.0))


# ---------------------------------------------------------------------------
# Short Pressure: point-in-time de fuentes FINRA
# ---------------------------------------------------------------------------


def short_volume_ratio_serie(
    short_volume_simbolo: pd.DataFrame,
    calendario: pd.DatetimeIndex,
) -> pd.Series:
    """Short volume ratio de un símbolo, reindexado sin relleno."""
    cal = pd.DatetimeIndex(calendario)
    if short_volume_simbolo is None or short_volume_simbolo.empty:
        return pd.Series(np.nan, index=cal, dtype=float)

    df = short_volume_simbolo.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date"], keep="last")
    serie = df.set_index("date")["short_volume_ratio"].reindex(cal)
    return serie.astype(float)


def _serie_snapshot_point_in_time(
    short_interest_simbolo: pd.DataFrame,
    calendario: pd.DatetimeIndex,
    columna: str,
) -> pd.Series:
    """Serie de snapshots vigentes de short interest según publicación FINRA."""
    cal = pd.DatetimeIndex(calendario)
    if short_interest_simbolo is None or short_interest_simbolo.empty:
        return pd.Series(np.nan, index=cal, dtype=float)

    df = short_interest_simbolo.copy()
    df["settlement_date"] = pd.to_datetime(df["settlement_date"])
    df = df.drop_duplicates(subset=["settlement_date"], keep="last")

    fechas_publicacion = df["settlement_date"] + pd.tseries.offsets.BDay(7)
    publicacion = pd.DataFrame(
        {
            "publicacion": pd.to_datetime(fechas_publicacion),
            "valor": pd.to_numeric(df[columna], errors="coerce"),
        }
    ).dropna(subset=["publicacion"])

    if publicacion.empty:
        return pd.Series(np.nan, index=cal, dtype=float)

    publicacion = publicacion.sort_values("publicacion", kind="mergesort")

    fechas_pub = publicacion["publicacion"].to_numpy()
    valores = publicacion["valor"].to_numpy(dtype=float)

    posiciones = np.searchsorted(fechas_pub, cal.to_numpy(), side="right") - 1
    resultado = np.full(len(cal), np.nan, dtype=float)
    validos = posiciones >= 0
    resultado[validos] = valores[posiciones[validos]]

    return pd.Series(resultado, index=cal, dtype=float)


def days_to_cover_serie(
    short_interest_simbolo: pd.DataFrame,
    calendario: pd.DatetimeIndex,
) -> pd.Series:
    """Days-to-cover vigente para cada fecha del calendario."""
    return _serie_snapshot_point_in_time(
        short_interest_simbolo,
        calendario,
        "days_to_cover",
    )


def short_interest_change_pct_serie(
    short_interest_simbolo: pd.DataFrame,
    calendario: pd.DatetimeIndex,
) -> pd.Series:
    """Cambio porcentual de short interest vigente para cada fecha."""
    return _serie_snapshot_point_in_time(
        short_interest_simbolo,
        calendario,
        "short_interest_change_pct",
    )


# ---------------------------------------------------------------------------
# Scores agregados
# ---------------------------------------------------------------------------


def SHORT_PRESSURE_SCORE(tabla_percentil: pd.DataFrame) -> pd.Series:
    """Promedio simple de las 4 sub-features de short pressure."""
    columnas = [
        "short_volume_ratio",
        "short_volume_ratio_zscore_20d",
        "days_to_cover",
        "short_interest_change_pct",
    ]
    return tabla_percentil[columnas].mean(axis=1, skipna=False)


_COLUMNAS_PE_INVERTIDAS = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "drawdown_5d",
    "drawdown_20d",
    "drawdown_60d",
    "dist_sma20",
    "dist_sma50",
    "dist_sma200",
    "rsi_2",
    "rsi_14",
    "zscore_ret_5d",
]

_COLUMNAS_PE_DIRECTAS = [
    "realized_vol_20d",
    "rel_volume",
]


def PRICE_EXHAUSTION_SCORE(tabla_percentil: pd.DataFrame) -> pd.Series:
    """Score de agotamiento de precio orientado a que bajo = más agotado."""
    orientadas = pd.concat(
        [
            1.0 - tabla_percentil[_COLUMNAS_PE_INVERTIDAS],
            tabla_percentil[_COLUMNAS_PE_DIRECTAS],
        ],
        axis=1,
    )
    promedio_orientado = orientadas.mean(axis=1, skipna=False)
    return 1.0 - promedio_orientado


# ---------------------------------------------------------------------------
# Reversal Confirmation
# ---------------------------------------------------------------------------


def _comparacion_booleana_shift(
    serie: pd.Series,
    operador: str,
) -> pd.Series:
    """Compara una serie contra su valor previo con dtype nullable."""
    desplazada = serie.shift(1)
    resultado = pd.Series(pd.NA, index=serie.index, dtype="boolean")
    validos = serie.notna() & desplazada.notna()

    if operador == "mayor":
        valores = serie.loc[validos] > desplazada.loc[validos]
    elif operador == "menor":
        valores = serie.loc[validos] < desplazada.loc[validos]
    else:  # pragma: no cover
        raise ValueError(f"Operador no soportado: {operador}")

    resultado.loc[validos] = valores.astype(bool)
    return resultado


def confirmacion_a(cierre: pd.Series) -> pd.Series:
    """Confirmación A: el cierre sube contra la sesión anterior."""
    return _comparacion_booleana_shift(cierre, "mayor")


def confirmacion_b(
    cierre: pd.Series,
    alto: pd.Series,
    bajo: pd.Series,
    ventana_caida: int = 10,
) -> pd.Series:
    """Confirmación B: recuperación de al menos 25% del rango reciente."""
    high_reciente = alto.rolling(
        ventana_caida, min_periods=ventana_caida
    ).max()
    low_reciente = bajo.rolling(
        ventana_caida, min_periods=ventana_caida
    ).min()
    rango = high_reciente - low_reciente

    resultado = pd.Series(pd.NA, index=cierre.index, dtype="boolean")
    ventana_completa = rango.notna()

    # Rango cero: precio plano toda la ventana. No hay caída que recuperar,
    # la confirmación no aplica y se declara explícitamente False.
    resultado.loc[ventana_completa & (rango == 0.0)] = False

    mascara = (
        ventana_completa
        & (rango > 0.0)
        & cierre.notna()
        & low_reciente.notna()
    )
    if bool(mascara.any()):
        valores = (cierre - low_reciente) / rango >= 0.25
        resultado.loc[mascara] = valores.loc[mascara].astype(bool)

    return resultado


def confirmacion_c(alto: pd.Series) -> pd.Series:
    """Confirmación C: el máximo de la sesión supera al anterior."""
    return _comparacion_booleana_shift(alto, "mayor")


def confirmacion_d(vol_5d: pd.Series) -> pd.Series:
    """Confirmación D: la volatilidad realizada de 5 días desciende."""
    return _comparacion_booleana_shift(vol_5d, "menor")


def confirmacion_e(rel_volume: pd.Series, cierre: pd.Series) -> pd.Series:
    """Confirmación E: volumen relativo alto y cierre al alza.

    La comparación de volumen alto considera el valor de la sesión y, para
    mantener compatibilidad con la serie de volumen relativo ya calculada,
    también el de la sesión inmediatamente anterior. La condición de cierre
    al alza es siempre contra la sesión previa.
    """
    cierre_previo = cierre.shift(1)
    rel_volume_previo = rel_volume.shift(1)

    resultado = pd.Series(pd.NA, index=cierre.index, dtype="boolean")
    validos = (
        rel_volume.notna()
        & cierre.notna()
        & cierre_previo.notna()
    )

    volumen_alto = (rel_volume > 1.0) | (rel_volume_previo > 1.0)
    cierre_sube = cierre > cierre_previo
    resultado.loc[validos] = (
        volumen_alto.loc[validos] & cierre_sube.loc[validos]
    ).astype(bool)

    return resultado


# ---------------------------------------------------------------------------
# Ensamblador por símbolo
# ---------------------------------------------------------------------------

_COLUMNAS_NUMERICAS = [
    "short_volume_ratio",
    "short_volume_ratio_zscore_20d",
    "days_to_cover",
    "short_interest_change_pct",
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "drawdown_5d",
    "drawdown_20d",
    "drawdown_60d",
    "dist_sma20",
    "dist_sma50",
    "dist_sma200",
    "rsi_2",
    "rsi_14",
    "realized_vol_20d",
    "rel_volume",
    "zscore_ret_5d",
]

_COLUMNAS_CONFIRMACION = [
    "confirmacion_a",
    "confirmacion_b",
    "confirmacion_c",
    "confirmacion_d",
    "confirmacion_e",
]


def calcular_features_simbolo(
    df: pd.DataFrame,
    short_volume_simbolo: pd.DataFrame,
    short_interest_simbolo: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula las 18 features crudas y las 5 confirmaciones booleanas."""
    calendario = pd.DatetimeIndex(df.index)
    cierre = df["close"].astype(float)
    alto = df["high"].astype(float)
    bajo = df["low"].astype(float)
    volumen = df["volume"].astype(float)

    short_volume_ratio = short_volume_ratio_serie(
        short_volume_simbolo,
        calendario,
    )
    days_to_cover = days_to_cover_serie(
        short_interest_simbolo,
        calendario,
    )
    short_interest_change_pct = short_interest_change_pct_serie(
        short_interest_simbolo,
        calendario,
    )

    rel_volume = volumen_relativo(volumen, 20)
    vol_5d = volatilidad_realizada(cierre, 5)

    columnas: dict[str, pd.Series] = {
        "short_volume_ratio": short_volume_ratio,
        "short_volume_ratio_zscore_20d": zscore_nivel(
            short_volume_ratio,
            ventana=20,
        ),
        "days_to_cover": days_to_cover,
        "short_interest_change_pct": short_interest_change_pct,
        "ret_1d": momentum(cierre, 1),
        "ret_5d": momentum(cierre, 5),
        "ret_20d": momentum(cierre, 20),
        "drawdown_5d": drawdown_previo(cierre, 5),
        "drawdown_20d": drawdown_previo(cierre, 20),
        "drawdown_60d": drawdown_previo(cierre, 60),
        "dist_sma20": distancia_sma(cierre, 20),
        "dist_sma50": distancia_sma(cierre, 50),
        "dist_sma200": distancia_sma(cierre, 200),
        "rsi_2": rsi(cierre, 2),
        "rsi_14": rsi(cierre, 14),
        "realized_vol_20d": volatilidad_realizada(cierre, 20),
        "rel_volume": rel_volume,
        "zscore_ret_5d": zscore_retorno(
            cierre,
            dias_retorno=5,
            ventana=252,
        ),
        "confirmacion_a": confirmacion_a(cierre),
        "confirmacion_b": confirmacion_b(cierre, alto, bajo),
        "confirmacion_c": confirmacion_c(alto),
        "confirmacion_d": confirmacion_d(vol_5d),
        "confirmacion_e": confirmacion_e(rel_volume, cierre),
    }

    return pd.DataFrame(columnas, index=df.index)

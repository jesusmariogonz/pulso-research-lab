from __future__ import annotations

import numpy as np
import pandas as pd


def _signo(valores: pd.Series) -> pd.Series:
    """Convierte valores numéricos en señales 1.0 / -1.0 / 0.0, preservando NaN."""
    out = pd.Series(np.nan, index=valores.index, dtype=float, name=valores.name)
    out[valores > 0] = 1.0
    out[valores < 0] = -1.0
    out[valores == 0] = 0.0
    return out


def ts_momentum_signal(precio: pd.Series, meses: int) -> pd.Series:
    """Señal de momentum temporal: signo del retorno contra ``meses`` meses atrás."""
    ventana = meses * 21
    retorno = precio / precio.shift(ventana) - 1.0
    return _signo(retorno)


def trend_signal(precio: pd.Series, ventana: int) -> pd.Series:
    """Señal de tendencia: signo del precio relativo a su media móvil simple."""
    sma = precio.rolling(ventana, min_periods=ventana).mean()
    retorno = precio / sma - 1.0
    return _signo(retorno)


def breakout_signal(precio: pd.Series, ventana: int) -> pd.Series:
    """Señal de ruptura contra máximo/mínimo móvil de ``ventana`` días."""
    maximo = precio.rolling(ventana, min_periods=ventana).max()
    minimo = precio.rolling(ventana, min_periods=ventana).min()

    out = pd.Series(np.nan, index=precio.index, dtype=float, name=precio.name)
    valido = maximo.notna() & minimo.notna() & precio.notna()

    out[valido] = 0.0
    out[valido & (precio <= minimo)] = -1.0
    out[valido & (precio >= maximo)] = 1.0
    return out


def reversion_zscore(precio: pd.Series, ventana: int) -> pd.Series:
    """Z-score del precio contra su media y desviación estándar móviles."""
    media = precio.rolling(ventana, min_periods=ventana).mean()
    sd = precio.rolling(ventana, min_periods=ventana).std(ddof=1)

    denominador = sd.where((sd != 0) & sd.notna(), np.nan)
    return (precio - media) / denominador


def senal_reversion(precio: pd.Series, ventana: int) -> pd.Series:
    """Señal de reversión: signo opuesto al z-score de reversion."""
    return _signo(-reversion_zscore(precio, ventana))


def volatilidad_realizada(precio: pd.Series, ventana: int) -> pd.Series:
    """Volatilidad realizada anualizada de retornos simples diarios."""
    retornos = precio.pct_change(fill_method=None)
    return retornos.rolling(ventana, min_periods=ventana).std(ddof=1) * np.sqrt(252.0)


def composite_score(dims: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Promedio ponderado por fila usando solo columnas disponibles y renormalizando."""
    columnas = [col for col in dims.columns if col in weights]
    if not columnas:
        return pd.Series(np.nan, index=dims.index, dtype=float)

    sub = dims[columnas]
    pesos = pd.Series({col: float(weights[col]) for col in columnas}, dtype=float)

    numerador = sub.mul(pesos, axis=1).sum(axis=1, min_count=1)
    denominador = sub.notna().astype(float).mul(pesos, axis=1).sum(axis=1)
    denominador = denominador.where(denominador != 0.0, np.nan)

    return (numerador / denominador).astype(float)


def signo_cambio_trailing(serie_conocida: pd.Series, dias: int) -> pd.Series:
    """Señal del signo del cambio contra el valor de hace ``dias`` observaciones."""
    cambio = serie_conocida - serie_conocida.shift(dias)
    return _signo(cambio)


def regimen_macro(
    liquidez_signo: pd.Series, crecimiento_signo: pd.Series
) -> pd.Series:
    """Régimen macro 1-4 a partir de los signos de liquidez y crecimiento."""
    out = pd.Series(np.nan, index=liquidez_signo.index, dtype=float)

    valido = (
        liquidez_signo.notna()
        & crecimiento_signo.notna()
        & (liquidez_signo != 0.0)
        & (crecimiento_signo != 0.0)
    )

    liq_pos = liquidez_signo == 1.0
    liq_neg = liquidez_signo == -1.0
    cre_pos = crecimiento_signo == 1.0
    cre_neg = crecimiento_signo == -1.0

    out[valido & liq_pos & cre_pos] = 1.0
    out[valido & liq_pos & cre_neg] = 2.0
    out[valido & liq_neg & cre_pos] = 3.0
    out[valido & liq_neg & cre_neg] = 4.0

    return out


def es_regimen_de_rango(regimen: pd.Series) -> pd.Series:
    """True solo para los regímenes 2 y 3; False para 1, 4 y NaN."""
    return regimen.isin([2.0, 3.0])


def senal_compuesta_con_overlay(
    direccional: pd.Series,
    reversion: pd.Series,
    regimen_de_rango: pd.Series,
) -> pd.Series:
    """Elige reversión en régimen de rango y direccional en el resto."""
    mascara = regimen_de_rango.fillna(False).astype(bool)
    out = direccional.where(~mascara, reversion)
    return out.astype(float)

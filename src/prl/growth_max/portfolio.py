from __future__ import annotations

import numpy as np
import pandas as pd


def pesos_equal(senales: pd.DataFrame) -> pd.DataFrame:
    """Pesos equiponderados por fila entre las señales válidas."""
    validas = senales.notna() & (senales != 0.0)
    signos = np.sign(senales).where(validas, 0.0)
    n_validas = validas.sum(axis=1)
    denominador = n_validas.where(n_validas > 0, np.nan)
    pesos = signos.div(denominador, axis=0)
    return pesos.where(validas, 0.0).fillna(0.0)


def pesos_inv_vol(senales: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    """Pesos normalizados a gross 1.0 usando inverso de volatilidad."""
    validas = senales.notna() & (senales != 0.0) & vol.notna() & (vol > 0.0)
    vol_valida = vol.where(validas)
    crudo = (np.sign(senales) / vol_valida).where(validas, 0.0)
    gross = crudo.abs().sum(axis=1)
    denominador = gross.where(gross > 0.0, np.nan)
    pesos = crudo.div(denominador, axis=0)
    return pesos.where(validas, 0.0).fillna(0.0)


def pesos_vol_target(
    senales: pd.DataFrame,
    vol: pd.DataFrame,
    objetivo: float,
) -> pd.DataFrame:
    """Escala pesos de inverso de volatilidad a una volatilidad objetivo."""
    base = pesos_inv_vol(senales, vol)

    contribucion = base.pow(2) * vol.pow(2)
    contribucion = contribucion.where(base != 0.0, 0.0).fillna(0.0)
    varianza_aprox = contribucion.sum(axis=1)
    vol_portafolio = np.sqrt(varianza_aprox.clip(lower=0.0))

    factor = pd.Series(0.0, index=base.index, dtype=float)
    mascara = vol_portafolio > 0.0
    factor.loc[mascara] = objetivo / vol_portafolio.loc[mascara]

    return base.mul(factor, axis=0)


def retorno_esperado_trailing(
    retornos: pd.DataFrame,
    ventana: int,
) -> pd.DataFrame:
    """Media móvil trailing de retornos por columna."""
    return retornos.rolling(ventana, min_periods=ventana).mean()


def varianza_trailing(retornos: pd.DataFrame, ventana: int) -> pd.DataFrame:
    """Varianza móvil trailing de retornos por columna."""
    return retornos.rolling(ventana, min_periods=ventana).var(ddof=1)


def pesos_kelly_frac(
    senales: pd.DataFrame,
    mu: pd.DataFrame,
    varianza: pd.DataFrame,
    fraccion: float,
    tope_posicion: float = 0.20,
) -> pd.DataFrame:
    """Pesos tipo Kelly fraccional, recortados por posición y gross."""
    validas = (
        senales.notna()
        & (senales != 0.0)
        & varianza.notna()
        & (varianza > 0.0)
    )

    mu_efectivo = mu.where(mu.notna(), 0.0)
    varianza_valida = varianza.where(validas)
    kelly = mu_efectivo / varianza_valida

    crudo = (np.sign(senales) * fraccion * kelly.abs()).where(validas, 0.0)
    crudo = crudo.clip(lower=-tope_posicion, upper=tope_posicion)

    gross = crudo.abs().sum(axis=1)
    escala = pd.Series(1.0, index=crudo.index, dtype=float)
    mascara = gross > 1.0
    escala.loc[mascara] = 1.0 / gross.loc[mascara]

    return crudo.mul(escala, axis=0)


def cash_pct_dinamico(regimen: pd.Series) -> pd.Series:
    """Porcentaje de cash según régimen macro; conservador ante NaN."""
    cash = pd.Series(0.10, index=regimen.index, dtype=float)
    cash.loc[regimen.isin([1.0, 2.0])] = 0.02
    return cash


def aplicar_leverage_y_cash(
    pesos_base: pd.DataFrame,
    L: float,
    cash_pct: pd.Series,
) -> pd.DataFrame:
    """Aplica apalancamiento y descuenta cash por fecha."""
    if not cash_pct.between(0.0, 1.0, inclusive="both").all():
        raise ValueError("cash_pct debe estar en el intervalo [0, 1]")

    escala = L * (1.0 - cash_pct)
    return pesos_base.mul(escala, axis=0)


def costo_apalancamiento_diario(
    L: float,
    tasa_cash_anual: pd.Series,
    spread_anual: float,
) -> pd.Series:
    """Costo diario de apalancamiento sobre la tasa cash más spread."""
    if L == 1.0:
        return pd.Series(0.0, index=tasa_cash_anual.index, dtype=float)

    return (L - 1.0) * (tasa_cash_anual / 252.0 + spread_anual / 252.0)

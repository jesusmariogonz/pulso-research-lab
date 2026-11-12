from __future__ import annotations

import numpy as np
import pandas as pd


def _turnover(pesos_aplicados: pd.DataFrame) -> pd.Series:
    """Calcula turnover fila a fila entre pesos ya aplicados."""
    turnover = pesos_aplicados.diff().abs().sum(axis=1).astype(float)
    if len(turnover) > 0:
        turnover.iloc[0] = 0.0
    return turnover


def costo_transaccion_diario(
    pesos_aplicados: pd.DataFrame,
    costo_por_lado: float = 0.001,
) -> pd.Series:
    """Costo de transacción diario a partir del turnover de pesos aplicados.

    El primer día no tiene fila anterior y, por convención, su turnover es 0.0.
    Los pesos recibidos ya están rezagados; esta función no aplica shift.
    """
    return _turnover(pesos_aplicados) * float(costo_por_lado)


def ejecutar_backtest(
    pesos: pd.DataFrame,
    retornos: pd.DataFrame,
    costo_apalancamiento: pd.Series,
    costo_por_lado: float = 0.001,
) -> pd.DataFrame:
    """Ejecuta el backtest diario aplicando rezago de pesos, costos y equity.

    Reglas principales:
    - ``pesos`` y ``retornos`` deben tener exactamente el mismo índice y columnas.
    - ``costo_apalancamiento`` debe compartir el índice de ``retornos``.
    - ``pesos`` no puede contener ``NaN``.
    - No se permite sostener una posición distinta de cero en un activo cuyo
      retorno sea ``NaN`` ese día.
    """
    if not pesos.index.equals(retornos.index):
        raise ValueError("pesos y retornos deben compartir exactamente el índice")
    if not pesos.columns.equals(retornos.columns):
        raise ValueError("pesos y retornos deben compartir exactamente las columnas")
    if not costo_apalancamiento.index.equals(retornos.index):
        raise ValueError(
            "costo_apalancamiento debe compartir exactamente el índice de retornos"
        )
    if pesos.isna().any().any():
        raise ValueError("pesos no puede contener NaN")

    pesos_aplicados = pesos.shift(1).fillna(0.0)

    posicion_sin_retorno = pesos_aplicados.ne(0.0) & retornos.isna()
    if posicion_sin_retorno.any().any():
        raise ValueError(
            "Hay una posición distinta de cero en un activo sin retorno ese día"
        )

    turnover = _turnover(pesos_aplicados)
    costo_transaccion = turnover * float(costo_por_lado)

    # Los NaN de retornos solo pueden ocurrir en activos con peso aplicado 0.0
    # gracias a la validación anterior. El sum(skipna=True) los ignora.
    bruto = (pesos_aplicados * retornos).sum(axis=1, skipna=True)

    ret = bruto - costo_transaccion - costo_apalancamiento
    equity = (1.0 + ret).cumprod()

    return pd.DataFrame(
        {
            "ret": ret,
            "equity": equity,
            "turnover": turnover,
            "costo_transaccion": costo_transaccion,
            "costo_apalancamiento": costo_apalancamiento,
        },
        index=retornos.index,
    )


def metricas(returns: pd.Series) -> dict:
    """Calcula métricas de performance diarias de una serie de retornos.

    Incluye CAGR, máximo drawdown, Calmar, Sharpe, Sortino y número de días.
    Los casos degenerados devuelven ``NaN`` en lugar de ``inf`` o excepciones.
    """
    n_days = int(len(returns))

    if n_days == 0:
        return {
            "cagr": np.nan,
            "max_drawdown": np.nan,
            "calmar": np.nan,
            "sharpe": np.nan,
            "sortino": np.nan,
            "n_days": 0,
        }

    returns = returns.astype(float)
    equity = (1.0 + returns).cumprod()
    equity_final = float((1.0 + returns).prod())

    dias_calendario = (returns.index[-1] - returns.index[0]).days
    if dias_calendario > 0:
        cagr = equity_final ** (365.25 / dias_calendario) - 1.0
    else:
        cagr = np.nan

    max_drawdown = float((equity / equity.cummax() - 1.0).min())

    if pd.isna(max_drawdown) or pd.isna(cagr) or max_drawdown == 0.0:
        calmar = np.nan
    else:
        calmar = cagr / abs(max_drawdown)

    media = float(returns.mean())
    desv = float(returns.std(ddof=1))

    if pd.isna(desv) or desv == 0.0:
        sharpe = np.nan
    else:
        sharpe = media / desv * np.sqrt(252.0)

    retornos_negativos = returns[returns < 0.0]
    if len(retornos_negativos) == 0:
        sortino = np.nan
    else:
        desv_baja = float(retornos_negativos.std(ddof=1))
        if pd.isna(desv_baja) or desv_baja == 0.0:
            sortino = np.nan
        else:
            sortino = media / desv_baja * np.sqrt(252.0)

    return {
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "sharpe": sharpe,
        "sortino": sortino,
        "n_days": n_days,
    }

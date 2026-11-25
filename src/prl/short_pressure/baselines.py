from __future__ import annotations

import pandas as pd


def baseline_buy_hold(simbolos_elegibles: list[str]) -> pd.Series:
    """Baseline 1: comprar y mantener todos los símbolos elegibles.

    Devuelve ``True`` para cada símbolo, respetando el orden recibido.
    """
    return pd.Series(True, index=simbolos_elegibles, dtype=bool)


def baseline_caida_simple(features_crudas: pd.DataFrame) -> pd.Series:
    """Baseline 2: caída simple de 5 días.

    Selecciona los símbolos cuyo retorno crudo de 5 días es menor o igual
    a -10 %. Los valores ``NaN`` se consideran ``False``.
    """
    mascara = features_crudas["ret_5d"] <= -0.10
    return mascara.fillna(False).astype(bool)


def baseline_price_exhaustion(tabla_percentil: pd.DataFrame) -> pd.Series:
    """Baseline 3: price exhaustion en el percentil bajo de referencia.

    Selecciona ``PRICE_EXHAUSTION_SCORE <= 0.10``. Los valores ``NaN`` se
    consideran ``False``.
    """
    mascara = tabla_percentil["PRICE_EXHAUSTION_SCORE"] <= 0.10
    return mascara.fillna(False).astype(bool)


def baseline_short_pressure(tabla_percentil: pd.DataFrame) -> pd.Series:
    """Baseline 4: short pressure en el percentil alto de referencia.

    Selecciona ``SHORT_PRESSURE_SCORE >= 0.90``. Los valores ``NaN`` se
    consideran ``False``.
    """
    mascara = tabla_percentil["SHORT_PRESSURE_SCORE"] >= 0.90
    return mascara.fillna(False).astype(bool)


def baseline_combo_ingenuo(tabla_percentil: pd.DataFrame) -> pd.Series:
    """Baseline 6: combinación ingenua de short pressure, agotamiento y confirmación A.

    Selecciona las filas que cumplen simultáneamente:

    * ``SHORT_PRESSURE_SCORE >= 0.90``
    * ``PRICE_EXHAUSTION_SCORE <= 0.10``
    * ``confirmacion_a == True``

    Un ``NaN``/``pd.NA`` en cualquiera de las tres columnas se interpreta
    como ``False`` para esa fila.
    """
    short_pressure = tabla_percentil["SHORT_PRESSURE_SCORE"] >= 0.90
    price_exhaustion = tabla_percentil["PRICE_EXHAUSTION_SCORE"] <= 0.10
    confirmacion_a = tabla_percentil["confirmacion_a"] == True  # noqa: E712

    mascara = (
        short_pressure.fillna(False).astype(bool)
        & price_exhaustion.fillna(False).astype(bool)
        & confirmacion_a.fillna(False).astype(bool)
    )
    return mascara.astype(bool)

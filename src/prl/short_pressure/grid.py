from __future__ import annotations

import itertools
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Grilla fija declarada en el pre-registro (EXP-004).
# ---------------------------------------------------------------------------

UMBRALES_SHORT_PRESSURE: list[float] = [0.75, 0.80, 0.85, 0.90, 0.95]
UMBRALES_PRICE_EXHAUSTION: list[float] = [0.05, 0.10, 0.15, 0.20]

# 7 configuraciones, en el orden exacto del pre-registro:
# "ninguna, A, A+C, A+B, A+D, A+E, A+B+C+D+E".
CONFIRMACIONES: list[tuple[str, ...]] = [
    (),
    ("a",),
    ("a", "c"),
    ("a", "b"),
    ("a", "d"),
    ("a", "e"),
    ("a", "b", "c", "d", "e"),
]


def _escala(umbral: float) -> int:
    """Convierte un umbral ``0.xx`` a su entero porcentual (``0.90`` -> ``90``).

    ``round`` explícito para evitar artefactos de representación binaria
    (``int(0.85 * 100)`` puede dar ``84`` por truncamiento de ``84.999...``).
    """

    return int(round(umbral * 100))


def _sufijo_confirmaciones(confirmaciones: tuple[str, ...]) -> str:
    """Sufijo textual para ``variant_id``: letras concatenadas o ``ninguna``."""

    return "".join(confirmaciones) if confirmaciones else "ninguna"


def build_grid() -> list[dict[str, Any]]:
    """Construye la grilla fija de variantes de EXP-004.

    Producto cartesiano ``itertools.product(UMBRALES_SHORT_PRESSURE,
    UMBRALES_PRICE_EXHAUSTION, CONFIRMACIONES)``, con short pressure como
    dimensión más significativa y la confirmación como la menos significativa.

    Devuelve 140 variantes (``5 * 4 * 7``), cada una con las claves
    ``variant_id``, ``umbral_short_pressure``, ``umbral_price_exhaustion``
    y ``confirmaciones``.
    """

    variantes: list[dict[str, Any]] = []

    for (
        umbral_short_pressure,
        umbral_price_exhaustion,
        confirmaciones,
    ) in itertools.product(
        UMBRALES_SHORT_PRESSURE,
        UMBRALES_PRICE_EXHAUSTION,
        CONFIRMACIONES,
    ):
        variant_id = (
            f"sp{_escala(umbral_short_pressure)}"
            f"_pe{_escala(umbral_price_exhaustion)}"
            f"_conf{_sufijo_confirmaciones(confirmaciones)}"
        )

        variantes.append(
            {
                "variant_id": variant_id,
                "umbral_short_pressure": umbral_short_pressure,
                "umbral_price_exhaustion": umbral_price_exhaustion,
                "confirmaciones": confirmaciones,
            }
        )

    return variantes


def _bool_serie(mascara: pd.Series) -> pd.Series:
    """Normaliza una máscara a ``bool`` con ``NaN``/``pd.NA`` -> ``False``."""

    # ``fillna(False)`` convierte tanto ``np.nan`` como ``pd.NA`` (dtype
    # nullable) en ``False``; ``astype(bool)`` deja la serie estrictamente
    # booleana (nunca object/float).
    return mascara.fillna(False).astype(bool)


def aplicar_bucket(
    variant: dict[str, Any], tabla_percentil: pd.DataFrame
) -> pd.Series:
    """Aplica una variante de la grilla a una tabla percentil cross-sectional.

    Una fila es señal si se cumplen todas las condiciones:

    * ``SHORT_PRESSURE_SCORE >= umbral_short_pressure`` (inclusive)
    * ``PRICE_EXHAUSTION_SCORE <= umbral_price_exhaustion`` (inclusive)
    * para cada letra requerida, ``confirmacion_<letra> == True``

    Cualquier ``NaN``/``pd.NA`` en alguna de las columnas usadas produce
    ``False`` para esa fila, nunca una excepción.

    Devuelve una ``pd.Series`` booleana con el mismo índice que
    ``tabla_percentil``.
    """

    sp = tabla_percentil["SHORT_PRESSURE_SCORE"]
    pe = tabla_percentil["PRICE_EXHAUSTION_SCORE"]

    mascara = sp.ge(variant["umbral_short_pressure"]) & pe.le(
        variant["umbral_price_exhaustion"]
    )

    for letra in variant["confirmaciones"]:
        columna = f"confirmacion_{letra}"
        mascara = mascara & tabla_percentil[columna].eq(True)

    return _bool_serie(mascara)

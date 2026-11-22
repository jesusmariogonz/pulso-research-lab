from __future__ import annotations

import itertools
from typing import Any


UMBRALES: list[float] = [0.60, 0.75, 0.90]


def direccion_features(
    discriminacion: "pd.DataFrame",
    features: list[str],
) -> dict[str, str]:
    """Determina si cada feature es favorable en valores altos o bajos."""
    direcciones: dict[str, str] = {}
    for feature in features:
        diferencia = discriminacion.loc[feature, "diferencia_medianas"]
        direcciones[feature] = "alto" if diferencia > 0 else "bajo"
    return direcciones


def build_grid(
    features_ordenadas: list[str],
    direcciones: dict[str, str],
) -> list[dict[str, Any]]:
    """Construye todas las variantes de bucket para las features ordenadas."""
    if not features_ordenadas:
        return []

    variantes: list[dict[str, Any]] = []

    for combinacion in itertools.product(*([UMBRALES] * len(features_ordenadas))):
        umbrales: dict[str, dict[str, Any]] = {}
        for feature, percentil in zip(features_ordenadas, combinacion):
            umbrales[feature] = {
                "direccion": direcciones[feature],
                "percentil": percentil,
            }

        variant_id = "|".join(
            f"{feature}:{direcciones[feature]}:{percentil:.2f}"
            for feature, percentil in zip(features_ordenadas, combinacion)
        )

        variantes.append(
            {
                "variant_id": variant_id,
                "umbrales": umbrales,
            }
        )

    return variantes


def aplicar_bucket(
    variant: dict[str, Any],
    features_percentil: "pd.DataFrame",
) -> "pd.Series":
    """Aplica un bucket como AND de sus condiciones de percentil."""
    condiciones = []

    for feature, info in variant["umbrales"].items():
        valores = features_percentil[feature]

        if info["direccion"] == "alto":
            condicion = valores >= info["percentil"]
        else:
            condicion = valores <= (1 - info["percentil"])

        condiciones.append(condicion)

    if not condiciones:
        return features_percentil.index.to_series().notna()

    resultado = condiciones[0]
    for condicion in condiciones[1:]:
        resultado = resultado & condicion

    return resultado

from __future__ import annotations

from itertools import product
from typing import Any

_WEIGHTS = ["equal", "tvc2"]
_THETAS = [0.5, 1.0, 1.5]
_KS = [2, 3, 5]
_MS = [5, 10, 20]
_DESTINATIONS = ["TLT", "CASH", "MIX"]

_DIMENSION_NAMES = [
    "trend",
    "vol",
    "correlation",
    "credit",
    "breadth",
    "drawdown_velocity",
]


def build_grid() -> list[dict[str, Any]]:
    """Devuelve las 162 variantes del pre-registro en orden determinista."""
    grid: list[dict[str, Any]] = []
    for weights, theta, k, m, destination in product(
        _WEIGHTS, _THETAS, _KS, _MS, _DESTINATIONS
    ):
        variant: dict[str, Any] = {
            "variant_id": f"{weights}|{theta}|{k}|{m}|{destination}",
            "weights": weights,
            "theta": theta,
            "k": k,
            "m": m,
            "destination": destination,
        }
        grid.append(variant)
    return grid


def dimension_weights(name: str) -> dict[str, float]:
    """Pesos de las dimensiones de estrés para una configuración dada."""
    if name == "equal":
        return {dim: 1.0 for dim in _DIMENSION_NAMES}
    if name == "tvc2":
        weights = {dim: 1.0 for dim in _DIMENSION_NAMES}
        weights["trend"] = 2.0
        weights["vol"] = 2.0
        weights["credit"] = 2.0
        return weights
    raise ValueError(f"Unknown dimension weights configuration: {name!r}")


def destination_weights(dest: str) -> dict[str, float]:
    """Pesos del activo refugio para cada destino permitido."""
    if dest == "TLT":
        return {"TLT": 1.0}
    if dest == "CASH":
        return {"CASH": 1.0}
    if dest == "MIX":
        return {"TLT": 0.5, "CASH": 0.5}
    raise ValueError(f"Unknown destination: {dest!r}")

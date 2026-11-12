from __future__ import annotations

from itertools import product
from typing import Any


def construccion_parametros() -> list[tuple[str, float | None]]:
    """Devuelve las 8 combinaciones fijas de método de construcción y parámetro."""
    return [
        ("equal", None),
        ("inv_vol", None),
        ("vol_target", 0.10),
        ("vol_target", 0.15),
        ("vol_target", 0.20),
        ("kelly_frac", 0.25),
        ("kelly_frac", 0.50),
        ("kelly_frac", 1.00),
    ]


def cash_politicas() -> list[str]:
    """Devuelve las políticas de cash en el orden del pre-registro."""
    return ["cash_0", "cash_5", "cash_10", "cash_20", "cash_dinamico"]


def build_grid() -> list[dict[str, Any]]:
    """Construye las 17 280 variantes exactas de la grilla de EXP-002."""
    grid: list[dict[str, Any]] = []

    for (
        l_meses,
        w_dias,
        b_dias,
        v_dias,
        (construccion, construccion_param),
        cash_politica,
        leverage,
        spread,
        k,
    ) in product(
        [3, 6, 12],
        [50, 100, 200],
        [55, 252],
        [20, 60],
        construccion_parametros(),
        cash_politicas(),
        [1.0, 1.5, 2.0],
        [0.01, 0.02],
        [0.5, 0.75],
    ):
        variant_id = "|".join(
            [
                str(l_meses),
                str(w_dias),
                str(b_dias),
                str(v_dias),
                f"{construccion}:{construccion_param}",
                cash_politica,
                str(leverage),
                str(spread),
                str(k),
            ]
        )

        grid.append(
            {
                "variant_id": variant_id,
                "L_meses": l_meses,
                "W_dias": w_dias,
                "B_dias": b_dias,
                "V_dias": v_dias,
                "construccion": construccion,
                "construccion_param": construccion_param,
                "cash_politica": cash_politica,
                "leverage": leverage,
                "spread": spread,
                "k": k,
            }
        )

    return grid

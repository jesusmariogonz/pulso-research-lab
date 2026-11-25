import numpy as np
import pandas as pd
import pytest

from prl.short_pressure.grid import (
    CONFIRMACIONES,
    UMBRALES_PRICE_EXHAUSTION,
    UMBRALES_SHORT_PRESSURE,
    aplicar_bucket,
    build_grid,
)


def test_build_grid_140_variantes_unicas():
    grid = build_grid()
    assert len(grid) == 140
    ids = [v["variant_id"] for v in grid]
    assert len(set(ids)) == 140


def test_build_grid_primer_y_ultimo_elemento():
    grid = build_grid()
    primero = grid[0]
    assert primero["umbral_short_pressure"] == pytest.approx(0.75)
    assert primero["umbral_price_exhaustion"] == pytest.approx(0.05)
    assert primero["confirmaciones"] == ()

    ultimo = grid[-1]
    assert ultimo["umbral_short_pressure"] == pytest.approx(0.95)
    assert ultimo["umbral_price_exhaustion"] == pytest.approx(0.20)
    assert ultimo["confirmaciones"] == ("a", "b", "c", "d", "e")


def test_umbrales_y_confirmaciones_constantes():
    assert UMBRALES_SHORT_PRESSURE == [0.75, 0.80, 0.85, 0.90, 0.95]
    assert UMBRALES_PRICE_EXHAUSTION == [0.05, 0.10, 0.15, 0.20]
    assert CONFIRMACIONES == [(), ("a",), ("a", "c"), ("a", "b"), ("a", "d"), ("a", "e"), ("a", "b", "c", "d", "e")]


def _tabla():
    return pd.DataFrame({
        "SHORT_PRESSURE_SCORE": [0.95, 0.80, 0.70, np.nan, 0.90],
        "PRICE_EXHAUSTION_SCORE": [0.05, 0.10, 0.50, 0.05, 0.05],
        "confirmacion_a": [True, False, True, True, True],
        "confirmacion_b": [True, True, False, True, True],
        "confirmacion_c": [True, True, True, True, True],
        "confirmacion_d": [True, True, True, True, True],
        "confirmacion_e": [True, True, True, True, True],
    }, index=["AAA", "BBB", "CCC", "DDD", "EEE"])


def test_aplicar_bucket_sin_confirmaciones():
    variant = {"umbral_short_pressure": 0.80, "umbral_price_exhaustion": 0.10, "confirmaciones": ()}
    r = aplicar_bucket(variant, _tabla())
    # AAA, BBB (límite inclusivo en ambos umbrales) y EEE pasan el filtro de
    # score; CCC falla por SHORT_PRESSURE_SCORE y DDD por NaN.
    assert list(r[r].index) == ["AAA", "BBB", "EEE"]


def test_aplicar_bucket_una_confirmacion():
    variant = {"umbral_short_pressure": 0.80, "umbral_price_exhaustion": 0.10, "confirmaciones": ("a",)}
    r = aplicar_bucket(variant, _tabla())
    # BBB pasa el filtro de score pero confirmacion_a es False.
    assert list(r[r].index) == ["AAA", "EEE"]


def test_aplicar_bucket_todas_confirmaciones_y_nan():
    variant = {"umbral_short_pressure": 0.80, "umbral_price_exhaustion": 0.10, "confirmaciones": ("a", "b", "c", "d", "e")}
    r = aplicar_bucket(variant, _tabla())
    # BBB falla confirmacion_a, CCC falla confirmacion_b y SHORT_PRESSURE_SCORE.
    assert list(r[r].index) == ["AAA", "EEE"]
    assert r.loc["DDD"] == False  # SHORT_PRESSURE_SCORE NaN -> False, nunca excepción

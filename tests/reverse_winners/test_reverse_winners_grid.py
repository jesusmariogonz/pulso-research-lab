import pandas as pd
import pytest

from prl.reverse_winners import grid


def test_direccion_features_basico():
    disc = pd.DataFrame(
        {"diferencia_medianas": [0.1, -0.2, 0.0]},
        index=["A", "B", "C"],
    )
    out = grid.direccion_features(disc, ["A", "B", "C"])
    assert out == {"A": "alto", "B": "bajo", "C": "bajo"}


def test_build_grid_vacio():
    assert grid.build_grid([], {}) == []


def test_build_grid_dos_features_orden_y_contenido():
    direcciones = {"A": "alto", "B": "bajo"}
    variantes = grid.build_grid(["A", "B"], direcciones)
    assert len(variantes) == 9
    ids = [v["variant_id"] for v in variantes]
    assert len(set(ids)) == 9

    primero = variantes[0]
    assert primero["variant_id"] == "A:alto:0.60|B:bajo:0.60"
    assert primero["umbrales"] == {
        "A": {"direccion": "alto", "percentil": 0.60},
        "B": {"direccion": "bajo", "percentil": 0.60},
    }

    segundo = variantes[1]
    assert segundo["umbrales"]["A"]["percentil"] == 0.60
    assert segundo["umbrales"]["B"]["percentil"] == 0.75

    ultimo = variantes[-1]
    assert ultimo["umbrales"]["A"]["percentil"] == 0.90
    assert ultimo["umbrales"]["B"]["percentil"] == 0.90


def test_build_grid_cinco_features_243():
    features = ["A", "B", "C", "D", "E"]
    direcciones = {f: "alto" for f in features}
    variantes = grid.build_grid(features, direcciones)
    assert len(variantes) == 243
    ids = {v["variant_id"] for v in variantes}
    assert len(ids) == 243


def test_aplicar_bucket_and_dos_features():
    df = pd.DataFrame(
        {
            "A": [0.90, 0.80, 0.70, 0.60, float("nan")],
            "B": [0.10, 0.50, 0.20, 0.90, 0.10],
        },
        index=["s1", "s2", "s3", "s4", "s5"],
    )
    variant = {
        "umbrales": {
            "A": {"direccion": "alto", "percentil": 0.75},
            "B": {"direccion": "bajo", "percentil": 0.60},
        }
    }
    seleccion = grid.aplicar_bucket(variant, df)
    # A>=0.75: s1(0.90), s2(0.80). B<=0.40: s1(0.10), s3(0.20), s5(0.10).
    # AND: solo s1.
    assert seleccion.loc["s1"] == True  # noqa: E712
    assert seleccion.loc["s2"] == False  # noqa: E712
    assert seleccion.loc["s3"] == False  # noqa: E712
    assert seleccion.loc["s4"] == False  # noqa: E712
    assert seleccion.loc["s5"] == False  # noqa: E712 (NaN en A)


def test_aplicar_bucket_sin_umbrales_selecciona_todos():
    df = pd.DataFrame({"A": [0.1, 0.9]}, index=["s1", "s2"])
    seleccion = grid.aplicar_bucket({"umbrales": {}}, df)
    assert bool(seleccion.loc["s1"]) is True
    assert bool(seleccion.loc["s2"]) is True

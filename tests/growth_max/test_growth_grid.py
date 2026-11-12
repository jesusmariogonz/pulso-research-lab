from prl.growth_max.grid import build_grid, cash_politicas, construccion_parametros


def test_construccion_parametros_exacto():
    assert construccion_parametros() == [
        ("equal", None),
        ("inv_vol", None),
        ("vol_target", 0.10),
        ("vol_target", 0.15),
        ("vol_target", 0.20),
        ("kelly_frac", 0.25),
        ("kelly_frac", 0.50),
        ("kelly_frac", 1.00),
    ]


def test_cash_politicas_exacto():
    assert cash_politicas() == ["cash_0", "cash_5", "cash_10", "cash_20", "cash_dinamico"]


def test_build_grid_tiene_17280_elementos():
    grid = build_grid()
    assert len(grid) == 17280


def test_variant_ids_unicos():
    grid = build_grid()
    ids = [v["variant_id"] for v in grid]
    assert len(set(ids)) == len(grid)


def test_cada_combinacion_aparece_exactamente_una_vez():
    grid = build_grid()
    objetivo = {
        "L_meses": 6,
        "W_dias": 100,
        "B_dias": 252,
        "V_dias": 20,
        "construccion": "kelly_frac",
        "construccion_param": 0.5,
        "cash_politica": "cash_dinamico",
        "leverage": 1.5,
        "spread": 0.02,
        "k": 0.75,
    }
    coincidencias = [v for v in grid if all(v[clave] == valor for clave, valor in objetivo.items())]
    assert len(coincidencias) == 1


def test_primer_y_ultimo_elemento():
    grid = build_grid()
    primero = grid[0]
    assert primero["L_meses"] == 3
    assert primero["W_dias"] == 50
    assert primero["B_dias"] == 55
    assert primero["V_dias"] == 20
    assert primero["construccion"] == "equal"
    assert primero["construccion_param"] is None
    assert primero["cash_politica"] == "cash_0"
    assert primero["leverage"] == 1.0
    assert primero["spread"] == 0.01
    assert primero["k"] == 0.5

    ultimo = grid[-1]
    assert ultimo["L_meses"] == 12
    assert ultimo["W_dias"] == 200
    assert ultimo["B_dias"] == 252
    assert ultimo["V_dias"] == 60
    assert ultimo["construccion"] == "kelly_frac"
    assert ultimo["construccion_param"] == 1.00
    assert ultimo["cash_politica"] == "cash_dinamico"
    assert ultimo["leverage"] == 2.0
    assert ultimo["spread"] == 0.02
    assert ultimo["k"] == 0.75

"""Pruebas del motor de paper trading de EXP-005, con datos SINTÉTICOS.

`detectar_senales` se compara contra una llamada directa a
`grid.aplicar_bucket` sobre la misma tabla normalizada (no basta con
verificar que devuelva "algo"). El resto de las pruebas son del motor de
cartera (`step_diario` y sus helpers), que no toca archivos ni depende de
`forward_runner` — son unidades independientes y deterministas.
"""
import pandas as pd
import pytest

from prl.reverse_winners import features, grid, paper_portfolio as pp


BUCKET = {
    "umbrales": {
        "f1": {"direccion": "alto", "percentil": 0.80},
    }
}


def test_detectar_senales_coincide_con_aplicar_bucket_directo():
    tabla = {
        "AAA": pd.Series({"f1": 1.0, "f2": 0.1}),
        "BBB": pd.Series({"f1": 5.0, "f2": 0.2}),
        "CCC": pd.Series({"f1": 10.0, "f2": 0.3}),
        "DDD": pd.Series({"f1": 20.0, "f2": 0.4}),
        "EEE": pd.Series({"f1": 30.0, "f2": 0.5}),
    }
    esperado_cruda = pd.DataFrame(tabla).T.sort_index()
    esperado_norm = features.normalizar_percentil_cross_sectional(esperado_cruda)
    mask_esperada = grid.aplicar_bucket(BUCKET, esperado_norm)
    tickers_esperados = sorted(esperado_cruda.index[mask_esperada.to_numpy()])

    assert pp.detectar_senales(tabla, BUCKET) == tickers_esperados
    # rank(pct=True) sobre 5 valores: [0.2, 0.4, 0.6, 0.8, 1.0]; >= 0.80 incluye el umbral mismo.
    assert tickers_esperados == ["DDD", "EEE"]


def test_detectar_senales_tabla_vacia():
    assert pp.detectar_senales({}, BUCKET) == []


def test_inicializar_estado_cartera_vacia():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    assert estado["efectivo"] == 1000.0
    assert estado["posiciones_abiertas"] == []
    assert estado["posiciones_cerradas"] == []
    assert estado["historial_diario"] == []


def test_step_sin_senales_no_abre_nada_y_registra_equity_plana():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(estado, "2026-11-24", step_actual=1, precios_cierre={}, tickers_nuevos=[])

    assert estado["efectivo"] == 1000.0
    assert estado["posiciones_abiertas"] == []
    assert len(estado["historial_diario"]) == 1
    assert estado["historial_diario"][0]["equity"] == 1000.0
    assert estado["historial_diario"][0]["cumulative_return_pct"] == 0.0
    assert estado["historial_diario"][0]["drawdown_pct"] == 0.0


def test_step_con_una_senal_invierte_todo_el_efectivo():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(
        estado, "2026-11-24", step_actual=1, precios_cierre={"AAA": 10.0}, tickers_nuevos=["AAA"]
    )

    assert estado["efectivo"] == 0.0
    assert len(estado["posiciones_abiertas"]) == 1
    pos = estado["posiciones_abiertas"][0]
    assert pos["ticker"] == "AAA"
    assert pos["dolares_invertidos"] == 1000.0
    assert pos["entry_price"] == 10.0
    assert pos["entry_step"] == 1
    # Equity no cambia el mismo día de entrada (se compra al cierre de ese día).
    assert estado["historial_diario"][-1]["equity"] == pytest.approx(1000.0)


def test_dos_senales_mismo_dia_reparten_efectivo_en_partes_iguales():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(
        estado, "2026-11-24", step_actual=1,
        precios_cierre={"AAA": 10.0, "BBB": 50.0}, tickers_nuevos=["AAA", "BBB"],
    )
    assert estado["efectivo"] == 0.0
    montos = sorted(p["dolares_invertidos"] for p in estado["posiciones_abiertas"])
    assert montos == pytest.approx([500.0, 500.0])


def test_mark_to_market_entre_entrada_y_salida():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(estado, "d1", 1, {"AAA": 10.0}, ["AAA"])
    # El precio sube 20% al día siguiente, todavía dentro del horizonte.
    estado = pp.step_diario(estado, "d2", 2, {"AAA": 12.0}, [])

    assert estado["posiciones_abiertas"][0]["ultimo_precio_conocido"] == 12.0
    assert estado["historial_diario"][-1]["equity"] == pytest.approx(1200.0)
    assert estado["historial_diario"][-1]["cumulative_return_pct"] == pytest.approx(20.0)


def test_posicion_se_liquida_exactamente_al_cumplir_el_horizonte():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(estado, "d0", 0, {"AAA": 10.0}, ["AAA"], horizonte_sesiones=3)
    estado = pp.step_diario(estado, "d1", 1, {"AAA": 11.0}, [], horizonte_sesiones=3)
    estado = pp.step_diario(estado, "d2", 2, {"AAA": 11.0}, [], horizonte_sesiones=3)
    assert len(estado["posiciones_abiertas"]) == 1  # 2 - 0 = 2 < 3, sigue abierta

    estado = pp.step_diario(estado, "d3", 3, {"AAA": 12.0}, [], horizonte_sesiones=3)
    assert estado["posiciones_abiertas"] == []
    assert len(estado["posiciones_cerradas"]) == 1
    cerrada = estado["posiciones_cerradas"][0]
    assert cerrada["exit_fecha"] == "d3"
    assert cerrada["exit_price"] == 12.0
    assert cerrada["pnl_pct"] == pytest.approx(0.2)
    assert estado["efectivo"] == pytest.approx(1200.0)
    assert estado["historial_diario"][-1]["equity"] == pytest.approx(1200.0)


def test_capital_liberado_al_vencer_financia_senales_del_mismo_dia():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(estado, "d0", 0, {"AAA": 10.0}, ["AAA"], horizonte_sesiones=1)
    # Al día siguiente AAA vence (step 1 - entry_step 0 >= 1) y BBB da señal nueva
    # el mismo día: el efectivo liberado por AAA debe financiar a BBB.
    estado = pp.step_diario(estado, "d1", 1, {"AAA": 10.0, "BBB": 20.0}, ["BBB"], horizonte_sesiones=1)

    assert estado["posiciones_cerradas"][0]["ticker"] == "AAA"
    assert len(estado["posiciones_abiertas"]) == 1
    assert estado["posiciones_abiertas"][0]["ticker"] == "BBB"
    assert estado["posiciones_abiertas"][0]["dolares_invertidos"] == pytest.approx(1000.0)
    assert estado["efectivo"] == 0.0


def test_sin_efectivo_disponible_no_abre_posiciones_nuevas():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(estado, "d0", 0, {"AAA": 10.0}, ["AAA"], horizonte_sesiones=30)
    # Ya no queda efectivo: una señal nueva al día siguiente no debe abrir nada.
    estado = pp.step_diario(estado, "d1", 1, {"AAA": 10.0, "BBB": 20.0}, ["BBB"], horizonte_sesiones=30)

    tickers_abiertos = [p["ticker"] for p in estado["posiciones_abiertas"]]
    assert tickers_abiertos == ["AAA"]
    assert estado["efectivo"] == 0.0


def test_mismo_ticker_senal_dos_dias_seguidos_abre_dos_posiciones_independientes():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(estado, "d0", 0, {"AAA": 10.0}, ["AAA"], horizonte_sesiones=30)
    # AAA vuelve a dar señal al día siguiente mientras sigue abierta — pero ya
    # no hay efectivo (caso realista); se fuerza efectivo disponible para
    # aislar el comportamiento de "no deduplicar por ticker".
    estado = {**estado, "efectivo": 500.0}
    estado = pp.step_diario(estado, "d1", 1, {"AAA": 11.0}, ["AAA"], horizonte_sesiones=30)

    tickers = [p["ticker"] for p in estado["posiciones_abiertas"]]
    assert tickers == ["AAA", "AAA"]
    assert estado["posiciones_abiertas"][0]["entry_step"] == 0
    assert estado["posiciones_abiertas"][1]["entry_step"] == 1


def test_drawdown_pct_tras_un_pico_y_una_caida():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(estado, "d0", 0, {"AAA": 10.0}, ["AAA"], horizonte_sesiones=30)
    estado = pp.step_diario(estado, "d1", 1, {"AAA": 20.0}, [], horizonte_sesiones=30)  # pico: equity 2000
    estado = pp.step_diario(estado, "d2", 2, {"AAA": 15.0}, [], horizonte_sesiones=30)  # cae a 1500

    assert estado["pico_equity"] == pytest.approx(2000.0)
    assert estado["historial_diario"][-1]["equity"] == pytest.approx(1500.0)
    assert estado["historial_diario"][-1]["drawdown_pct"] == pytest.approx(-25.0)


def test_precio_faltante_usa_el_ultimo_precio_conocido_para_marcar_y_liquidar():
    estado = pp.inicializar_estado("2026-11-23", 1000.0)
    estado = pp.step_diario(estado, "d0", 0, {"AAA": 10.0}, ["AAA"], horizonte_sesiones=2)
    # Falta el precio de AAA este día (hueco de datos): se usa el último conocido.
    estado = pp.step_diario(estado, "d1", 1, {}, [], horizonte_sesiones=2)
    assert estado["posiciones_abiertas"][0]["ultimo_precio_conocido"] == 10.0
    assert estado["historial_diario"][-1]["equity"] == pytest.approx(1000.0)

    # Vence sin precio disponible tampoco: se liquida al último conocido y se marca.
    estado = pp.step_diario(estado, "d2", 2, {}, [], horizonte_sesiones=2)
    assert estado["posiciones_abiertas"] == []
    cerrada = estado["posiciones_cerradas"][0]
    assert cerrada["exit_fecha"] == "d2"
    assert cerrada["exit_price"] == 10.0
    assert cerrada["exit_price_estimado"] is True
    assert cerrada["pnl"] == pytest.approx(0.0)

"""Motor de paper trading real para el bucket CONGELADO de EXP-005.

Distinto de `forward_validation`/`forward_runner` (que miden, de forma
agregada, si el retorno de 30 sesiones del bucket le gana a los baselines):
este módulo simula una cartera virtual día a día — efectivo, posiciones
abiertas/cerradas y una curva de equity — para poder verla con el mismo
nivel de detalle que un motor de trading real (capital, equity, retorno,
drawdown). Nunca reoptimiza el bucket ni cambia sus umbrales.

Reglas de construcción de cartera (NUEVAS respecto a la validación
original — EXP-005 solo midió el retorno agregado de 30 sesiones de las
señales, nunca una cartera con capital; estas reglas son necesarias para
poder "verla operar" y se documentan aparte para no hacerlas pasar como
parte de lo ya validado):

- Horizonte de tenencia: 30 SESIONES de mercado (no 30 días calendario) —
  el mismo horizonte que `exp005.retorno_forward`/`forward_runner` miden,
  contado en pasos del calendario que procesa este motor, no en fechas.
- Entrada: al cierre del día en que un símbolo satisface el bucket. Un
  mismo símbolo puede volver a dar señal en días consecutivos mientras
  siga calificando (igual que en la validación: cada (fecha, ticker) es
  una señal independiente, no se deduplica) — eso abre una posición
  NUEVA e independiente, no amplía la anterior.
- Tamaño de posición: el efectivo disponible ese día se reparte en
  partes iguales entre las señales nuevas de ese día. Si no alcanza el
  efectivo (cartera ya totalmente invertida), no se abren posiciones
  nuevas hasta que madure alguna y libere capital.
- Salida: al cumplirse el horizonte, se liquida al precio de cierre
  ajustado de esa fecha (o el último precio conocido, si falta ese día
  puntual — se marca `precio_cierre_estimado` en ese caso).
- Sin stop-loss ni control de riesgo por posición: la validación
  original tampoco los tenía (midió el retorno crudo a 30 sesiones), así
  que agregar uno aquí sería una regla no probada.

Todos los precios son cierres AJUSTADOS (`exp005.ajustar_ohlc`), igual que
en `forward_runner`, para que la detección de señales y el P&L usen la
misma convención.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from prl.reverse_winners import features, grid


def detectar_senales(
    tabla_features_hoy: dict[str, "pd.Series"],
    bucket_congelado: dict,
) -> list[str]:
    """Tickers que satisfacen `bucket_congelado` en una fecha de corte.

    `tabla_features_hoy` es `{ticker: fila_de_features}` para TODOS los
    símbolos elegibles en esa fecha (ya filtrados por historia mínima y
    sin NaN) — el mismo insumo que arma `forward_runner` antes de llamar
    a `grid.aplicar_bucket`, pero sin requerir retorno forward (esta
    función no lo necesita: solo detecta, no evalúa resultado).

    No tiene side effects ni lee archivos: así se puede probar con datos
    sintéticos sin fixtures de parquet.
    """
    if not tabla_features_hoy:
        return []

    tabla_cruda = pd.DataFrame(tabla_features_hoy).T.sort_index()
    tabla_norm = features.normalizar_percentil_cross_sectional(tabla_cruda)
    seleccion = grid.aplicar_bucket(bucket_congelado, tabla_norm)

    index = tabla_cruda.index
    valores = seleccion.to_numpy() if isinstance(seleccion, pd.Series) else seleccion
    return sorted(str(t) for t in index[valores])


def inicializar_estado(fecha_inicio: str, capital_inicial: float) -> dict[str, Any]:
    """Cartera vacía: todo en efectivo, sin historial todavía."""
    return {
        "fecha_inicio": str(fecha_inicio),
        "capital_inicial": float(capital_inicial),
        "efectivo": float(capital_inicial),
        "posiciones_abiertas": [],
        "posiciones_cerradas": [],
        "historial_diario": [],
        "pico_equity": float(capital_inicial),
    }


def _cerrar_posiciones_vencidas(
    estado: dict[str, Any],
    fecha: str,
    step_actual: int,
    precios_cierre: dict[str, float],
    horizonte_sesiones: int,
) -> dict[str, Any]:
    """Liquida las posiciones con `step_actual - entry_step >= horizonte_sesiones`."""
    siguen_abiertas = []
    cerradas_nuevas = []
    efectivo = estado["efectivo"]

    for pos in estado["posiciones_abiertas"]:
        if step_actual - pos["entry_step"] < horizonte_sesiones:
            siguen_abiertas.append(pos)
            continue

        precio_salida = precios_cierre.get(pos["ticker"], pos["ultimo_precio_conocido"])
        precio_estimado = pos["ticker"] not in precios_cierre
        valor_salida = pos["dolares_invertidos"] * (precio_salida / pos["entry_price"])
        efectivo += valor_salida
        cerradas_nuevas.append(
            {
                **pos,
                "exit_fecha": fecha,
                "exit_step": step_actual,
                "exit_price": precio_salida,
                "exit_price_estimado": precio_estimado,
                "valor_salida": valor_salida,
                "pnl": valor_salida - pos["dolares_invertidos"],
                "pnl_pct": (precio_salida / pos["entry_price"]) - 1.0,
            }
        )

    return {
        **estado,
        "efectivo": efectivo,
        "posiciones_abiertas": siguen_abiertas,
        "posiciones_cerradas": estado["posiciones_cerradas"] + cerradas_nuevas,
    }


def _abrir_posiciones_nuevas(
    estado: dict[str, Any],
    fecha: str,
    step_actual: int,
    tickers_nuevos: list[str],
    precios_cierre: dict[str, float],
) -> dict[str, Any]:
    """Reparte el efectivo disponible en partes iguales entre `tickers_nuevos`.

    Ignora silenciosamente un ticker sin precio ese día (no debería pasar:
    ser señal requiere tener features ese día, que requieren precio) y no
    abre nada si no hay efectivo disponible.
    """
    tickers_validos = [t for t in tickers_nuevos if t in precios_cierre]
    if not tickers_validos or estado["efectivo"] <= 0:
        return estado

    dolares_por_posicion = estado["efectivo"] / len(tickers_validos)
    nuevas = [
        {
            "ticker": t,
            "entry_fecha": fecha,
            "entry_step": step_actual,
            "entry_price": precios_cierre[t],
            "ultimo_precio_conocido": precios_cierre[t],
            "dolares_invertidos": dolares_por_posicion,
        }
        for t in tickers_validos
    ]
    return {
        **estado,
        "efectivo": 0.0,
        "posiciones_abiertas": estado["posiciones_abiertas"] + nuevas,
    }


def _marcar_a_mercado(estado: dict[str, Any], precios_cierre: dict[str, float]) -> dict[str, Any]:
    """Actualiza `ultimo_precio_conocido` de cada posición abierta, si hay precio nuevo hoy."""
    actualizadas = [
        {**pos, "ultimo_precio_conocido": precios_cierre.get(pos["ticker"], pos["ultimo_precio_conocido"])}
        for pos in estado["posiciones_abiertas"]
    ]
    return {**estado, "posiciones_abiertas": actualizadas}


def _calcular_equity(estado: dict[str, Any]) -> float:
    valor_posiciones = sum(
        pos["dolares_invertidos"] * (pos["ultimo_precio_conocido"] / pos["entry_price"])
        for pos in estado["posiciones_abiertas"]
    )
    return estado["efectivo"] + valor_posiciones


def step_diario(
    estado: dict[str, Any],
    fecha: str,
    step_actual: int,
    precios_cierre: dict[str, float],
    tickers_nuevos: list[str],
    horizonte_sesiones: int = 30,
) -> dict[str, Any]:
    """Avanza la cartera un día de mercado: cierra vencidas, abre nuevas, registra equity.

    Orden intencional: primero se liquidan las posiciones que cumplen el
    horizonte (liberan efectivo), luego se reparte ese efectivo (más el ya
    disponible) entre las señales nuevas de hoy — así una posición que
    madura el mismo día en que hay señales nuevas sí puede financiarlas,
    en vez de quedar un día entero sin invertir de más.
    """
    estado = _cerrar_posiciones_vencidas(estado, fecha, step_actual, precios_cierre, horizonte_sesiones)
    estado = _abrir_posiciones_nuevas(estado, fecha, step_actual, tickers_nuevos, precios_cierre)
    estado = _marcar_a_mercado(estado, precios_cierre)

    equity = _calcular_equity(estado)
    pico = max(estado["pico_equity"], equity)
    drawdown_pct = (equity / pico - 1.0) if pico > 0 else 0.0

    historial = estado["historial_diario"] + [
        {
            "fecha": fecha,
            "equity": equity,
            "cumulative_return_pct": (equity / estado["capital_inicial"] - 1.0) * 100.0,
            "drawdown_pct": drawdown_pct * 100.0,
        }
    ]

    return {**estado, "pico_equity": pico, "historial_diario": historial}

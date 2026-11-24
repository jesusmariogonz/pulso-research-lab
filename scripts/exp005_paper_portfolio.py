"""Cartera virtual EN VIVO del bucket CONGELADO de EXP-005 (Reverse Winners).

    python scripts/exp005_paper_portfolio.py

Distinto de `exp005_forward_check.py` (que solo PUNTÚA retrospectivamente,
cuando ya existe el retorno forward de 30 sesiones completo): este script
mantiene una cartera con capital virtual que opera en tiempo real — abre
posiciones en cuanto ocurre una fecha de corte del mismo grid de 10
sesiones que ya usa la validación forward (`exp005.fechas_t0`), sin
esperar a poder calificarlas. Es el "Paper Lab" de EXP-005: para ver si
el bucket, llevado a una cartera, sostiene lo que mostró en el locked
test — no reemplaza esa validación estadística, la complementa.

El bucket es el mismo BUCKET_CONGELADO que `exp005_forward_check.py`
(variant_id_ganador exacto de run_real/results.json) — nunca se
reoptimiza aquí tampoco. Las reglas de construcción de cartera (capital
inicial, reparto de efectivo, horizonte de 30 sesiones) están descritas
en `prl.reverse_winners.paper_portfolio` y son NUEVAS respecto a esa
validación (que midió retorno agregado, no una cartera) — ver el
docstring de ese módulo.

Primera corrida: no hay backtest retroactivo. La cartera arranca en la
última fecha disponible del calendario al momento de esta corrida (igual
que el Motor IBKR de jesus-site arrancó con historial corto el día que
se prendió) — así el historial que se vea después es 100% forward, nunca
una simulación maquillada de "paper trading".

Corre semanalmente (domingos, después de exp005-forward-check.yml) y
bajo demanda. Cómputo puro: sin LLM, sin llaves.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from prl.reverse_winners import exp005, features, paper_portfolio as pp
from prl.reverse_winners.exp005 import ajustar_ohlc

ROOT = Path(__file__).resolve().parents[1]
INPUTS_DIR = ROOT / "data" / "raw"
UNIVERSO_PATH = ROOT / "data" / "universes" / "sp1500_short_pressure.txt"
EXP_DIR = ROOT / "experiments" / "EXP-005-reverse-winners"
RUN_DIR = EXP_DIR / "run_paper_portfolio"
ESTADO_PATH = RUN_DIR / "estado.json"
SNAPSHOT_PATH = RUN_DIR / "paper_portfolio.json"

BENCHMARK = "SPY"
CAPITAL_INICIAL = 1000.0
HORIZONTE_SESIONES = 30
GRID_PASO_SESIONES = 10
GRID_INICIO = "2010-01-01"
MIN_HISTORIA = 252

# Idéntico a BUCKET_CONGELADO de exp005_forward_check.py — una sola fuente
# de verdad duplicada a propósito en ambos scripts (son procesos
# independientes, sin import cruzado entre scripts) para que un cambio
# accidental en uno nunca se filtre al otro sin revisión explícita.
BUCKET_CONGELADO = {
    "umbrales": {
        "vol_realizada_20d": {"direccion": "alto", "percentil": 0.90},
        "drawdown_60d": {"direccion": "bajo", "percentil": 0.90},
        "dist_max20": {"direccion": "bajo", "percentil": 0.90},
        "beta_60d": {"direccion": "alto", "percentil": 0.75},
    }
}


def _leer_universo() -> list[str]:
    return [l.strip() for l in UNIVERSO_PATH.read_text().splitlines() if l.strip()]


def _cargar_datos(universo: list[str], df_bench_adj: pd.DataFrame) -> dict[str, dict]:
    """Una sola pasada por símbolo: precio ajustado + features sobre toda su historia."""
    datos: dict[str, dict] = {}
    for symbol in universo:
        ruta = INPUTS_DIR / f"{symbol}.parquet"
        if not ruta.exists():
            continue
        df_raw = pd.read_parquet(ruta).sort_index()
        df_adj = ajustar_ohlc(df_raw).sort_index()
        feat = features.calcular_features_simbolo(df_adj, df_bench_adj.reindex(df_adj.index))
        datos[symbol] = {"df_raw": df_raw, "df_adj": df_adj, "feat": feat}
    return datos


def _tabla_features_elegibles(
    datos: dict[str, dict], fecha: pd.Timestamp, min_historia: int
) -> dict[str, pd.Series]:
    """Mismo criterio de elegibilidad que forward_runner: historia mínima, sin NaN."""
    filas: dict[str, pd.Series] = {}
    for symbol, dato in datos.items():
        n_historia = int((dato["df_raw"].index <= fecha).sum())
        if n_historia < min_historia:
            continue
        feat = dato["feat"]
        if fecha not in feat.index:
            continue
        fila = feat.loc[fecha]
        if fila.isna().any():
            continue
        filas[symbol] = fila
    return filas


def _precio_en(datos: dict[str, dict], ticker: str, fecha: pd.Timestamp) -> float | None:
    dato = datos.get(ticker)
    if dato is None:
        return None
    close = dato["df_adj"]["close"]
    if fecha not in close.index:
        return None
    valor = close.loc[fecha]
    return None if pd.isna(valor) else float(valor)


def _construir_snapshot(estado: dict) -> dict:
    ultimo = estado["historial_diario"][-1] if estado["historial_diario"] else None
    return {
        "experimento": "EXP-005",
        "nombre": "Reverse Winners — Paper Portfolio",
        "bucket_congelado": BUCKET_CONGELADO,
        "horizonte_sesiones": HORIZONTE_SESIONES,
        "grid_paso_sesiones": GRID_PASO_SESIONES,
        "fecha_inicio": estado["fecha_inicio"],
        "capital_inicial": estado["capital_inicial"],
        "efectivo": round(estado["efectivo"], 2),
        "equity_actual": round(ultimo["equity"], 2) if ultimo else estado["capital_inicial"],
        "retorno_acumulado_pct": round(ultimo["cumulative_return_pct"], 2) if ultimo else 0.0,
        "drawdown_pct": round(ultimo["drawdown_pct"], 2) if ultimo else 0.0,
        "n_posiciones_abiertas": len(estado["posiciones_abiertas"]),
        "n_posiciones_cerradas": len(estado["posiciones_cerradas"]),
        "pnl_realizado_total": round(sum(p["pnl"] for p in estado["posiciones_cerradas"]), 2),
        "pnl_no_realizado_total": round(
            sum(
                p["dolares_invertidos"] * (p["ultimo_precio_conocido"] / p["entry_price"] - 1.0)
                for p in estado["posiciones_abiertas"]
            ),
            2,
        ),
        "win_rate_pct": (
            round(100.0 * sum(1 for p in estado["posiciones_cerradas"] if p["pnl"] > 0) / len(estado["posiciones_cerradas"]), 1)
            if estado["posiciones_cerradas"]
            else None
        ),
        "posiciones_abiertas": [
            {
                "ticker": p["ticker"],
                "entry_fecha": p["entry_fecha"],
                "entry_price": round(p["entry_price"], 2),
                "ultimo_precio_conocido": round(p["ultimo_precio_conocido"], 2),
                "dolares_invertidos": round(p["dolares_invertidos"], 2),
                "retorno_no_realizado_pct": round(
                    (p["ultimo_precio_conocido"] / p["entry_price"] - 1.0) * 100.0, 2
                ),
            }
            for p in estado["posiciones_abiertas"]
        ],
        "posiciones_cerradas": [
            {
                "ticker": p["ticker"],
                "entry_fecha": p["entry_fecha"],
                "entry_price": round(p["entry_price"], 2),
                "exit_fecha": p["exit_fecha"],
                "exit_price": round(p["exit_price"], 2),
                "exit_price_estimado": p["exit_price_estimado"],
                "dolares_invertidos": round(p["dolares_invertidos"], 2),
                "pnl": round(p["pnl"], 2),
                "pnl_pct": round(p["pnl_pct"] * 100.0, 2),
            }
            for p in estado["posiciones_cerradas"]
        ],
        "historial_diario": [
            {
                "fecha": h["fecha"],
                "equity": round(h["equity"], 2),
                "cumulative_return_pct": round(h["cumulative_return_pct"], 2),
                "drawdown_pct": round(h["drawdown_pct"], 2),
            }
            for h in estado["historial_diario"]
        ],
        "ultima_actualizacion": pd.Timestamp.now(tz="UTC").isoformat(),
    }


def main() -> dict:
    universo = _leer_universo()

    df_bench_raw = pd.read_parquet(INPUTS_DIR / f"{BENCHMARK}.parquet").sort_index()
    df_bench_adj = ajustar_ohlc(df_bench_raw).sort_index()
    calendario = df_bench_adj.index

    grid_cortes = exp005.fechas_t0(calendario, inicio=GRID_INICIO, paso=GRID_PASO_SESIONES)
    grid_cortes_set = set(grid_cortes)

    if ESTADO_PATH.exists():
        estado = json.loads(ESTADO_PATH.read_text())
        ultima_fecha_procesada = pd.Timestamp(estado["historial_diario"][-1]["fecha"])
        fechas_a_procesar = calendario[calendario > ultima_fecha_procesada]
    else:
        # Primera corrida: arranca HOY (última fecha disponible), sin backtest retroactivo.
        fecha_arranque = calendario[-1]
        estado = pp.inicializar_estado(str(fecha_arranque.date()), CAPITAL_INICIAL)
        fechas_a_procesar = calendario[calendario == fecha_arranque]

    if len(fechas_a_procesar) == 0:
        print("Sin fechas nuevas todavía (nada que actualizar).")
        return {"fechas_nuevas": 0}

    datos = _cargar_datos(universo, df_bench_adj)

    for fecha in fechas_a_procesar:
        step_actual = int(calendario.get_loc(fecha))

        tickers_nuevos: list[str] = []
        if fecha in grid_cortes_set:
            tabla = _tabla_features_elegibles(datos, fecha, MIN_HISTORIA)
            tickers_nuevos = pp.detectar_senales(tabla, BUCKET_CONGELADO)

        tickers_relevantes = {p["ticker"] for p in estado["posiciones_abiertas"]} | set(tickers_nuevos)
        precios_cierre = {
            t: precio
            for t in tickers_relevantes
            if (precio := _precio_en(datos, t, fecha)) is not None
        }

        estado = pp.step_diario(
            estado,
            fecha=str(fecha.date()),
            step_actual=step_actual,
            precios_cierre=precios_cierre,
            tickers_nuevos=tickers_nuevos,
            horizonte_sesiones=HORIZONTE_SESIONES,
        )

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    ESTADO_PATH.write_text(json.dumps(estado, indent=2, ensure_ascii=False, sort_keys=True))
    SNAPSHOT_PATH.write_text(
        json.dumps(_construir_snapshot(estado), indent=2, ensure_ascii=False, sort_keys=True)
    )
    print(f"Procesadas {len(fechas_a_procesar)} fecha(s) nueva(s).")
    return {"fechas_nuevas": len(fechas_a_procesar)}


if __name__ == "__main__":
    main()

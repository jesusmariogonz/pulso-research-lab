"""Chequeo periódico de la validación forward de EXP-005 (Reverse Winners).

    python scripts/exp005_forward_check.py

Plumbing puro: decide si ya existen fechas de corte nuevas con retorno de
30 días completo y, si existen, aplica el bucket CONGELADO (nunca se
reoptimiza) vía prl.reverse_winners.forward_runner, acumula el log en
run_forward/log.json vía prl.reverse_winners.forward_check, y
re-renderiza FORWARD_VALIDATION_RESULTADOS.md. Ningún cálculo numérico
vive en este archivo — todo pasa por módulos ya implementados por
DeepSeek y revisados (ver FORWARD_VALIDATION.md / FORWARD_VALIDATION_SPEC.md).

Si no hay fechas nuevas, no escribe nada y termina en silencio (código 0):
es el resultado esperado la mayoría de las veces que corre este chequeo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from prl.reverse_winners import forward_check, forward_runner

ROOT = Path(__file__).resolve().parents[1]
INPUTS_DIR = ROOT / "data" / "raw"
UNIVERSO_PATH = ROOT / "data" / "universes" / "sp1500_short_pressure.txt"
EXP_DIR = ROOT / "experiments" / "EXP-005-reverse-winners"
RUN_DIR = EXP_DIR / "run_forward"
LOG_PATH = RUN_DIR / "log.json"
REPORT_PATH = EXP_DIR / "FORWARD_VALIDATION_RESULTADOS.md"

BENCHMARK = "SPY"
ULTIMA_FECHA_ORIGINAL = pd.Timestamp("2026-09-30")

# Bucket congelado: variant_id_ganador exacto de run_real/results.json
# (EXP-005, corrida 2026-11-23). NUNCA se reoptimiza — ver FORWARD_VALIDATION.md.
BUCKET_CONGELADO = {
    "umbrales": {
        "vol_realizada_20d": {"direccion": "alto", "percentil": 0.90},
        "drawdown_60d": {"direccion": "bajo", "percentil": 0.90},
        "dist_max20": {"direccion": "bajo", "percentil": 0.90},
        "beta_60d": {"direccion": "alto", "percentil": 0.75},
    }
}

_EMOJI = {"favorable": "🟢", "inconclusa": "🟡", "negativa": "🔴"}
_NOMBRE = {
    "ganador": "Bucket (ganador)",
    "baseline_momentum_simple": "Momentum simple",
    "baseline_buy_hold": "Buy & Hold",
    "baseline_rsi_simple": "RSI simple",
    "baseline_combo_ingenuo": "Combo ingenuo",
    "spy": "SPY",
}


def _pct(x: float | None) -> str:
    return "n/d" if x is None else f"{x * 100:.2f}%"


def _num(x: float | None, decimales: int = 2) -> str:
    return "n/d" if x is None else f"{x:.{decimales}f}"


def _renderizar_reporte(m: dict) -> str:
    label = m["label"]
    mpm = m["metricas_por_metodo"]
    filas_tabla = "\n".join(
        f"| {_NOMBRE[metodo]} | {_pct(mpm[metodo]['retorno_acumulado'])} "
        f"| {_num(mpm[metodo]['sharpe'])} | {_pct(mpm[metodo]['max_drawdown'])} "
        f"| {_pct(mpm[metodo]['hit_rate'])} |"
        for metodo in ("ganador", "baseline_momentum_simple", "baseline_buy_hold",
                       "baseline_rsi_simple", "baseline_combo_ingenuo", "spy")
    )
    nota_muestra = (
        "\n> Menos de 10 fechas de corte acumuladas: muestra insuficiente para "
        "concluir nada todavía, sin importar el signo del resultado.\n"
        if m["n_fechas_acumuladas"] < 10 else ""
    )
    return f"""# Reverse Winners — Forward Validation

Generado automáticamente por `scripts/exp005_forward_check.py`. El bucket
está **congelado** (ver `FORWARD_VALIDATION.md`) — ninguna cifra de esta
página proviene de reoptimizar nada con datos nuevos.

## Hipótesis congelada

`vol_realizada_20d: alto P90 | drawdown_60d: bajo P90 | dist_max20: bajo P90 | beta_60d: alto P75`
— el bucket ganador exacto de la corrida original de EXP-005 (2026-11-23).

## Periodo forward

{ULTIMA_FECHA_ORIGINAL.date()} (exclusivo) → hoy.

## Número de señales

**{m['n_fechas_acumuladas']}** fechas de corte acumuladas · **{m['n_senales_ganador']}** señales del bucket ganador.

## Resultado acumulado

| | Retorno acumulado | Sharpe | Max Drawdown | Hit Rate |
|---|---|---|---|---|
{filas_tabla}

**Exceso de retorno vs. Momentum simple**: {_pct(m['exceso_vs_momentum'])}
**Exceso de retorno vs. SPY**: {_pct(m['exceso_vs_spy'])}
{nota_muestra}
## Conclusión

{_EMOJI[label]} **{label.upper()}**

---
*Última actualización: {pd.Timestamp.now(tz="UTC").isoformat()}*
"""


def main() -> dict:
    df_bench = pd.read_parquet(INPUTS_DIR / f"{BENCHMARK}.parquet").sort_index()
    calendario = df_bench.index

    log = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else {}

    ultima_fecha_procesada = ULTIMA_FECHA_ORIGINAL
    for entrada in log.get("ganador") or []:
        fecha = pd.Timestamp(entrada["fecha"])
        if fecha > ultima_fecha_procesada:
            ultima_fecha_procesada = fecha

    nuevas_fechas = forward_check.determinar_fechas_nuevas(
        calendario, ultima_fecha_procesada,
    )
    if not nuevas_fechas:
        print("Sin fechas nuevas todavía (nada que actualizar).")
        return {"nuevas_fechas": 0}

    nuevas_senales = forward_runner.construir_senales_para_fechas(
        INPUTS_DIR, UNIVERSO_PATH, nuevas_fechas, BUCKET_CONGELADO,
        benchmark=BENCHMARK,
    )
    log = forward_check.actualizar_log(log, nuevas_senales)

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(
        json.dumps(log, indent=2, ensure_ascii=False, sort_keys=True)
    )

    vix_path = INPUTS_DIR / "VIX.parquet"
    if vix_path.exists():
        vix_por_fecha = pd.read_parquet(vix_path).sort_index()["close"]
    else:
        vix_por_fecha = pd.Series(dtype=float)

    metricas = forward_check.calcular_metricas_reporte(
        log, vix_por_fecha, ultima_fecha_original=str(ULTIMA_FECHA_ORIGINAL.date())
    )
    REPORT_PATH.write_text(_renderizar_reporte(metricas))

    print(
        f"{len(nuevas_fechas)} fecha(s) nueva(s) procesadas. "
        f"label={metricas['label']} n_fechas_acumuladas={metricas['n_fechas_acumuladas']}"
    )
    return {"nuevas_fechas": len(nuevas_fechas), "label": metricas["label"]}


if __name__ == "__main__":
    main()

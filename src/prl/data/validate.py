"""Validación de integridad de una serie descargada. NO corrige nada:
solo detecta y reporta, para que cada hallazgo quede a la vista y el
experimento decida (y documente) qué hacer con él."""

from __future__ import annotations

import pandas as pd

# Un movimiento diario mayor a esto en un ETF/índice de precio es sospechoso
# (puede ser real: oct-1987 no está en rango, mar-2020 sí llega a -12%).
UMBRAL_RETORNO_EXTREMO = 0.25
# Más de estos días hábiles sin dato = hueco que merece atención.
UMBRAL_HUECO_DIAS_HABILES = 6
# Racha de precios idénticos consecutivos que sugiere dato rancio.
UMBRAL_RACHA_RANCIA = 5

ROLES_SIN_PRECIO_POSITIVO_ESTRICTO = {"curve", "recession_flag", "cash_rate", "yield", "credit_spread"}


def _col_precio(df: pd.DataFrame) -> str:
    for c in ("adj_close", "close", "value"):
        if c in df.columns:
            return c
    raise ValueError("la serie no tiene columna de precio/valor")


def validar_serie(df: pd.DataFrame, meta: dict) -> dict:
    hallazgos: list[dict] = []
    col = _col_precio(df)
    serie = df[col]

    def add(codigo: str, severidad: str, detalle: str):
        hallazgos.append({"codigo": codigo, "severidad": severidad, "detalle": detalle})

    if not df.index.is_monotonic_increasing:
        add("INDICE_NO_MONOTONO", "error", "las fechas no están ordenadas")
    dups = int(df.index.duplicated().sum())
    if dups:
        add("FECHAS_DUPLICADAS", "error", f"{dups} fechas repetidas")
    nulos = int(serie.isna().sum())
    if nulos:
        add("VALORES_NULOS", "aviso", f"{nulos} valores nulos en {col}")

    if meta.get("role") not in ROLES_SIN_PRECIO_POSITIVO_ESTRICTO:
        no_pos = int((serie <= 0).sum())
        if no_pos:
            add("PRECIO_NO_POSITIVO", "error", f"{no_pos} precios <= 0")

    if {"high", "low"} <= set(df.columns):
        inc = int((df["high"] < df["low"]).sum())
        if inc:
            add("HIGH_MENOR_QUE_LOW", "error", f"{inc} filas con high < low")
    if {"high", "close", "low"} <= set(df.columns):
        fuera = int(((df["close"] > df["high"] * 1.0001) | (df["close"] < df["low"] * 0.9999)).sum())
        if fuera:
            add("CIERRE_FUERA_DEL_RANGO", "aviso", f"{fuera} filas con close fuera de [low, high]")

    ret = serie.pct_change().dropna()
    if meta.get("role") not in {"curve", "recession_flag", "yield", "credit_spread", "cash_rate"}:
        extremos = ret[ret.abs() > UMBRAL_RETORNO_EXTREMO]
        if len(extremos):
            ej = ", ".join(f"{d.date()} ({v:+.0%})" for d, v in extremos.head(3).items())
            add("RETORNOS_EXTREMOS", "aviso", f"{len(extremos)} días con |retorno| > {UMBRAL_RETORNO_EXTREMO:.0%}: {ej}")

    if len(df) > 1:
        brechas = df.index.to_series().diff().dt.days.dropna()
        grandes = brechas[brechas > UMBRAL_HUECO_DIAS_HABILES * 7 / 5]
        if len(grandes):
            peor = grandes.idxmax()
            add("HUECOS", "aviso", f"{len(grandes)} huecos > {UMBRAL_HUECO_DIAS_HABILES} días hábiles; el mayor termina {peor.date()} ({int(grandes.max())} días corridos)")

    if meta.get("role") not in {"recession_flag", "curve", "yield", "credit_spread", "cash_rate"}:
        igual = (serie.diff() == 0).astype(int)
        racha = igual.groupby((igual == 0).cumsum()).cumsum()
        if len(racha) and int(racha.max()) >= UMBRAL_RACHA_RANCIA:
            add("RACHA_DE_PRECIOS_IDENTICOS", "aviso", f"racha máxima de {int(racha.max())} cierres idénticos (posible dato rancio)")

    return {
        "resumen": {
            "errores": sum(1 for h in hallazgos if h["severidad"] == "error"),
            "avisos": sum(1 for h in hallazgos if h["severidad"] == "aviso"),
        },
        "hallazgos": hallazgos,
    }


def reporte_markdown(manifiesto: dict, validaciones: dict[str, dict]) -> str:
    lineas = [
        "# Reporte de calidad de datos",
        "",
        f"Generado (UTC): {manifiesto['generado_utc']}",
        "",
        f"Series descargadas: **{len(manifiesto['series'])}** · fallidas: **{len(manifiesto['fallidas'])}**",
        "",
        "| Serie | Fuente | Desde | Hasta | Filas | Errores | Avisos |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for sid, m in manifiesto["series"].items():
        lineas.append(
            f"| {sid} | {m['source']} | {m['primera_fecha']} | {m['ultima_fecha']} | {m['filas']} "
            f"| {m['hallazgos']['errores']} | {m['hallazgos']['avisos']} |"
        )
    if manifiesto["fallidas"]:
        lineas += ["", "## Series que NO se pudieron descargar", ""]
        lineas += [f"- **{k}**: {v}" for k, v in manifiesto["fallidas"].items()]
    detalle = [(sid, v["hallazgos"]) for sid, v in validaciones.items() if v["hallazgos"]]
    if detalle:
        lineas += ["", "## Hallazgos por serie", ""]
        for sid, hs in detalle:
            lineas.append(f"### {sid}")
            lineas += [f"- [{h['severidad']}] `{h['codigo']}` — {h['detalle']}" for h in hs]
            lineas.append("")
    return "\n".join(lineas) + "\n"

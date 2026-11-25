"""Construye la base de datos del Research Lab: descarga cada serie del
catálogo, la valida y la congela con un manifiesto reproducible.

    python -m prl.data.build                # todo el catálogo
    python -m prl.data.build --only SPY VIX # solo algunas series

Principios (ver METHODOLOGY.md):
  * RAW es inmutable: se guarda lo que entregó la fuente, sin ajustes
    propios. Los precios de Yahoo se piden SIN auto-ajuste (close y
    adj_close por separado) para que el ajuste sea explícito.
  * Cada corrida deja un manifiesto con SHA-256 por serie, fecha de
    descarga y versiones de librerías: una serie "congelada" se puede
    verificar byte a byte.
  * Nada se imputa ni se rellena aquí. Los huecos se REPORTAN, no se tapan.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from prl.data.macro_vintage import parse_vintage_observations, validar_vintages
from prl.data.validate import validar_serie, reporte_markdown

ROOT = Path(__file__).resolve().parents[3]
CATALOGO = ROOT / "data" / "catalog.yaml"
RAW = ROOT / "data" / "raw"
MANIFIESTO = ROOT / "data" / "manifest.json"
REPORTE = ROOT / "data" / "quality_report.md"
INICIO = "1990-01-01"
# Símbolos de universo fallidos tolerados en una sola corrida antes de
# tratarlo como fallo real (en vez de churn normal: delistings, fusiones,
# cambios de ticker — esperables en una lista de ~1600 símbolos). Más que
# esto en una sola corrida probablemente es un bloqueo sistémico (ej. IP
# de CI bloqueada por Yahoo), no un puñado de empresas que dejaron de
# cotizar — bug real encontrado el 2026-11-22: CWEN-A/TCBI fallidos
# tumbaban TODA la corrida (incluido SPY, que sí se había descargado
# bien), dejando sin publicar ningún Release nuevo desde entonces.
UMBRAL_FALLIDAS_UNIVERSO = 10
# Días corridos de atraso tolerados entre "hoy" y el último dato de Yahoo
# antes de tratarlo como una corrida fallida (no un aviso, ver
# UMBRAL_HUECO_DIAS_HABILES en validate.py para huecos DENTRO de la
# serie). Cubre un fin de semana largo con feriado (hasta ~4 días
# corridos); más que eso casi siempre es Yahoo truncando/cacheando
# silenciosamente la respuesta en las IPs de GitHub Actions — pasó el
# 2026-11-21, dejó el SPY pegado 8 días sin que ningún error lo avisara,
# y EXP-005 Paper Portfolio se quedó sin fechas nuevas que procesar toda
# esa semana (ver exp005_paper_portfolio.py).
UMBRAL_DATOS_VIEJOS_DIAS = 5


def cargar_catalogo(path: Path = CATALOGO) -> dict:
    return yaml.safe_load(path.read_text())


def descargar_yahoo(symbol: str, inicio: str = INICIO) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(symbol, start=inicio, auto_adjust=False, progress=False, actions=False, multi_level_index=False)
    if df is None or df.empty:
        raise RuntimeError(f"Yahoo no devolvió datos para {symbol}")
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close", "Volume": "volume"})
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    atraso_dias = (pd.Timestamp.now().normalize() - df.index.max()).days
    if atraso_dias > UMBRAL_DATOS_VIEJOS_DIAS:
        raise RuntimeError(
            f"{symbol}: el dato más reciente es del {df.index.max().date()} "
            f"({atraso_dias} días de atraso) — Yahoo respondió sin error pero "
            f"con datos viejos, probable truncamiento silencioso en CI, no se "
            f"congela una serie desactualizada sin avisar"
        )
    cols = [c for c in ["open", "high", "low", "close", "adj_close", "volume"] if c in df.columns]
    return df[cols].sort_index()


def descargar_fred(serie: str) -> pd.DataFrame:
    import requests

    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": serie}, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), na_values=".")
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df.dropna()


FRED_MIN_REALTIME_START = "1776-07-04"  # mínimo real exigido por la API (no 1776-01-01)


def descargar_fred_vintage(serie: str) -> pd.DataFrame:
    """Historial completo de vintages (ALFRED) de una serie FRED: una sola
    llamada con output_type=1 y ventana de tiempo real completa trae todas
    las versiones (obs_date, value, realtime_start, realtime_end) que
    existieron. Requiere FRED_API_KEY (no la usa descargar_fred: el
    fredgraph.csv público no da vintages). Ver
    experiments/EXP-002-growth-max-global/DATA_INFRA_MACRO_VINTAGE.md.

    La API no acepta realtime_end=9999-12-31 como entrada (solo lo usa como
    valor de salida): hay que pedir hasta hoy. FRED entonces devuelve la
    versión vigente con realtime_end = hoy (no 9999-12-31), así que se
    normaliza aquí a 9999-12-31 para cumplir el centinela que espera
    prl.data.macro_vintage ("vigente para siempre")."""
    import requests

    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("falta FRED_API_KEY en el entorno (requerida para series fred_vintage)")
    hoy = datetime.now(timezone.utc).date().isoformat()
    r = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": serie,
            "api_key": api_key,
            "file_type": "json",
            "realtime_start": FRED_MIN_REALTIME_START,
            "realtime_end": hoy,
            "output_type": 1,
        },
        timeout=60,
    )
    r.raise_for_status()
    crudo = r.json().get("observations", [])
    if not crudo:
        raise RuntimeError(f"ALFRED no devolvió observaciones para {serie}")
    for obs in crudo:
        if obs.get("realtime_end") == hoy:
            obs["realtime_end"] = "9999-12-31"
    return parse_vintage_observations(crudo)


def validar_vintage_serie(df: pd.DataFrame) -> dict:
    """Adapta validar_vintages (lista de strings) a la misma forma
    {resumen, hallazgos} que usa validar_serie, para que el manifiesto y
    reporte_markdown no necesiten dos formatos distintos. Cada problema de
    validar_vintages es, por diseño, un error (no un aviso): son
    inconsistencias de integridad, no anomalías de mercado."""
    problemas = validar_vintages(df)
    hallazgos = [{"codigo": p.split(" ", 1)[0], "severidad": "error", "detalle": p} for p in problemas]
    return {"resumen": {"errores": len(hallazgos), "avisos": 0}, "hallazgos": hallazgos}


def sha256_archivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def construir(only: list[str] | None = None) -> dict:
    cat = cargar_catalogo()
    RAW.mkdir(parents=True, exist_ok=True)

    objetivos = []
    for s in cat["series"]:
        if only and s["id"] not in only:
            continue
        objetivos.append(s)
    for u in cat.get("universes", []):
        archivo = ROOT / "data" / u["file"]
        if archivo.exists() and (not only or u["id"] in only):
            for sym in archivo.read_text().split():
                objetivos.append({"id": sym, "source": "yahoo", "symbol": sym, "role": f"universe:{u['id']}", "notes": u["notes"]})

    # Con `only`, esta corrida toca solo un subconjunto del catálogo — el
    # manifiesto previo (si existe) se usa como base y se actualiza en vez
    # de reemplazarse entero, para no perder el hash/procedencia de series
    # ya congeladas por una corrida anterior con un `only` distinto (bug
    # real encontrado el 2026-11-21: `construir(only=[...])` para EXP-004
    # había borrado las 207 series de EXP-001/EXP-002 del manifiesto).
    previo = json.loads(MANIFIESTO.read_text()) if MANIFIESTO.exists() else None
    manifiesto = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "librerias": {"pandas": pd.__version__, "python": sys.version.split()[0]},
        "series": dict(previo["series"]) if previo else {},
        "fallidas": dict(previo["fallidas"]) if previo else {},
    }
    descargadores = {"yahoo": descargar_yahoo, "fred": descargar_fred, "fred_vintage": descargar_fred_vintage}
    resultados_validacion = {}
    for s in objetivos:
        manifiesto["fallidas"].pop(s["id"], None)
        manifiesto["series"].pop(s["id"], None)
        try:
            df = descargadores[s["source"]](s["symbol"])
        except Exception as e:  # noqa: BLE001 - se reporta, no se esconde
            manifiesto["fallidas"][s["id"]] = f"{type(e).__name__}: {e}"
            continue
        destino = RAW / f"{s['id']}.parquet"
        df.to_parquet(destino)
        es_vintage = s["source"] == "fred_vintage"
        resultados_validacion[s["id"]] = validar_vintage_serie(df) if es_vintage else validar_serie(df, s)
        primera_fecha, ultima_fecha = (df["obs_date"].min(), df["obs_date"].max()) if es_vintage else (df.index.min(), df.index.max())
        manifiesto["series"][s["id"]] = {
            "source": s["source"],
            "symbol": s["symbol"],
            "role": s["role"],
            "filas": int(len(df)),
            "primera_fecha": str(primera_fecha.date()),
            "ultima_fecha": str(ultima_fecha.date()),
            "sha256": sha256_archivo(destino),
            "notas": s.get("notes", ""),
            "hallazgos": resultados_validacion[s["id"]]["resumen"],
        }

    MANIFIESTO.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    REPORTE.write_text(reporte_markdown(manifiesto, resultados_validacion))
    return manifiesto


def verificar_integridad() -> list[str]:
    """Compara cada parquet de data/raw con el SHA-256 del manifiesto.
    Devuelve la lista de problemas (vacía = todo íntegro)."""
    manifiesto = json.loads(MANIFIESTO.read_text())
    problemas = []
    for sid, m in manifiesto["series"].items():
        archivo = RAW / f"{sid}.parquet"
        if not archivo.exists():
            problemas.append(f"{sid}: falta el archivo")
        elif sha256_archivo(archivo) != m["sha256"]:
            problemas.append(f"{sid}: el hash no coincide con el manifiesto")
    return problemas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="ids de series a descargar (default: todas)")
    ap.add_argument("--verify", action="store_true", help="solo verificar data/raw contra data/manifest.json")
    args = ap.parse_args(argv)
    if args.verify:
        problemas = verificar_integridad()
        for p in problemas:
            print("INTEGRIDAD:", p)
        print("Integridad OK" if not problemas else f"{len(problemas)} problema(s)")
        return 1 if problemas else 0
    m = construir(args.only)
    print(f"Series guardadas: {len(m['series'])} · fallidas: {len(m['fallidas'])}")
    for k, v in m["fallidas"].items():
        print(f"  FALLÓ {k}: {v}")
    if not m["fallidas"]:
        return 0

    # No toda falla bloquea la publicación: un símbolo de universo
    # delistado es churn normal, no una razón para dejar a SPY (y los
    # demás ~1600 símbolos que sí se descargaron bien) sin un Release
    # nuevo. Lo que SÍ bloquea: una serie del catálogo explícito (no un
    # miembro de universo) o demasiados fallos de universo a la vez
    # (señal de bloqueo sistémico real, no churn).
    ids_criticos = {s["id"] for s in cargar_catalogo()["series"]}
    fallidas_criticas = sorted(set(m["fallidas"]) & ids_criticos)
    if fallidas_criticas:
        print(f"CRÍTICO: fallaron series del catálogo explícito (no universo): {', '.join(fallidas_criticas)}")
        return 1
    if len(m["fallidas"]) > UMBRAL_FALLIDAS_UNIVERSO:
        print(
            f"CRÍTICO: {len(m['fallidas'])} símbolos de universo fallaron "
            f"(> {UMBRAL_FALLIDAS_UNIVERSO}) — no parece churn normal"
        )
        return 1
    print(f"{len(m['fallidas'])} símbolo(s) de universo fallido(s) — churn normal, no bloquea la publicación.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

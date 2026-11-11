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
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from prl.data.validate import validar_serie, reporte_markdown

ROOT = Path(__file__).resolve().parents[3]
CATALOGO = ROOT / "data" / "catalog.yaml"
RAW = ROOT / "data" / "raw"
MANIFIESTO = ROOT / "data" / "manifest.json"
REPORTE = ROOT / "data" / "quality_report.md"
INICIO = "1990-01-01"


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

    manifiesto = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "librerias": {"pandas": pd.__version__, "python": sys.version.split()[0]},
        "series": {},
        "fallidas": {},
    }
    resultados_validacion = {}
    for s in objetivos:
        try:
            df = descargar_yahoo(s["symbol"]) if s["source"] == "yahoo" else descargar_fred(s["symbol"])
        except Exception as e:  # noqa: BLE001 - se reporta, no se esconde
            manifiesto["fallidas"][s["id"]] = f"{type(e).__name__}: {e}"
            continue
        destino = RAW / f"{s['id']}.parquet"
        df.to_parquet(destino)
        resultados_validacion[s["id"]] = validar_serie(df, s)
        manifiesto["series"][s["id"]] = {
            "source": s["source"],
            "symbol": s["symbol"],
            "role": s["role"],
            "filas": int(len(df)),
            "primera_fecha": str(df.index.min().date()),
            "ultima_fecha": str(df.index.max().date()),
            "sha256": sha256_archivo(destino),
            "notas": s.get("notes", ""),
            "hallazgos": resultados_validacion[s["id"]]["resumen"],
        }

    MANIFIESTO.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    REPORTE.write_text(reporte_markdown(manifiesto, resultados_validacion))
    return manifiesto


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="ids de series a descargar (default: todas)")
    args = ap.parse_args(argv)
    m = construir(args.only)
    print(f"Series guardadas: {len(m['series'])} · fallidas: {len(m['fallidas'])}")
    for k, v in m["fallidas"].items():
        print(f"  FALLÓ {k}: {v}")
    return 1 if m["fallidas"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

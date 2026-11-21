"""Universo S&P 1500 para EXP-004 (Short Pressure Reversal) — ver
experiments/EXP-004-short-pressure-reversal/PREREGISTRATION.md.

Combina S&P 500 + S&P 400 (MidCap) + S&P 600 (SmallCap): constituyentes
ACTUALES, no point-in-time históricos. Esto elimina el sesgo de
SELECCIÓN MANUAL CON HINDSIGHT (no se eligen 30-79 nombres porque ya se
sabe que ganaron — se toma el índice completo), pero NO elimina el
sesgo de supervivencia completo: una empresa que quebró, fue adquirida
o salió de estos 3 índices durante la ventana del experimento
(2019-2026) no aparece en ningún lado. Limitación declarada en el
pre-registro, no oculta aquí.

Fuentes (verificadas accesibles con peticiones HTTP reales antes de
escribir este módulo, no de memoria):
  * S&P 500: github.com/datasets/s-and-p-500-companies (CSV directo).
  * S&P 400 / S&P 600: tablas de Wikipedia "List of S&P 400/600
    companies" (primera tabla de la página, columna "Symbol").
  * Intento descartado: descargar holdings de iShares IWB (Russell
    1000) por HTTP directo — devuelve una página HTML con bloqueo
    anti-bot, no el CSV. No se reintenta.

    python -m prl.data.equity_universe   # descarga real, congela el resultado
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DESTINO_UNIVERSO = ROOT / "data" / "universes" / "sp1500_short_pressure.txt"
DESTINO_MANIFIESTO = ROOT / "data" / "universes" / "sp1500_short_pressure_manifest.json"

URL_SP500 = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
URL_SP400 = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
URL_SP600 = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
USER_AGENT = "Mozilla/5.0"


def normalizar_simbolo_yahoo(simbolo: str) -> str:
    """yfinance espera guion, no punto, para clases de acción (ej. la
    de Berkshire Hathaway clase B: "BRK.B" en S&P/Wikipedia -> "BRK-B"
    para yfinance). Gotcha real y conocido, no un caso hipotético."""
    return simbolo.strip().upper().replace(".", "-")


def parse_sp500_csv(texto: str) -> list[str]:
    """Columna "Symbol" del CSV de datasets/s-and-p-500-companies."""
    df = pd.read_csv(io.StringIO(texto))
    return df["Symbol"].dropna().astype(str).tolist()


def parse_wikipedia_tabla_simbolos(html: str, columna: str = "Symbol") -> list[str]:
    """Primera tabla (`<table class="wikitable">` renderizada por
    pandas.read_html) de una página de Wikipedia tipo "List of S&P
    400/600 companies" — misma estructura confirmada en ambas páginas
    antes de escribir este módulo."""
    tablas = pd.read_html(io.StringIO(html))
    primera = tablas[0]
    return primera[columna].dropna().astype(str).tolist()


def construir_universo(sp500: list[str], sp400: list[str], sp600: list[str]) -> list[str]:
    """Normaliza, deduplica (un símbolo puede aparecer en más de un
    índice en un momento de transición) y ordena — función pura, sin
    red, para poder probarla sin descargar nada."""
    todos = (normalizar_simbolo_yahoo(s) for s in (*sp500, *sp400, *sp600))
    return sorted(set(todos))


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def descargar_y_congelar() -> dict:
    """Descarga real de las 3 fuentes, construye el universo, lo
    congela en DESTINO_UNIVERSO (un símbolo por línea, mismo formato
    que data/universes/trading_universe.txt ya existente) y escribe un
    manifiesto con hash SHA-256 de cada fuente cruda, fecha de
    descarga y conteos — mismo espíritu que data/manifest.json, en su
    propio archivo (catalog.yaml está pensado para series curadas una
    por una, no para una lista de ~1,500 tickers autogenerada)."""
    import requests

    headers = {"User-Agent": USER_AGENT}
    r_sp500 = requests.get(URL_SP500, headers=headers, timeout=60)
    r_sp500.raise_for_status()
    r_sp400 = requests.get(URL_SP400, headers=headers, timeout=60)
    r_sp400.raise_for_status()
    r_sp600 = requests.get(URL_SP600, headers=headers, timeout=60)
    r_sp600.raise_for_status()

    sp500 = parse_sp500_csv(r_sp500.text)
    sp400 = parse_wikipedia_tabla_simbolos(r_sp400.text)
    sp600 = parse_wikipedia_tabla_simbolos(r_sp600.text)
    universo = construir_universo(sp500, sp400, sp600)

    DESTINO_UNIVERSO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO_UNIVERSO.write_text("\n".join(universo) + "\n", encoding="utf-8")

    manifiesto = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "n_sp500": len(sp500),
        "n_sp400": len(sp400),
        "n_sp600": len(sp600),
        "n_universo_final": len(universo),
        "fuentes": {
            "sp500": {"url": URL_SP500, "sha256": _sha256_texto(r_sp500.text)},
            "sp400": {"url": URL_SP400, "sha256": _sha256_texto(r_sp400.text)},
            "sp600": {"url": URL_SP600, "sha256": _sha256_texto(r_sp600.text)},
        },
        "limitacion": (
            "Constituyentes ACTUALES, no point-in-time históricos. Elimina sesgo "
            "de selección manual con hindsight; NO elimina sesgo de supervivencia "
            "completo (empresas que salieron de estos 3 índices entre 2019-2026 "
            "no aparecen)."
        ),
    }
    DESTINO_MANIFIESTO.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    return manifiesto


def main() -> int:
    m = descargar_y_congelar()
    print(
        f"Universo S&P 1500: {m['n_universo_final']} símbolos únicos "
        f"(S&P500={m['n_sp500']}, S&P400={m['n_sp400']}, S&P600={m['n_sp600']})"
    )
    print(f"Guardado en {DESTINO_UNIVERSO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

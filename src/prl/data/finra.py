"""Short volume diario y short interest bi-mensual de FINRA para EXP-004
(Short Pressure Reversal) — ver
experiments/EXP-004-short-pressure-reversal/PREREGISTRATION.md.

Dos fuentes GRATIS, SIN autenticación, verificadas con peticiones HTTP
reales antes de escribir este módulo (no de documentación):

  * Short volume DIARIO (Reg SHO): actividad de trading en corto, no
    posición acumulada. `cdn.finra.org/equity/regsho/daily/
    CNMSshvol<YYYYMMDD>.txt`, funciona desde 2019-01-02 (403 antes).
  * Short interest BI-MENSUAL: posición corta acumulada por fecha de
    settlement (15 y último día hábil de cada mes), con
    `days_to_cover` y `change_pct` ya calculados por FINRA — no hay
    que derivarlos. `cdn.finra.org/equity/otcmarket/biweekly/
    shrt<YYYYMMDD>.csv`, funciona desde ~2019-2020 (403 antes).

LIMITACIONES DECLARADAS (ver pre-registro, no se ocultan aquí):
  * No hay float histórico gratis point-in-time: "short interest/float"
    se sustituye por `days_to_cover` + `change_pct` + el short volume
    diario, que sí son gratis y point-in-time-usables.
  * El esquema de short interest trae una columna `revisionFlag`: si un
    settlement histórico fue revisado, la descarga de HOY da el valor
    revisado, no el originalmente publicado — no hay historial de
    versiones en esta fuente. Limitación heredada del proveedor.
  * La fecha de PUBLICACIÓN real (7º día hábil tras el settlement, dato
    de la página "about" de FINRA) es la que gobierna el point-in-time
    — nunca el settlement date directo, que sería look-ahead. El
    cálculo de "día hábil" aquí es una aproximación lunes-viernes, sin
    calendario de feriados bursátiles — aproximación declarada, no se
    pretende precisión al día exacto.

    python -m prl.data.finra --inicio 2019-02-01 --fin 2026-11-21   # descarga real, congela
"""

from __future__ import annotations

import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW_SHORT_VOLUME = ROOT / "data" / "raw" / "finra_short_volume"
RAW_SHORT_INTEREST = ROOT / "data" / "raw" / "finra_short_interest"
MANIFIESTO = ROOT / "data" / "raw" / "finra_manifest.json"
UNIVERSO_DEFAULT = ROOT / "data" / "universes" / "sp1500_short_pressure.txt"
N_WORKERS = 10

URL_SHORT_VOLUME = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{fecha}.txt"
URL_SHORT_INTEREST = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{fecha}.csv"

COLUMNAS_SHORT_INTEREST = {
    "symbolCode": "symbol",
    "issueName": "issue_name",
    "marketClassCode": "market_class",
    "currentShortPositionQuantity": "short_interest",
    "previousShortPositionQuantity": "short_interest_previo",
    "averageDailyVolumeQuantity": "avg_daily_volume",
    "daysToCoverQuantity": "days_to_cover",
    "revisionFlag": "revision_flag",
    "changePercent": "short_interest_change_pct",
    "changePreviousNumber": "short_interest_change_abs",
    "settlementDate": "settlement_date",
}


# ---------------------------------------------------------------------------
# Parsing puro (sin red) — probado con texto de muestra, nunca con la red
# real dentro de la suite de tests.
# ---------------------------------------------------------------------------


def parse_short_volume_diario(texto: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(texto), sep="|")
    df = df.rename(columns={
        "Date": "date", "Symbol": "symbol", "ShortVolume": "short_volume",
        "ShortExemptVolume": "short_exempt_volume", "TotalVolume": "total_volume", "Market": "market",
    })
    # El archivo real trae una línea de pie con el conteo de registros (un
    # solo campo, ej. "12343"), sin pipes — pandas la rellena con NaN en
    # las demás columnas en vez de fallar. Se descarta por completitud de
    # fila, no por adivinar el formato exacto del pie.
    df = df.dropna(subset=["symbol", "short_volume", "total_volume"])
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df["short_volume_ratio"] = df["short_volume"] / df["total_volume"].replace(0, pd.NA)
    return df


def parse_short_interest_csv(texto: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(texto), sep="|", quotechar='"')
    df = df.rename(columns=COLUMNAS_SHORT_INTEREST)
    df = df[[c for c in COLUMNAS_SHORT_INTEREST.values() if c in df.columns]]
    df["settlement_date"] = pd.to_datetime(df["settlement_date"])
    return df


# ---------------------------------------------------------------------------
# Fechas de settlement y point-in-time — pura, sin red.
# ---------------------------------------------------------------------------


def generar_candidatos_settlement(inicio: pd.Timestamp, fin: pd.Timestamp) -> list[pd.Timestamp]:
    """Dos candidatos por mes: el 15 (o el viernes anterior si el 15
    cae sábado/domingo) y el último día hábil (lunes-viernes) del mes.
    Son CANDIDATOS de URL a intentar, no la fecha de settlement real
    garantizada — `descargar_short_interest_con_reintentos` retrocede
    unos días si el candidato no existe (ej. por un feriado que esta
    aproximación lunes-viernes no conoce)."""
    inicio, fin = pd.Timestamp(inicio), pd.Timestamp(fin)
    candidatos: list[pd.Timestamp] = []
    for periodo in pd.period_range(inicio, fin, freq="M"):
        dia15 = pd.Timestamp(year=periodo.year, month=periodo.month, day=15)
        while dia15.dayofweek >= 5:  # 5=sábado, 6=domingo
            dia15 -= pd.Timedelta(days=1)
        fin_mes = periodo.end_time.normalize()
        while fin_mes.dayofweek >= 5:
            fin_mes -= pd.Timedelta(days=1)
        for d in (dia15, fin_mes):
            if inicio <= d <= fin:
                candidatos.append(d)
    return sorted(set(candidatos))


def fecha_publicacion(settlement: pd.Timestamp, dias_habiles: int = 7) -> pd.Timestamp:
    """7º día hábil después del settlement (dato real de la página
    "about" de FINRA) — aproximación lunes-viernes, sin calendario de
    feriados bursátiles."""
    return pd.Timestamp(settlement) + pd.tseries.offsets.BDay(dias_habiles)


def ultimo_short_interest_vigente(
    snapshots: dict[pd.Timestamp, pd.DataFrame], as_of: pd.Timestamp
) -> pd.DataFrame | None:
    """El snapshot VIGENTE a `as_of`: el de settlement más reciente
    cuya fecha de PUBLICACIÓN ya pasó — nunca el settlement date
    directo (sería look-ahead). None si todavía no se publicó nada."""
    as_of = pd.Timestamp(as_of)
    publicados = [s for s in snapshots if fecha_publicacion(s) <= as_of]
    if not publicados:
        return None
    return snapshots[max(publicados)]


# ---------------------------------------------------------------------------
# Red — no se prueba con llamadas reales en la suite de tests, mismo
# patrón que `descargar_yahoo`/`descargar_fred` en build.py.
# ---------------------------------------------------------------------------


def descargar_short_volume_diario(fecha: pd.Timestamp) -> pd.DataFrame | None:
    import requests

    url = URL_SHORT_VOLUME.format(fecha=pd.Timestamp(fecha).strftime("%Y%m%d"))
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        return None
    return parse_short_volume_diario(r.text)


def descargar_short_interest_con_reintentos(
    fecha_candidata: pd.Timestamp, max_retroceso_dias: int = 5
) -> pd.DataFrame | None:
    import requests

    for retroceso in range(max_retroceso_dias + 1):
        fecha = pd.Timestamp(fecha_candidata) - pd.Timedelta(days=retroceso)
        url = URL_SHORT_INTEREST.format(fecha=fecha.strftime("%Y%m%d"))
        r = requests.get(url, timeout=60)
        if r.status_code == 200:
            return parse_short_interest_csv(r.text)
    return None


def _cargar_universo(universo_path: Path) -> set[str]:
    return set(universo_path.read_text().split())


def descargar_y_congelar_rango(inicio: str, fin: str, universo_path: Path = UNIVERSO_DEFAULT) -> dict:
    """Descarga real: short volume diario para cada día hábil del
    rango, short interest para cada fecha de settlement candidata.
    Ambas fuentes cubren TODO el mercado (varios miles de símbolos
    por día) — se filtra cada descarga al universo de EXP-004
    (~1,502 símbolos) antes de acumular, para no guardar en memoria/
    disco datos que el experimento no va a usar. Paralelismo modesto
    (ThreadPoolExecutor, N_WORKERS hilos) porque son miles de
    peticiones HTTP individuales. Congela cada fuente como un parquet
    consolidado (no miles de archivos individuales) + manifiesto con
    conteos de éxito/fallo."""
    inicio_ts, fin_ts = pd.Timestamp(inicio), pd.Timestamp(fin)
    RAW_SHORT_VOLUME.mkdir(parents=True, exist_ok=True)
    RAW_SHORT_INTEREST.mkdir(parents=True, exist_ok=True)
    universo = _cargar_universo(universo_path)

    def _sv(d):
        df = descargar_short_volume_diario(d)
        if df is None:
            return d, None
        return d, df[df["symbol"].isin(universo)]

    t0 = time.monotonic()
    dias_habiles = pd.bdate_range(inicio_ts, fin_ts)
    sv_frames, sv_fallidos = [], []
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(_sv, d): d for d in dias_habiles}
        for fut in as_completed(futs):
            d, df = fut.result()
            if df is None:
                sv_fallidos.append(str(d.date()))
            else:
                sv_frames.append(df)
    sv_consolidado = pd.concat(sv_frames, ignore_index=True).sort_values(["date", "symbol"]) if sv_frames else pd.DataFrame()
    if not sv_consolidado.empty:
        sv_consolidado.to_parquet(RAW_SHORT_VOLUME / "short_volume_consolidado.parquet")
    t_sv = time.monotonic() - t0

    def _si(c):
        df = descargar_short_interest_con_reintentos(c)
        if df is None:
            return c, None
        return c, df[df["symbol"].isin(universo)]

    t1 = time.monotonic()
    candidatos = generar_candidatos_settlement(inicio_ts, fin_ts)
    si_frames, si_fallidos = [], []
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(_si, c): c for c in candidatos}
        for fut in as_completed(futs):
            c, df = fut.result()
            if df is None:
                si_fallidos.append(str(c.date()))
            else:
                si_frames.append(df)
    si_consolidado = pd.concat(si_frames, ignore_index=True).sort_values(["settlement_date", "symbol"]) if si_frames else pd.DataFrame()
    if not si_consolidado.empty:
        si_consolidado.to_parquet(RAW_SHORT_INTEREST / "short_interest_consolidado.parquet")
    t_si = time.monotonic() - t1

    manifiesto = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "rango": {"inicio": inicio, "fin": fin},
        "universo_n": len(universo),
        "short_volume": {
            "dias_intentados": len(dias_habiles),
            "dias_exitosos": len(sv_frames),
            "dias_fallidos": sv_fallidos,
            "filas_totales": int(len(sv_consolidado)),
            "segundos": round(t_sv, 1),
        },
        "short_interest": {
            "settlements_intentados": len(candidatos),
            "settlements_exitosos": len(si_frames),
            "settlements_fallidos": si_fallidos,
            "filas_totales": int(len(si_consolidado)),
            "segundos": round(t_si, 1),
        },
    }
    MANIFIESTO.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    return manifiesto


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inicio", default="2019-02-01")
    ap.add_argument("--fin", required=True)
    args = ap.parse_args()
    m = descargar_y_congelar_rango(args.inicio, args.fin)
    print(json.dumps(m, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

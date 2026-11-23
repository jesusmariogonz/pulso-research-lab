"""Forward validation check para EXP-005.

Determina fechas nuevas, acumula el log de señales (JSON plano) entre
corridas y calcula las métricas del reporte reutilizando las funciones
ya implementadas en ``prl.reverse_winners.forward_validation`` y
``prl.reverse_winners.evaluation``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from prl.reverse_winners import evaluation, exp005, forward_validation


_METODOS: tuple[str, ...] = (
    "ganador",
    "baseline_momentum_simple",
    "baseline_buy_hold",
    "baseline_rsi_simple",
    "baseline_combo_ingenuo",
    "spy",
)

_BENCHMARKS: tuple[str, ...] = (
    "baseline_momentum_simple",
    "baseline_buy_hold",
    "baseline_rsi_simple",
    "baseline_combo_ingenuo",
    "spy",
)


# ---------------------------------------------------------------------------
# Helpers de serialización a JSON plano
# ---------------------------------------------------------------------------
def _json_scalar(value: Any) -> Any:
    """Convierte un escalar (posiblemente numpy/pandas) a algo JSON-safe."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        fv = float(value)
        if math.isnan(fv) or math.isinf(fv):
            return None
        return fv
    if isinstance(value, str):
        return value
    return value


def _json_safe(obj: Any) -> Any:
    """Convierte recursivamente estructuras con pandas/numpy a JSON plano."""
    if isinstance(obj, pd.DataFrame):
        df = obj.reset_index()
        return [_json_safe(rec) for rec in df.to_dict(orient="records")]
    if isinstance(obj, pd.Series):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return [_json_safe(v) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return _json_scalar(obj)


def _fecha_iso(value: Any) -> str | None:
    """Fecha (Timestamp / ISO-string) a formato date-only ISO."""
    if value is None or value is pd.NaT:
        return None
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    return ts.date().isoformat()


def _df_a_registros(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Convierte un DataFrame de señales a lista de dicts JSON-plano."""
    if df is None or len(df) == 0:
        return []
    registros: list[dict[str, Any]] = []
    for raw in df.to_dict(orient="records"):
        registro: dict[str, Any] = {}
        for key, value in raw.items():
            if key == "fecha":
                registro[key] = _fecha_iso(value)
            else:
                registro[key] = _json_scalar(value)
        registros.append(registro)
    return registros


# ---------------------------------------------------------------------------
# Determinación de fechas nuevas
# ---------------------------------------------------------------------------
def determinar_fechas_nuevas(
    calendario: pd.DatetimeIndex,
    ultima_fecha_procesada: pd.Timestamp,
    discovery_start: str = "2010-01-01",
    paso_dias: int = 10,
    ventana_forward: int = 30,
) -> list[pd.Timestamp]:
    """Fechas del grid de paso ``paso_dias`` (anclado en ``discovery_start``)
    estrictamente posteriores a ``ultima_fecha_procesada`` y con ventana
    forward completa."""
    todas = pd.DatetimeIndex(
        exp005.fechas_t0(calendario, inicio=discovery_start, paso=paso_dias)
    )
    n_cal = len(calendario)
    if len(todas) == 0:
        return []

    positions = np.searchsorted(calendario.values, todas.values, side="left")
    completas = todas[positions + ventana_forward < n_cal]
    nuevas = completas[completas > ultima_fecha_procesada]
    return list(nuevas)


# ---------------------------------------------------------------------------
# Acumulación del log
# ---------------------------------------------------------------------------
def actualizar_log(
    log_existente: dict[str, list[dict]],
    nuevas_senales: dict[str, pd.DataFrame],
) -> dict[str, list[dict]]:
    """Agrega las señales nuevas al log existente, deduplicando por
    ``(fecha, ticker)`` y ordenando cada lista por ``fecha`` ascendente."""
    resultado: dict[str, list[dict]] = {
        metodo: list(entradas) for metodo, entradas in log_existente.items()
    }

    for metodo, df in nuevas_senales.items():
        base = resultado.get(metodo, [])
        vistos = {(str(e.get("fecha")), str(e.get("ticker"))) for e in base}
        for registro in _df_a_registros(df):
            clave = (str(registro.get("fecha")), str(registro.get("ticker")))
            if clave in vistos:
                continue
            base.append(registro)
            vistos.add(clave)
        resultado[metodo] = base

    for metodo in list(resultado.keys()):
        resultado[metodo] = sorted(
            resultado[metodo], key=lambda e: str(e.get("fecha", ""))
        )
    return resultado


# ---------------------------------------------------------------------------
# Métricas del reporte
# ---------------------------------------------------------------------------
def calcular_metricas_reporte(
    log_acumulado: dict[str, list[dict]],
    vix_por_fecha: pd.Series,
    ultima_fecha_original: str = "2026-09-30",
) -> dict:
    """Calcula el dict de métricas del reporte a partir del log acumulado.

    El resultado es directamente serializable con ``json.dumps``.
    """

    def df_de(metodo: str) -> pd.DataFrame:
        entradas = log_acumulado.get(metodo) or []
        if not entradas:
            return pd.DataFrame(
                {
                    "fecha": pd.Series(dtype="datetime64[ns]"),
                    "ticker": pd.Series(dtype="object"),
                    "retorno_30d": pd.Series(dtype="float64"),
                }
            )
        df = pd.DataFrame(list(entradas))
        if "fecha" in df.columns:
            df["fecha"] = pd.to_datetime(df["fecha"])
        if "retorno_30d" not in df.columns:
            df["retorno_30d"] = np.nan
        return df

    dfs = {metodo: df_de(metodo) for metodo in _METODOS}
    series = {
        metodo: forward_validation.serie_por_fecha(dfs[metodo])
        for metodo in _METODOS
    }

    df_ganador = dfs["ganador"]
    n_fechas_acumuladas = (
        int(df_ganador["fecha"].nunique()) if len(df_ganador) else 0
    )
    n_senales_ganador = len(log_acumulado.get("ganador") or [])

    metricas: dict[str, dict[str, Any]] = {}
    for metodo in _METODOS:
        metricas[metodo] = {
            "retorno_acumulado": forward_validation.retorno_acumulado(
                series[metodo]
            ),
            "sharpe": forward_validation.sharpe(series[metodo]),
            "max_drawdown": forward_validation.max_drawdown(series[metodo]),
            "hit_rate": forward_validation.hit_rate(dfs[metodo]),
        }

    exceso_vs_momentum = forward_validation.exceso_vs_benchmark(
        series["ganador"], series["baseline_momentum_simple"]
    ).mean()
    exceso_vs_spy = forward_validation.exceso_vs_benchmark(
        series["ganador"], series["spy"]
    ).mean()

    ra_ganador = metricas["ganador"]["retorno_acumulado"]
    supera = True
    for benchmark in _BENCHMARKS:
        rb = metricas[benchmark]["retorno_acumulado"]
        if pd.isna(ra_ganador) or pd.isna(rb) or not (
            float(ra_ganador) > float(rb)
        ):
            supera = False
            break
    supera = bool(supera)

    if len(df_ganador) > 0:
        concentracion = evaluation.concentracion_maxima(df_ganador)
        leave_one_ticker_out = evaluation.leave_one_ticker_out_signo(df_ganador)
    else:
        concentracion = None
        leave_one_ticker_out = None

    concentracion_del_efecto = forward_validation.concentracion_del_efecto(
        df_ganador
    )
    depende = bool(concentracion_del_efecto["depende_de_pocas_senales"])

    desglose_periodo = forward_validation.desglose_por_periodo(df_ganador)
    desglose_vix = forward_validation.desglose_por_regimen_vix(
        df_ganador, vix_por_fecha
    )
    df_vol = df_ganador.copy()
    if "vol_realizada_20d_cruda" not in df_vol.columns:
        df_vol["vol_realizada_20d_cruda"] = np.nan
    desglose_volatilidad = forward_validation.desglose_por_volatilidad(df_vol)

    label = forward_validation.etiqueta_forward(
        n_fechas_acumuladas, supera, depende
    )

    resultado: dict[str, Any] = {
        "n_fechas_acumuladas": n_fechas_acumuladas,
        "n_senales_ganador": n_senales_ganador,
        "metricas_por_metodo": metricas,
        "exceso_vs_momentum": exceso_vs_momentum,
        "exceso_vs_spy": exceso_vs_spy,
        "concentracion": concentracion,
        "leave_one_ticker_out": leave_one_ticker_out,
        "concentracion_del_efecto": concentracion_del_efecto,
        "desglose_periodo": desglose_periodo,
        "desglose_vix": desglose_vix,
        "desglose_volatilidad": desglose_volatilidad,
        "supera_los_5_benchmarks": supera,
        "label": str(label),
        "ultima_fecha_original": str(ultima_fecha_original),
    }
    return _json_safe(resultado)

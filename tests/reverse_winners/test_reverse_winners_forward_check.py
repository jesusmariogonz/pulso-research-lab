import json

import numpy as np
import pandas as pd
import pytest

from prl.reverse_winners import forward_check
from prl.reverse_winners.exp005 import fechas_t0


_METODOS = (
    "ganador",
    "baseline_momentum_simple",
    "baseline_buy_hold",
    "baseline_rsi_simple",
    "baseline_combo_ingenuo",
    "spy",
)


def test_determinar_fechas_nuevas():
    calendario = pd.bdate_range("2020-01-01", periods=500)
    discovery_start = "2020-01-01"
    paso_dias = 10
    ventana_forward = 30

    todas = fechas_t0(calendario, inicio=discovery_start, paso=paso_dias)
    n_cal = len(calendario)
    positions = np.searchsorted(calendario.values, todas.values, side="left")
    completas = todas[positions + ventana_forward < n_cal]

    ultima_fecha_procesada = completas[40]
    esperado = list(completas[completas > ultima_fecha_procesada])

    obtenido = forward_check.determinar_fechas_nuevas(
        calendario, ultima_fecha_procesada,
        discovery_start=discovery_start, paso_dias=paso_dias,
        ventana_forward=ventana_forward,
    )
    assert obtenido == esperado
    assert len(obtenido) > 0


def test_determinar_fechas_nuevas_sin_fechas_nuevas():
    calendario = pd.bdate_range("2020-01-01", periods=500)
    todas = fechas_t0(calendario, inicio="2020-01-01", paso=10)
    n_cal = len(calendario)
    positions = np.searchsorted(calendario.values, todas.values, side="left")
    completas = todas[positions + 30 < n_cal]

    obtenido = forward_check.determinar_fechas_nuevas(
        calendario, completas[-1],
        discovery_start="2020-01-01", paso_dias=10, ventana_forward=30,
    )
    assert obtenido == []


def test_actualizar_log_deduplica():
    log_existente = {
        "ganador": [
            {"fecha": "2022-01-01", "ticker": "A", "retorno_30d": 0.1}
        ]
    }
    nuevas = pd.DataFrame(
        {
            "fecha": [pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-15")],
            "ticker": ["A", "B"],
            "retorno_30d": [0.1, 0.2],
        }
    )
    out = forward_check.actualizar_log(log_existente, {"ganador": nuevas})
    assert len(out["ganador"]) == 2
    tickers = {(e["fecha"], e["ticker"]) for e in out["ganador"]}
    assert tickers == {("2022-01-01", "A"), ("2022-01-15", "B")}


def test_actualizar_log_con_log_vacio():
    nuevas_senales = {}
    for m in _METODOS:
        nuevas_senales[m] = pd.DataFrame(
            {
                "fecha": [pd.Timestamp("2022-01-01")],
                "ticker": ["A" if m != "spy" else "SPY"],
                "retorno_30d": [0.05],
            }
        )
    out = forward_check.actualizar_log({}, nuevas_senales)
    assert set(out.keys()) == set(_METODOS)
    for m in _METODOS:
        assert len(out[m]) == 1
        assert out[m][0]["fecha"] == "2022-01-01"


def test_calcular_metricas_reporte_log_vacio():
    log_vacio = {m: [] for m in _METODOS}
    vix = pd.Series(dtype=float)
    out = forward_check.calcular_metricas_reporte(log_vacio, vix)
    assert out["n_fechas_acumuladas"] == 0
    assert out["n_senales_ganador"] == 0
    assert out["label"] == "inconclusa"
    # Debe ser serializable a JSON sin pasos adicionales.
    json.dumps(out)


def _log_favorable():
    fechas = [pd.Timestamp("2022-01-01") + pd.Timedelta(days=14 * i) for i in range(12)]
    log = {}
    for metodo in _METODOS:
        filas = []
        for i, fecha in enumerate(fechas):
            retorno = 0.05 if metodo == "ganador" else 0.01
            ticker = f"T{i}{metodo[:3]}A"
            filas.append({"fecha": fecha.isoformat(), "ticker": ticker, "retorno_30d": retorno})
            ticker2 = f"T{i}{metodo[:3]}B"
            filas.append({"fecha": fecha.isoformat(), "ticker": ticker2, "retorno_30d": retorno})
        log[metodo] = filas
    return log


def test_calcular_metricas_reporte_caso_favorable():
    log = _log_favorable()
    vix = pd.Series(dtype=float)
    out = forward_check.calcular_metricas_reporte(log, vix)
    assert out["n_fechas_acumuladas"] == 12
    assert out["supera_los_5_benchmarks"] is True
    assert out["label"] == "favorable"


def test_calcular_metricas_reporte_determinista():
    log = _log_favorable()
    vix = pd.Series(dtype=float)
    out1 = forward_check.calcular_metricas_reporte(log, vix)
    out2 = forward_check.calcular_metricas_reporte(log, vix)
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)

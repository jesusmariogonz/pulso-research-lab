from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

_VIGENTE_HASTA = pd.Timestamp("9999-12-31")
_COLUMNAS_VINTAGE = ("obs_date", "value", "realtime_start", "realtime_end")


def _vintage_vacio() -> pd.DataFrame:
    """DataFrame vacío con el esquema esperado de vintages."""
    return pd.DataFrame(
        {
            "obs_date": pd.Series(dtype="datetime64[ns]"),
            "value": pd.Series(dtype="float64"),
            "realtime_start": pd.Series(dtype="datetime64[ns]"),
            "realtime_end": pd.Series(dtype="datetime64[ns]"),
        }
    )


def _sin_valor_conocido() -> dict[str, Any]:
    """Resultado de `ultimo_valor_conocido` cuando no hay dato conocido."""
    return {"obs_date": None, "value": None, "antiguedad_dias": None}


def parse_vintage_observations(raw: list[dict]) -> pd.DataFrame:
    """Convierte la respuesta cruda de ALFRED/FRED al DataFrame de vintages."""
    if not raw:
        return _vintage_vacio()

    filas: list[dict[str, Any]] = []

    for item in raw:
        obs_date = pd.Timestamp(item["date"])
        realtime_start = pd.Timestamp(item["realtime_start"])
        realtime_end = pd.Timestamp(item["realtime_end"])

        if realtime_start > realtime_end:
            raise ValueError(
                "realtime_start no puede ser posterior a realtime_end "
                f"({realtime_start} > {realtime_end})"
            )

        if realtime_start < obs_date:
            raise ValueError(
                "realtime_start no puede ser anterior a obs_date "
                f"({realtime_start} < {obs_date})"
            )

        if realtime_start > obs_date + pd.DateOffset(years=50):
            raise ValueError(
                "realtime_start no puede estar más de 50 años después de obs_date "
                f"({realtime_start} vs {obs_date})"
            )

        valor_raw = item["value"]
        if isinstance(valor_raw, str) and valor_raw.strip() == ".":
            continue

        try:
            valor = float(valor_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Valor no numérico en vintage: {valor_raw!r}") from exc

        filas.append(
            {
                "obs_date": obs_date,
                "value": valor,
                "realtime_start": realtime_start,
                "realtime_end": realtime_end,
            }
        )

    if not filas:
        return _vintage_vacio()

    df = pd.DataFrame(filas, columns=list(_COLUMNAS_VINTAGE))
    df["obs_date"] = pd.to_datetime(df["obs_date"])
    df["realtime_start"] = pd.to_datetime(df["realtime_start"])
    df["realtime_end"] = pd.to_datetime(df["realtime_end"])
    df["value"] = df["value"].astype(float)
    return df


def validar_vintages(df: pd.DataFrame) -> list[str]:
    """Reporta problemas de consistencia en un DataFrame de vintages."""
    if df is None or df.empty:
        return []

    problemas: list[str] = []

    for obs_date, grupo in df.groupby("obs_date", sort=False):
        etiqueta = str(obs_date)

        if bool((grupo["realtime_start"] < obs_date).any()):
            problemas.append(
                f"REALTIME_START_ANTES_DE_OBS_DATE {etiqueta}: "
                "alguna versión es anterior al período que describe"
            )

        ordenado = grupo.sort_values("realtime_start", kind="mergesort")
        for i in range(len(ordenado) - 1):
            fin_actual = ordenado.iloc[i]["realtime_end"]
            inicio_siguiente = ordenado.iloc[i + 1]["realtime_start"]

            if pd.isna(fin_actual) or pd.isna(inicio_siguiente):
                problemas.append(
                    f"VENTANAS_INCONSISTENTES {etiqueta}: "
                    "hay una ventana con fechas nulas"
                )
                continue

            if fin_actual == _VIGENTE_HASTA:
                problemas.append(
                    f"VENTANAS_INCONSISTENTES {etiqueta}: "
                    "una versión vigente para siempre tiene otra posterior"
                )
                continue

            esperado = fin_actual + pd.Timedelta(days=1)
            if inicio_siguiente != esperado:
                problemas.append(
                    f"VENTANAS_INCONSISTENTES {etiqueta}: "
                    "las ventanas se superponen o dejan un hueco"
                )

        if not bool((grupo["realtime_end"] == _VIGENTE_HASTA).any()):
            problemas.append(
                f"OBS_DATE_SIN_VERSION_VIGENTE {etiqueta}: "
                "no hay ninguna versión con realtime_end=9999-12-31"
            )

    return problemas


def ultimo_valor_conocido(df: pd.DataFrame, fecha_corte: Any) -> dict[str, Any]:
    """Último valor conocido en `fecha_corte`, sin usar información futura."""
    corte = pd.Timestamp(fecha_corte)

    if df is None or df.empty:
        return _sin_valor_conocido()

    realtime_start = pd.to_datetime(df["realtime_start"])
    realtime_end = pd.to_datetime(df["realtime_end"])

    mask = (realtime_start <= corte) & (realtime_end >= corte)
    if not bool(mask.any()):
        return _sin_valor_conocido()

    posiciones = np.flatnonzero(mask.to_numpy())
    candidatos = df.iloc[posiciones].copy()
    candidatos["obs_date"] = pd.to_datetime(candidatos["obs_date"])
    candidatos["realtime_start"] = pd.to_datetime(candidatos["realtime_start"])

    fila = candidatos.sort_values(
        ["obs_date", "realtime_start"], kind="mergesort"
    ).iloc[-1]

    obs_date = pd.Timestamp(fila["obs_date"])
    return {
        "obs_date": obs_date,
        "value": float(fila["value"]),
        "antiguedad_dias": int((corte - obs_date).days),
    }


def serie_conocida_en(df: pd.DataFrame, fechas_corte: Iterable[Any]) -> pd.DataFrame:
    """Serie del último valor conocido para cada fecha de corte."""
    fechas = pd.DatetimeIndex(fechas_corte)
    n = len(fechas)

    if n == 0:
        return pd.DataFrame(
            {
                "value": pd.Series(dtype="float64"),
                "obs_date_origen": pd.Series(dtype="datetime64[ns]"),
                "antiguedad_dias": pd.Series(dtype="float64"),
            },
            index=fechas,
        )

    valores: list[float] = [np.nan] * n
    obs_origen: list[pd.Timestamp | None] = [None] * n
    antiguedades: list[float] = [np.nan] * n

    if df is not None and not df.empty:
        obs_serie = pd.to_datetime(df["obs_date"])
        realtime_start = pd.to_datetime(df["realtime_start"])
        realtime_end = pd.to_datetime(df["realtime_end"])
        valores_serie = df["value"].astype(float)

        for i, corte in enumerate(fechas):
            mask = (realtime_start <= corte) & (realtime_end >= corte)
            if not bool(mask.any()):
                continue

            posiciones = np.flatnonzero(mask.to_numpy())
            candidatos = pd.DataFrame(
                {
                    "obs_date": obs_serie.iloc[posiciones].to_numpy(),
                    "realtime_start": realtime_start.iloc[posiciones].to_numpy(),
                    "value": valores_serie.iloc[posiciones].to_numpy(),
                }
            )

            fila = candidatos.sort_values(
                ["obs_date", "realtime_start"], kind="mergesort"
            ).iloc[-1]

            obs_date = pd.Timestamp(fila["obs_date"])
            valores[i] = float(fila["value"])
            obs_origen[i] = obs_date
            antiguedades[i] = (corte - obs_date).days

    return pd.DataFrame(
        {
            "value": np.asarray(valores, dtype=float),
            "obs_date_origen": pd.to_datetime(obs_origen).to_numpy(),
            "antiguedad_dias": np.asarray(antiguedades, dtype=float),
        },
        index=fechas,
    )

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from prl.short_pressure import baselines, evaluation, features, grid


SHORT_NUMERICAS = [
    "short_volume_ratio",
    "short_volume_ratio_zscore_20d",
    "days_to_cover",
    "short_interest_change_pct",
]

PRICE_NUMERICAS = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "drawdown_5d",
    "drawdown_20d",
    "drawdown_60d",
    "dist_sma20",
    "dist_sma50",
    "dist_sma200",
    "rsi_2",
    "rsi_14",
    "realized_vol_20d",
    "rel_volume",
    "zscore_ret_5d",
]

NUMERICAS = SHORT_NUMERICAS + PRICE_NUMERICAS
CONFIRMACIONES = [
    "confirmacion_a",
    "confirmacion_b",
    "confirmacion_c",
    "confirmacion_d",
    "confirmacion_e",
]
COLUMNAS_FEATURES = NUMERICAS + CONFIRMACIONES

BASELINE_NAMES = [
    "baseline_buy_hold",
    "baseline_caida_simple",
    "baseline_price_exhaustion",
    "baseline_short_pressure",
    "baseline_combo_ingenuo",
]


def ajustar_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Ajusta OHLC por el factor adj_close/close.

    Idéntica convención que EXP-005: se multiplican open/high/low/close por
    adj_close/close. Donde close es cero o NaN el factor queda NaN para no
    propagar infinitos.
    """
    out = df.copy()
    if "adj_close" not in out.columns or "close" not in out.columns:
        return out

    close = pd.to_numeric(out["close"], errors="coerce")
    adj_close = pd.to_numeric(out["adj_close"], errors="coerce")
    factor = adj_close / close
    factor = factor.where(close.notna() & (close != 0))

    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce") * factor

    return out


def retorno_forward(precio_cierre: pd.Series, dias: int) -> pd.Series:
    return precio_cierre.shift(-dias) / precio_cierre - 1.0


def _selected_symbols(mask: pd.Series) -> pd.Index:
    if mask is None:
        return pd.Index([])
    try:
        m = mask.fillna(False)
    except Exception:
        m = mask
    try:
        return m[m.astype(bool)].index
    except Exception:
        return pd.Index([])


def _mean_or_nan(serie: pd.Series | None) -> float:
    if serie is None:
        return float("nan")
    try:
        vals = pd.Series(serie).dropna()
    except Exception:
        return float("nan")
    if len(vals) == 0:
        return float("nan")
    return float(vals.mean())


def _stats_from_series(serie: pd.Series | None) -> dict[str, Any]:
    if serie is None:
        return {"media": None, "mediana": None, "frac_positivo": None}
    vals = pd.Series(serie).dropna()
    if len(vals) == 0:
        return {"media": None, "mediana": None, "frac_positivo": None}
    return {
        "media": float(vals.mean()),
        "mediana": float(vals.median()),
        "frac_positivo": float((vals > 0).mean()),
    }


def _es_finito(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is pd.NaT or obj is pd.NA:
        return None
    return obj


def _grupo_o_vacio(
    mapa: dict[str, pd.DataFrame],
    simbolo: str,
    columnas: list[str],
) -> pd.DataFrame:
    if simbolo in mapa:
        return mapa[simbolo]
    return pd.DataFrame(columns=columnas)


def _leer_universo(path: str | Path) -> list[str]:
    texto = Path(path).read_text(encoding="utf-8")
    return [linea.strip() for linea in texto.splitlines() if linea.strip()]


def _construir_tabla_fecha(
    fecha: pd.Timestamp,
    precios: dict[str, pd.DataFrame],
    features_por_simbolo: dict[str, pd.DataFrame],
    retornos_forward: dict[str, dict[int, pd.Series]],
    horizontes: tuple[int, ...],
    min_historia: int,
) -> dict[str, pd.DataFrame] | None:
    crudas: dict[str, pd.Series] = {}
    filas_retorno: dict[str, dict[str, float]] = {}

    for simbolo, df_precio in precios.items():
        feats = features_por_simbolo[simbolo]
        if fecha not in feats.index:
            continue

        # Filas de precio original con índice <= fecha.
        pos = int(df_precio.index.searchsorted(fecha, side="right"))
        if pos < min_historia:
            continue

        fila = feats.loc[fecha]
        if isinstance(fila, pd.DataFrame):
            if fila.empty:
                continue
            fila = fila.iloc[-1]

        if any(col not in fila.index for col in COLUMNAS_FEATURES):
            continue
        if fila[COLUMNAS_FEATURES].isna().any():
            continue

        crudas[simbolo] = fila

        ret_fila: dict[str, float] = {}
        for h in horizontes:
            serie_h = retornos_forward[simbolo].get(h)
            if serie_h is None or fecha not in serie_h.index:
                ret_fila[f"retorno_{h}d"] = float("nan")
            else:
                ret_fila[f"retorno_{h}d"] = float(serie_h.loc[fecha])
        filas_retorno[simbolo] = ret_fila

    if not crudas:
        return None

    features_crudas = pd.DataFrame.from_dict(crudas, orient="index")
    features_crudas = features_crudas.reindex(columns=COLUMNAS_FEATURES)

    percentil_sin_orientar = features_crudas[NUMERICAS].astype(float).rank(pct=True)

    tabla_percentil = percentil_sin_orientar.copy()
    tabla_percentil["SHORT_PRESSURE_SCORE"] = features.SHORT_PRESSURE_SCORE(
        percentil_sin_orientar
    )
    tabla_percentil["PRICE_EXHAUSTION_SCORE"] = features.PRICE_EXHAUSTION_SCORE(
        percentil_sin_orientar
    )
    for col in CONFIRMACIONES:
        tabla_percentil[col] = features_crudas[col]

    retornos = pd.DataFrame.from_dict(filas_retorno, orient="index")
    retornos = retornos.reindex(columns=[f"retorno_{h}d" for h in horizontes])

    return {
        "raw": features_crudas,
        "tabla": tabla_percentil,
        "retornos": retornos,
    }


def _aplicar_baseline(nombre: str, datos_fecha: dict[str, pd.DataFrame]) -> pd.Series:
    tabla = datos_fecha["tabla"]
    raw = datos_fecha["raw"]

    if nombre == "baseline_buy_hold":
        return baselines.baseline_buy_hold(list(tabla.index))
    if nombre == "baseline_caida_simple":
        return baselines.baseline_caida_simple(raw)
    if nombre == "baseline_price_exhaustion":
        return baselines.baseline_price_exhaustion(tabla)
    if nombre == "baseline_short_pressure":
        return baselines.baseline_short_pressure(tabla)
    if nombre == "baseline_combo_ingenuo":
        return baselines.baseline_combo_ingenuo(tabla)

    raise ValueError(f"Baseline desconocido: {nombre}")


def _locked_stats_para_variante(
    variante: dict[str, Any],
    fechas_locked: list[pd.Timestamp],
    datos_por_fecha: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    horizonte: int,
) -> tuple[float, int, pd.Series]:
    valores_por_fecha: dict[pd.Timestamp, float] = {}
    n_senales = 0
    col_ret = f"retorno_{horizonte}d"

    for fecha in fechas_locked:
        datos_fecha = datos_por_fecha.get(fecha)
        if datos_fecha is None:
            continue

        mask = grid.aplicar_bucket(variante, datos_fecha["tabla"])
        seleccionados = _selected_symbols(mask)
        if len(seleccionados) == 0:
            continue

        n_senales += len(seleccionados)
        vals = datos_fecha["retornos"].loc[seleccionados, col_ret].dropna()
        if len(vals) > 0:
            valores_por_fecha[fecha] = float(vals.mean())

    serie = pd.Series(valores_por_fecha, dtype=float).sort_index()
    media = _mean_or_nan(serie)
    return media, n_senales, serie


def run(
    inputs_dir: str | Path,
    short_volume_path: str | Path,
    short_interest_path: str | Path,
    universo_path: str | Path,
    run_dir: str | Path,
    discovery_start: str = "2019-02-01",
    discovery_end: str = "2022-12-31",
    validation_end: str = "2024-06-30",
    locked_end: str = "2026-11-01",
    paso_dias: int = 10,
    min_historia: int = 252,
    horizontes: tuple[int, ...] = (5, 10, 20),
    horizonte_principal: int = 10,
    min_senales_discovery: int = 30,
    max_frac_ticker: float = 0.20,
    n_particiones_pbo: int = 10,
    n_boot: int = 10000,
    n_placebos: int = 1000,
    seed: int = 0,
) -> dict:
    """Ejecuta EXP-004 de forma determinista y escribe results.json."""
    inputs_dir = Path(inputs_dir)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    horizontes = tuple(int(h) for h in horizontes)
    horizonte_principal = int(horizonte_principal)

    discovery_start_ts = pd.Timestamp(discovery_start)
    discovery_end_ts = pd.Timestamp(discovery_end)
    validation_end_ts = pd.Timestamp(validation_end)
    locked_end_ts = pd.Timestamp(locked_end)

    notes: list[str] = []

    universo = _leer_universo(universo_path)
    n_simbolos_universo = len(universo)

    precios: dict[str, pd.DataFrame] = {}
    for simbolo in universo:
        ruta = inputs_dir / f"{simbolo}.parquet"
        if not ruta.exists():
            notes.append(f"{simbolo}: sin archivo de datos, omitido")
            continue

        df = pd.read_parquet(ruta)
        if df.empty:
            notes.append(f"{simbolo}: archivo de datos vacío, omitido")
            continue
        df = df.sort_index()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df = ajustar_ohlc(df)
        precios[simbolo] = df

    n_simbolos_con_datos = len(precios)

    if precios:
        calendario = pd.DatetimeIndex(sorted(set().union(*[set(df.index) for df in precios.values()])))
    else:
        calendario = pd.DatetimeIndex([])

    sv = pd.read_parquet(short_volume_path)
    si = pd.read_parquet(short_interest_path)

    sv_grupos: dict[str, pd.DataFrame] = {}
    si_grupos: dict[str, pd.DataFrame] = {}
    if not sv.empty and "symbol" in sv.columns:
        sv_grupos = {str(k): v for k, v in sv.groupby("symbol", sort=False)}
    if not si.empty and "symbol" in si.columns:
        si_grupos = {str(k): v for k, v in si.groupby("symbol", sort=False)}

    features_por_simbolo: dict[str, pd.DataFrame] = {}
    retornos_forward: dict[str, dict[int, pd.Series]] = {}

    for simbolo, df in precios.items():
        sv_simbolo = _grupo_o_vacio(
            sv_grupos, simbolo, ["date", "symbol", "short_volume_ratio"]
        )
        si_simbolo = _grupo_o_vacio(
            si_grupos,
            simbolo,
            ["symbol", "settlement_date", "days_to_cover", "short_interest_change_pct"],
        )

        feats = features.calcular_features_simbolo(df, sv_simbolo, si_simbolo)
        feats = feats.copy()

        # Forward-fill acotado a las tres fuentes FINRA con huecos de publicación.
        for col in (
            "short_volume_ratio",
            "days_to_cover",
            "short_interest_change_pct",
        ):
            if col in feats.columns:
                feats[col] = feats[col].ffill()

        features_por_simbolo[simbolo] = feats

        ret_h: dict[int, pd.Series] = {}
        for h in horizontes:
            ret_h[h] = retorno_forward(df["close"], h)
        retornos_forward[simbolo] = ret_h

    max_h = max(horizontes) if horizontes else 0
    candidatas = calendario[
        (calendario >= discovery_start_ts) & (calendario <= locked_end_ts)
    ]
    if paso_dias > 0:
        candidatas = candidatas[::paso_dias]

    fechas_corte: list[pd.Timestamp] = []
    for fecha in candidatas:
        pos = int(calendario.searchsorted(fecha))
        if pos + max_h < len(calendario):
            fechas_corte.append(pd.Timestamp(fecha))

    fechas_discovery = [f for f in fechas_corte if f < discovery_end_ts]
    fechas_validation = [
        f for f in fechas_corte if discovery_end_ts <= f <= validation_end_ts
    ]
    fechas_locked = [
        f for f in fechas_corte if validation_end_ts < f <= locked_end_ts
    ]

    fechas_t0 = {
        "discovery": len(fechas_discovery),
        "validation": len(fechas_validation),
        "locked": len(fechas_locked),
        "total": len(fechas_corte),
    }

    datos_por_fecha: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for fecha in fechas_corte:
        datos_fecha = _construir_tabla_fecha(
            fecha,
            precios,
            features_por_simbolo,
            retornos_forward,
            horizontes,
            min_historia,
        )
        if datos_fecha is not None:
            datos_por_fecha[fecha] = datos_fecha

    variantes = grid.build_grid()

    # ------------------------------------------------------------------
    # Filtro de soporte en discovery y selección en validation.
    # ------------------------------------------------------------------
    sobrevivientes: list[dict[str, Any]] = []
    for variante in variantes:
        total_senales = 0
        conteo_simbolos: dict[str, int] = {}

        for fecha in fechas_discovery:
            datos_fecha = datos_por_fecha.get(fecha)
            if datos_fecha is None:
                continue

            mask = grid.aplicar_bucket(variante, datos_fecha["tabla"])
            seleccionados = _selected_symbols(mask)
            if len(seleccionados) == 0:
                continue

            total_senales += len(seleccionados)
            for simbolo in seleccionados:
                conteo_simbolos[str(simbolo)] = conteo_simbolos.get(str(simbolo), 0) + 1

        if total_senales < min_senales_discovery or total_senales == 0:
            continue

        frac_max = max(conteo_simbolos.values()) / float(total_senales)
        if frac_max <= max_frac_ticker:
            sobrevivientes.append(variante)

    if not sobrevivientes:
        resultado = {
            "experiment": "EXP-004",
            "n_simbolos_universo": n_simbolos_universo,
            "n_simbolos_con_datos": n_simbolos_con_datos,
            "fechas_t0": fechas_t0,
            "n_variantes_grid_total": len(variantes),
            "n_variantes_sobreviven_filtro_soporte": 0,
            "variant_id_ganador": None,
            "motivo": "ninguna_variante_pasa_el_filtro_de_soporte",
            "metricas_locked": None,
            "n_horizontes_superados": None,
            "mejor_baseline_10d": None,
            "comparacion_bootstrap_vs_mejor_baseline": None,
            "dsr": None,
            "n_trials_dsr": len(variantes),
            "pbo": None,
            "n_variantes_pbo": None,
            "concentracion": None,
            "leave_one_ticker_out": None,
            "sensibilidad_vecinos": None,
            "placebo": None,
            "label": "INCONCLUSIVE",
            "notes": notes
            + [
                "MFE/MAE/drawdown post-señal/tiempo-a-objetivo fuera de alcance v1",
                "análisis por sector fuera de alcance (sin clasificación GICS)",
                "análisis por régimen bull/bear y vol alta/baja exploratorio-no-incluido-en-v1",
                "baseline 5 (price exhaustion sin short pressure) idéntico al baseline 3 por diseño del pre-registro; reportado una sola vez",
            ],
        }
        resultado_json = _to_jsonable(resultado)
        (run_dir / "results.json").write_text(
            json.dumps(resultado_json, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return resultado_json

    # Media y serie de validation por variante sobreviviente.
    scores_validation: dict[str, float] = {}
    series_validation: dict[str, pd.Series] = {}
    col_principal = f"retorno_{horizonte_principal}d"

    for variante in sobrevivientes:
        vid = str(variante["variant_id"])
        valores: dict[pd.Timestamp, float] = {}

        for fecha in fechas_validation:
            datos_fecha = datos_por_fecha.get(fecha)
            if datos_fecha is None:
                continue

            mask = grid.aplicar_bucket(variante, datos_fecha["tabla"])
            seleccionados = _selected_symbols(mask)
            if len(seleccionados) == 0:
                continue

            vals = datos_fecha["retornos"].loc[seleccionados, col_principal].dropna()
            if len(vals) > 0:
                valores[fecha] = float(vals.mean())

        serie = pd.Series(valores, dtype=float).sort_index()
        series_validation[vid] = serie
        scores_validation[vid] = _mean_or_nan(serie)

    # Mayor media de validation; empate -> primer variant_id alfabético.
    ganador: dict[str, Any] | None = None
    mejor_score = -float("inf")
    for variante in sorted(sobrevivientes, key=lambda v: str(v["variant_id"])):
        vid = str(variante["variant_id"])
        score = scores_validation.get(vid, float("nan"))
        if ganador is None:
            ganador = variante
            mejor_score = score
        elif _es_finito(score) and (
            not _es_finito(mejor_score) or float(score) > float(mejor_score)
        ):
            ganador = variante
            mejor_score = score

    assert ganador is not None
    vid_ganador = str(ganador["variant_id"])

    # ------------------------------------------------------------------
    # Locked test: ganador + los cinco baselines.
    # ------------------------------------------------------------------
    locked_series: dict[str, dict[int, dict[pd.Timestamp, float]]] = {
        nombre: {h: {} for h in horizontes} for nombre in ["ganador"] + BASELINE_NAMES
    }
    ganador_registros: list[dict[str, Any]] = []

    for fecha in fechas_locked:
        datos_fecha = datos_por_fecha.get(fecha)
        if datos_fecha is None:
            continue

        mascaras: dict[str, pd.Series] = {
            "ganador": grid.aplicar_bucket(ganador, datos_fecha["tabla"])
        }
        for nombre in BASELINE_NAMES:
            mascaras[nombre] = _aplicar_baseline(nombre, datos_fecha)

        for nombre, mask in mascaras.items():
            seleccionados = _selected_symbols(mask)
            if len(seleccionados) == 0:
                continue

            for h in horizontes:
                col = f"retorno_{h}d"
                vals = datos_fecha["retornos"].loc[seleccionados, col].dropna()
                if len(vals) > 0:
                    locked_series[nombre][h][fecha] = float(vals.mean())

            if nombre == "ganador":
                for simbolo in seleccionados:
                    try:
                        ret = float(
                            datos_fecha["retornos"].loc[simbolo, col_principal]
                        )
                    except Exception:
                        ret = float("nan")
                    ganador_registros.append(
                        {
                            "symbol": str(simbolo),
                            "ticker": str(simbolo),
                            col_principal: ret,
                        }
                    )

    series_locked: dict[str, dict[int, pd.Series]] = {}
    for nombre in ["ganador"] + BASELINE_NAMES:
        series_locked[nombre] = {}
        for h in horizontes:
            series_locked[nombre][h] = pd.Series(
                locked_series[nombre][h], dtype=float
            ).sort_index()

    metricas_locked: dict[str, dict[str, dict[str, Any]]] = {}
    for nombre in ["ganador"] + BASELINE_NAMES:
        metricas_locked[nombre] = {}
        for h in horizontes:
            metricas_locked[nombre][str(h)] = _stats_from_series(
                series_locked[nombre][h]
            )

    # ------------------------------------------------------------------
    # Horizontes superados y mejor baseline en el horizonte principal.
    # ------------------------------------------------------------------
    medias_locked: dict[str, dict[int, float]] = {
        nombre: {
            h: _mean_or_nan(series_locked[nombre][h]) for h in horizontes
        }
        for nombre in ["ganador"] + BASELINE_NAMES
    }

    n_horizontes_superados = 0
    for h in horizontes:
        media_ganador = medias_locked["ganador"][h]
        if not _es_finito(media_ganador):
            continue
        medias_baselines = [
            medias_locked[nombre][h]
            for nombre in BASELINE_NAMES
            if _es_finito(medias_locked[nombre][h])
        ]
        if medias_baselines and float(media_ganador) > max(medias_baselines):
            n_horizontes_superados += 1

    mejor_baseline_10d: str | None = None
    mejor_baseline_valor = -float("inf")
    for nombre in BASELINE_NAMES:
        valor = medias_locked[nombre][horizonte_principal]
        if _es_finito(valor) and (
            mejor_baseline_10d is None or float(valor) > mejor_baseline_valor
        ):
            mejor_baseline_10d = nombre
            mejor_baseline_valor = float(valor)

    # ------------------------------------------------------------------
    # Bootstrap pareado contra el mejor baseline en el horizonte principal.
    # ------------------------------------------------------------------
    mejor_frac_bootstrap = float("nan")
    comparacion_bootstrap: dict[str, Any] | None = None

    if mejor_baseline_10d is not None:
        serie_ganador = series_locked["ganador"][horizonte_principal]
        serie_baseline = series_locked[mejor_baseline_10d][horizonte_principal]
        alineadas = pd.concat(
            [serie_ganador, serie_baseline], axis=1, join="inner"
        ).dropna()
        if len(alineadas) > 0:
            try:
                comparacion_bootstrap = evaluation.comparacion_bootstrap(
                    alineadas.iloc[:, 0],
                    alineadas.iloc[:, 1],
                    tamano_bloque=2,
                    n_replicas=n_boot,
                    seed=seed,
                )
                if isinstance(comparacion_bootstrap, dict):
                    for key in ("frac_supera_baseline", "frac_supera", "frac"):
                        if key in comparacion_bootstrap:
                            mejor_frac_bootstrap = float(comparacion_bootstrap[key])
                            break
            except Exception:
                comparacion_bootstrap = None
                notes.append("bootstrap pareado no calculable")
        else:
            notes.append("bootstrap pareado sin fechas comunes ganador-baseline")
    else:
        notes.append("bootstrap pareado sin baseline válido en el horizonte principal")

    if not _es_finito(mejor_frac_bootstrap):
        if comparacion_bootstrap is None:
            comparacion_bootstrap = {"frac_supera_baseline": None}

    # ------------------------------------------------------------------
    # DSR del ganador en validation.
    # ------------------------------------------------------------------
    serie_dsr = series_validation.get(vid_ganador, pd.Series(dtype=float)).dropna()
    if len(serie_dsr) > 0:
        try:
            dsr = float(
                evaluation.deflated_sharpe_ratio(serie_dsr, n_trials=len(variantes))
            )
        except Exception:
            dsr = float("nan")
            notes.append("DSR no calculable")
    else:
        dsr = float("nan")
        notes.append("DSR sin observaciones de validation del ganador")

    # ------------------------------------------------------------------
    # PBO sobre discovery + validation.
    # ------------------------------------------------------------------
    pbo: float | None = None
    n_variantes_pbo = 0

    fechas_pbo = sorted(set(fechas_discovery + fechas_validation))
    if len(sobrevivientes) < 2 or n_particiones_pbo < 2:
        notes.append("PBO no calculable: menos de 2 variantes o particiones insuficientes")
    elif len(fechas_pbo) < n_particiones_pbo:
        notes.append("PBO no calculable: pocas fechas para las particiones pedidas")
    else:
        tam_bloque = len(fechas_pbo) // n_particiones_pbo
        if tam_bloque < 1:
            notes.append("PBO no calculable: tamaño de bloque menor a 1")
        else:
            fechas_truncadas = fechas_pbo[: tam_bloque * n_particiones_pbo]
            bloques = [
                fechas_truncadas[i * tam_bloque : (i + 1) * tam_bloque]
                for i in range(n_particiones_pbo)
            ]

            columnas_validas: dict[str, list[float]] = {}
            for variante in sobrevivientes:
                medias_bloque: list[float] = []
                valido = True

                for bloque in bloques:
                    valores_bloque: list[float] = []
                    for fecha in bloque:
                        datos_fecha = datos_por_fecha.get(fecha)
                        if datos_fecha is None:
                            continue
                        mask = grid.aplicar_bucket(variante, datos_fecha["tabla"])
                        seleccionados = _selected_symbols(mask)
                        if len(seleccionados) == 0:
                            continue
                        vals = datos_fecha["retornos"].loc[
                            seleccionados, col_principal
                        ].dropna()
                        valores_bloque.extend(vals.tolist())

                    if len(valores_bloque) == 0:
                        valido = False
                        break
                    medias_bloque.append(float(np.mean(valores_bloque)))

                if valido:
                    columnas_validas[str(variante["variant_id"])] = medias_bloque

            n_variantes_pbo = len(columnas_validas)
            if n_variantes_pbo < 2:
                notes.append(
                    "PBO no calculable: menos de 2 variantes con señal en todos los bloques"
                )
            else:
                matriz_desempeno = pd.DataFrame(
                    {
                        vid: columnas_validas[vid]
                        for vid in sorted(columnas_validas)
                    },
                    index=range(n_particiones_pbo),
                )
                try:
                    pbo = float(
                        evaluation.probabilidad_backtest_overfitting(
                            matriz_desempeno,
                            n_particiones=n_particiones_pbo,
                        )
                    )
                except Exception:
                    pbo = None
                    notes.append("PBO no calculable por error en la evaluación")

    # ------------------------------------------------------------------
    # Concentración y leave-one-ticker-out en locked.
    # ------------------------------------------------------------------
    if ganador_registros:
        senales_locked_df = pd.DataFrame(ganador_registros)
    else:
        senales_locked_df = pd.DataFrame(
            columns=["symbol", "ticker", col_principal]
        )

    if len(senales_locked_df) > 0:
        try:
            concentracion = evaluation.concentracion_maxima(senales_locked_df)
        except Exception:
            concentracion = {
                "frac_max_ticker": 0.0,
                "n_senales": len(senales_locked_df),
            }
            notes.append("concentración no calculable; se usa frac_max_ticker=0")

        try:
            leave_one_ticker_out = evaluation.leave_one_ticker_out_signo(
                senales_locked_df,
                columna_retorno=col_principal,
            )
        except Exception:
            leave_one_ticker_out = {"revierte_con_algun_ticker": False}
            notes.append("leave-one-ticker-out no calculable")
    else:
        concentracion = {"frac_max_ticker": 0.0, "n_senales": 0}
        leave_one_ticker_out = {"revierte_con_algun_ticker": False}
        notes.append("sin señales del ganador en locked")

    frac_max_ticker_locked = float(concentracion.get("frac_max_ticker", 0.0) or 0.0)
    revierte_con_algun_ticker = bool(
        leave_one_ticker_out.get("revierte_con_algun_ticker", False)
    )

    # ------------------------------------------------------------------
    # Sensibilidad a vecinos (umbrales numéricos, confirmaciones fijas).
    # ------------------------------------------------------------------
    media_ganador_locked = medias_locked["ganador"][horizonte_principal]

    def _detalle_vecino(valor_sp: float, valor_pe: float, conf: tuple[str, ...]) -> dict:
        variante_vecina = {
            "variant_id": (
                f"sp{int(round(valor_sp * 100))}_"
                f"pe{int(round(valor_pe * 100))}_"
                f"conf{''.join(conf) if conf else 'ninguna'}"
            ),
            "umbral_short_pressure": float(valor_sp),
            "umbral_price_exhaustion": float(valor_pe),
            "confirmaciones": tuple(conf),
        }
        media, n_senales, _ = _locked_stats_para_variante(
            variante_vecina,
            fechas_locked,
            datos_por_fecha,
            horizonte_principal,
        )
        return {
            "umbral_short_pressure": float(valor_sp),
            "umbral_price_exhaustion": float(valor_pe),
            "media": None if not _es_finito(media) else float(media),
            "n_senales": int(n_senales),
        }

    sp_ganador = float(ganador["umbral_short_pressure"])
    pe_ganador = float(ganador["umbral_price_exhaustion"])
    conf_ganador = tuple(ganador["confirmaciones"])

    umbrales_sp = list(grid.UMBRALES_SHORT_PRESSURE)
    umbrales_pe = list(grid.UMBRALES_PRICE_EXHAUSTION)

    idx_sp = umbrales_sp.index(sp_ganador)
    idx_pe = umbrales_pe.index(pe_ganador)

    vecinos_sp: list[dict] = []
    for idx in (idx_sp - 1, idx_sp + 1):
        if 0 <= idx < len(umbrales_sp):
            vecinos_sp.append(
                _detalle_vecino(umbrales_sp[idx], pe_ganador, conf_ganador)
            )

    vecinos_pe: list[dict] = []
    for idx in (idx_pe - 1, idx_pe + 1):
        if 0 <= idx < len(umbrales_pe):
            vecinos_pe.append(
                _detalle_vecino(sp_ganador, umbrales_pe[idx], conf_ganador)
            )

    vecino_revierte_signo = False
    vecino_destruye_mas_50pct = False

    if _es_finito(media_ganador_locked):
        mg = float(media_ganador_locked)
        medias_vecinas = [
            float(v["media"])
            for v in vecinos_sp + vecinos_pe
            if v["media"] is not None and _es_finito(v["media"])
        ]

        if mg > 0:
            vecino_revierte_signo = any(m < 0 for m in medias_vecinas)
        elif mg < 0:
            vecino_revierte_signo = any(m > 0 for m in medias_vecinas)

        if mg > 0:
            vecino_destruye_mas_50pct = any(m < 0.5 * mg for m in medias_vecinas)
        elif mg < 0:
            vecino_destruye_mas_50pct = any(m > 0.5 * mg for m in medias_vecinas)

    sensibilidad_vecinos = {
        "confirmaciones_fijas": list(conf_ganador),
        "media_ganador": None if not _es_finito(media_ganador_locked) else float(media_ganador_locked),
        "short_pressure": vecinos_sp,
        "price_exhaustion": vecinos_pe,
        "vecino_revierte_signo": bool(vecino_revierte_signo),
        "vecino_destruye_mas_50pct": bool(vecino_destruye_mas_50pct),
    }

    # ------------------------------------------------------------------
    # Placebo aleatorio.
    # ------------------------------------------------------------------
    pool_valores: list[float] = []
    for fecha in fechas_locked:
        datos_fecha = datos_por_fecha.get(fecha)
        if datos_fecha is None:
            continue
        vals = datos_fecha["retornos"][col_principal].dropna()
        pool_valores.extend(float(x) for x in vals.tolist())

    pool_retornos = pd.Series(pool_valores, dtype=float)
    n_senales_locked = len(ganador_registros)

    if ganador_registros:
        ret_real = pd.Series(
            [r[col_principal] for r in ganador_registros], dtype=float
        ).dropna()
        media_real = float(ret_real.mean()) if len(ret_real) > 0 else float("nan")
    else:
        media_real = float("nan")

    placebo_distingue: bool | None = None
    percentil_placebo: float = float("nan")
    n_placebos_calculados = 0

    if n_senales_locked > 0 and len(pool_retornos) > 0 and _es_finito(media_real):
        try:
            placebos = evaluation.placebo_aleatorio(
                pool_retornos,
                n_senales=n_senales_locked,
                n_placebos=n_placebos,
                seed=seed,
            )
            placebos = np.asarray(placebos)
            n_placebos_calculados = int(len(placebos))
            percentil_placebo = float(
                evaluation.percentil_real_vs_placebo(media_real, placebos)
            )
            if _es_finito(percentil_placebo):
                placebo_distingue = bool(
                    percentil_placebo >= 0.95 or percentil_placebo <= 0.05
                )
        except Exception:
            notes.append("placebo no calculable")
            placebo_distingue = None
    else:
        notes.append("placebo no calculable: sin señales o sin pool en locked")

    placebo = {
        "n_senales_locked": int(n_senales_locked),
        "media_real": None if not _es_finito(media_real) else float(media_real),
        "percentil_real_vs_placebo": (
            None if not _es_finito(percentil_placebo) else float(percentil_placebo)
        ),
        "placebo_distingue": placebo_distingue,
        "n_placebos": int(n_placebos_calculados),
    }

    # ------------------------------------------------------------------
    # Etiqueta final.
    # ------------------------------------------------------------------
    frac_para_etiqueta = (
        0.0 if not _es_finito(mejor_frac_bootstrap) else float(mejor_frac_bootstrap)
    )
    dsr_para_etiqueta = float(dsr) if _es_finito(dsr) else float("nan")

    try:
        label = evaluation.etiqueta(
            n_horizontes_superados=n_horizontes_superados,
            mejor_frac_bootstrap=frac_para_etiqueta,
            dsr=dsr_para_etiqueta,
            n_senales_locked=n_senales_locked,
            frac_max_ticker=frac_max_ticker_locked,
            vecino_revierte_signo=vecino_revierte_signo,
            vecino_destruye_mas_50pct=vecino_destruye_mas_50pct,
            placebo_distingue=placebo_distingue,
        )
    except Exception:
        label = "INCONCLUSIVE"

    if revierte_con_algun_ticker:
        label = "REJECTED"

    if label not in {"VALIDATED", "REJECTED", "INCONCLUSIVE"}:
        label = "INCONCLUSIVE"

    notes.extend(
        [
            "MFE/MAE/drawdown post-señal/tiempo-a-objetivo fuera de alcance v1",
            "análisis por sector fuera de alcance (sin clasificación GICS)",
            "análisis por régimen bull/bear y vol alta/baja exploratorio-no-incluido-en-v1",
            "baseline 5 (price exhaustion sin short pressure) idéntico al baseline 3 por diseño del pre-registro; reportado una sola vez",
        ]
    )

    resultado = {
        "experiment": "EXP-004",
        "n_simbolos_universo": n_simbolos_universo,
        "n_simbolos_con_datos": n_simbolos_con_datos,
        "fechas_t0": fechas_t0,
        "n_variantes_grid_total": len(variantes),
        "n_variantes_sobreviven_filtro_soporte": len(sobrevivientes),
        "variant_id_ganador": vid_ganador,
        "motivo": None,
        "metricas_locked": metricas_locked,
        "n_horizontes_superados": int(n_horizontes_superados),
        "mejor_baseline_10d": mejor_baseline_10d,
        "comparacion_bootstrap_vs_mejor_baseline": comparacion_bootstrap,
        "dsr": None if not _es_finito(dsr) else float(dsr),
        "n_trials_dsr": len(variantes),
        "pbo": pbo,
        "n_variantes_pbo": int(n_variantes_pbo),
        "concentracion": concentracion,
        "leave_one_ticker_out": leave_one_ticker_out,
        "sensibilidad_vecinos": sensibilidad_vecinos,
        "placebo": placebo,
        "label": label,
        "notes": notes,
    }

    resultado_json = _to_jsonable(resultado)
    (run_dir / "results.json").write_text(
        json.dumps(resultado_json, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return resultado_json

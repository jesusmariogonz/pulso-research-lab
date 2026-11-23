from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from prl.reverse_winners import baselines, evaluation, features, grid


COLS_FEATURES: List[str] = [
    "mom_5d",
    "mom_10d",
    "mom_20d",
    "dist_sma20",
    "dist_sma50",
    "dist_sma200",
    "golden_cross",
    "atr14",
    "vol_realizada_20d",
    "vol_relativo_20d",
    "volume_spike_z",
    "rsi14",
    "drawdown_60d",
    "gap",
    "fuerza_relativa_20d",
    "beta_60d",
    "sharpe_20d",
    "dist_max20",
    "dist_min20",
    "aceleracion",
]


# ---------------------------------------------------------------------------
# Funciones puras auxiliares
# ---------------------------------------------------------------------------


def ajustar_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Ajusta OHLC por splits/dividendos usando adj_close / close."""
    close = df["close"]
    adj = df["adj_close"]
    factor = adj / close
    factor = factor.mask(close.isna() | (close == 0.0))
    out = pd.DataFrame(
        {
            "open": df["open"] * factor,
            "high": df["high"] * factor,
            "low": df["low"] * factor,
            "close": adj,
            "volume": df["volume"],
        },
        index=df.index,
    )
    return out


def fechas_t0(
    calendario: pd.DatetimeIndex, inicio: str, paso: int = 10
) -> pd.DatetimeIndex:
    """Toma una de cada `paso` fechas desde `inicio`."""
    ts_inicio = pd.Timestamp(inicio)
    sub = calendario[calendario >= ts_inicio]
    return sub[::paso]


def retorno_forward(precio_cierre: pd.Series, dias: int) -> pd.Series:
    """Retorno forward a `dias` sesiones."""
    return precio_cierre.shift(-dias) / precio_cierre - 1.0


# ---------------------------------------------------------------------------
# Serialización determinista
# ---------------------------------------------------------------------------


def _limpiar(obj: Any) -> Any:
    """Convierte recursivamente a tipos JSON-safe (NaN/NaT -> None)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _limpiar(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_limpiar(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_limpiar(v) for v in obj.tolist()]
    if obj is pd.NaT:
        return None
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, str):
        return obj
    return obj


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _serie_por_fecha(senales: List[dict]) -> pd.Series:
    """Serie indexada por fecha = media de retorno_30d por fecha."""
    if not senales:
        return pd.Series(dtype=float)
    df = pd.DataFrame(senales)
    if "fecha" not in df.columns or "retorno_30d" not in df.columns:
        return pd.Series(dtype=float)
    grupo = df.groupby("fecha")["retorno_30d"].mean()
    return grupo


def _metricas(senales: List[dict]) -> Dict[str, Optional[float]]:
    """Métricas descriptivas de un conjunto de señales."""
    vacio = {
        "media": None,
        "mediana": None,
        "frac_positivo": None,
        "retorno_10d": None,
        "retorno_20d": None,
        "retorno_60d": None,
    }
    if not senales:
        return vacio
    r30 = np.array([s["retorno_30d"] for s in senales], dtype=float)
    r10 = np.array([s["retorno_10d"] for s in senales], dtype=float)
    r20 = np.array([s["retorno_20d"] for s in senales], dtype=float)
    r60 = np.array([s["retorno_60d"] for s in senales], dtype=float)

    def _media(arr: np.ndarray) -> Optional[float]:
        v = arr[~np.isnan(arr)]
        if v.size == 0:
            return None
        return float(v.mean())

    def _mediana(arr: np.ndarray) -> Optional[float]:
        v = arr[~np.isnan(arr)]
        if v.size == 0:
            return None
        return float(np.median(v))

    v30 = r30[~np.isnan(r30)]
    frac_pos = float((v30 > 0).mean()) if v30.size > 0 else None
    return {
        "media": _media(r30),
        "mediana": _mediana(r30),
        "frac_positivo": frac_pos,
        "retorno_10d": _media(r10),
        "retorno_20d": _media(r20),
        "retorno_60d": _media(r60),
    }


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------


def run(
    inputs_dir,
    universo_path,
    run_dir,
    benchmark: str = "SPY",
    discovery_start: str = "2010-01-01",
    discovery_end: str = "2018-12-31",
    validation_end: str = "2021-12-31",
    paso_dias: int = 10,
    min_historia: int = 252,
    ventana_forward: int = 30,
    pct_ganadores: float = 0.10,
    umbral_correlacion: float = 0.05,
    max_features: int = 5,
    min_senales_discovery: int = 30,
    max_frac_ticker: float = 0.20,
    n_particiones_pbo: int = 10,
    n_boot: int = 10000,
    n_placebos: int = 1000,
    seed: int = 0,
) -> dict:
    """Ejecuta EXP-005 end-to-end y escribe run_dir/results.json."""
    inputs_dir = Path(inputs_dir)
    universo_path = Path(universo_path)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "results.json"

    notes: List[str] = [
        "Fuerza relativa vs. sector fuera de alcance v1 (sin clasificación sectorial).",
        "Concentración por sector fuera de alcance v1.",
        "MFE, MAE, máximo drawdown post-señal y tiempo-a-objetivo (+5%/+10%) fuera de alcance v1.",
        "Autocorrelación serial por solapamiento de ventanas forward de 30 días con paso de 10 sesiones declarada.",
    ]

    # --- 1. Universo -------------------------------------------------------- #
    try:
        lineas = universo_path.read_text().splitlines()
    except Exception:
        lineas = []
    simbolos = [s.strip() for s in lineas if s.strip()]

    # Benchmark
    benchmark_df: Optional[pd.DataFrame] = None
    try:
        bpath = inputs_dir / f"{benchmark}.parquet"
        if bpath.exists():
            benchmark_df = ajustar_ohlc(pd.read_parquet(bpath)).sort_index()
    except Exception:
        benchmark_df = None

    if benchmark_df is None or len(benchmark_df) == 0:
        results = {
            "experiment": "EXP-005",
            "n_simbolos_universo": len(simbolos),
            "n_simbolos_con_datos": 0,
            "fechas_t0": {"discovery": 0, "validation": 0, "locked": 0},
            "features_discriminantes": [],
            "direcciones": {},
            "n_variantes_grid_total": 0,
            "n_variantes_sobreviven_filtro_soporte": 0,
            "variant_id_ganador": None,
            "motivo": "sin_benchmark",
            "metricas_locked": {},
            "comparacion_bootstrap_vs_baseline1": {},
            "dsr": None,
            "n_trials_dsr": 0,
            "pbo": None,
            "n_variantes_pbo": 0,
            "concentracion": {},
            "leave_one_ticker_out": {},
            "sensibilidad_vecinos": {},
            "placebo": {},
            "label": "INCONCLUSIVE",
            "notes": notes + [f"Benchmark {benchmark} sin datos, no se puede ejecutar."],
        }
        out_path.write_text(
            json.dumps(_limpiar(results), sort_keys=True, ensure_ascii=False, indent=2)
        )
        return results

    datos: Dict[str, pd.DataFrame] = {}
    simbolos_con_datos: List[str] = []
    for sym in simbolos:
        p = inputs_dir / f"{sym}.parquet"
        if not p.exists():
            notes.append(f"{sym}: sin archivo de datos, omitido")
            continue
        try:
            df = ajustar_ohlc(pd.read_parquet(p)).sort_index()
        except Exception:
            notes.append(f"{sym}: sin archivo de datos, omitido")
            continue
        if len(df) == 0:
            notes.append(f"{sym}: sin archivo de datos, omitido")
            continue
        datos[sym] = df
        simbolos_con_datos.append(sym)

    # --- 2. Features por símbolo (historia completa) ------------------------ #
    features_por_simbolo: Dict[str, dict] = {}
    for sym, df in datos.items():
        try:
            df_bench = benchmark_df.reindex(df.index)
            feats = features.calcular_features_simbolo(df, df_bench)
        except Exception:
            continue
        close = df["close"]
        rets = {
            10: retorno_forward(close, 10),
            20: retorno_forward(close, 20),
            30: retorno_forward(close, 30),
            60: retorno_forward(close, 60),
        }
        features_por_simbolo[sym] = {
            "df_feat": feats,
            "idx": feats.index,
            "rets": rets,
        }

    simbolos_validos = [s for s in simbolos_con_datos if s in features_por_simbolo]

    # --- 3. Fechas de corte ------------------------------------------------- #
    calendario = benchmark_df.index
    fechas = fechas_t0(calendario, inicio=discovery_start, paso=paso_dias)
    if len(fechas) > 0 and ventana_forward > 0:
        n_cal = len(calendario)
        positions = np.searchsorted(calendario.values, fechas.values, side="left")
        keep = positions + ventana_forward < n_cal
        fechas = fechas[keep]

    d_end = pd.Timestamp(discovery_end)
    v_end = pd.Timestamp(validation_end)
    f_discovery = [f for f in fechas if f <= d_end]
    f_validation = [f for f in fechas if (f > d_end) and (f <= v_end)]
    f_locked = [f for f in fechas if f > v_end]

    fechas_todas = list(f_discovery) + list(f_validation) + list(f_locked)

    # --- 4. Tabla cross-sectional por fecha (precalculada) ------------------ #
    def cross_section(fecha: pd.Timestamp):
        filas: Dict[str, pd.Series] = {}
        r30_d: Dict[str, float] = {}
        r10_d: Dict[str, float] = {}
        r20_d: Dict[str, float] = {}
        r60_d: Dict[str, float] = {}
        for sym in simbolos_validos:
            info = features_por_simbolo[sym]
            idx = info["idx"]
            try:
                pos = int(idx.searchsorted(fecha, side="right")) - 1
            except Exception:
                pos = -1
            if pos < 0:
                continue
            if (pos + 1) < min_historia:
                continue
            fila = info["df_feat"].iloc[pos]
            if fila.isna().any():
                continue
            filas[sym] = fila
            try:
                r30_d[sym] = float(info["rets"][30].iloc[pos])
            except Exception:
                r30_d[sym] = float("nan")
            try:
                r10_d[sym] = float(info["rets"][10].iloc[pos])
            except Exception:
                r10_d[sym] = float("nan")
            try:
                r20_d[sym] = float(info["rets"][20].iloc[pos])
            except Exception:
                r20_d[sym] = float("nan")
            try:
                r60_d[sym] = float(info["rets"][60].iloc[pos])
            except Exception:
                r60_d[sym] = float("nan")

        if not filas:
            empty_fc = pd.DataFrame(columns=COLS_FEATURES)
            empty_s = pd.Series(dtype=float)
            return empty_fc, empty_fc.copy(), empty_s, empty_s.copy(), empty_s.copy(), empty_s.copy()

        fc = pd.DataFrame(filas).T
        fc = fc.sort_index()
        for c in COLS_FEATURES:
            if c not in fc.columns:
                fc[c] = np.nan
        fc = fc[COLS_FEATURES]
        # golden_cross puede ser nullable boolean; convertir a float para rank
        if "golden_cross" in fc.columns:
            fc["golden_cross"] = fc["golden_cross"].astype("float64")
        try:
            fp = features.normalizar_percentil_cross_sectional(fc)
        except Exception:
            fp = fc.copy()

        r30 = pd.Series(r30_d, dtype=float).reindex(fc.index)
        r10 = pd.Series(r10_d, dtype=float).reindex(fc.index)
        r20 = pd.Series(r20_d, dtype=float).reindex(fc.index)
        r60 = pd.Series(r60_d, dtype=float).reindex(fc.index)
        return fc, fp, r30, r10, r20, r60

    tablas: Dict[pd.Timestamp, tuple] = {}
    for fecha in fechas_todas:
        tablas[fecha] = cross_section(fecha)

    fechas_t0_counts = {
        "discovery": len(f_discovery),
        "validation": len(f_validation),
        "locked": len(f_locked),
    }

    def _resultado_inconclusivo(motivo: str, extra: Optional[dict] = None) -> dict:
        base = {
            "experiment": "EXP-005",
            "n_simbolos_universo": len(simbolos),
            "n_simbolos_con_datos": len(simbolos_con_datos),
            "fechas_t0": fechas_t0_counts,
            "features_discriminantes": [],
            "direcciones": {},
            "n_variantes_grid_total": 0,
            "n_variantes_sobreviven_filtro_soporte": 0,
            "variant_id_ganador": None,
            "motivo": motivo,
            "metricas_locked": {},
            "comparacion_bootstrap_vs_baseline1": {},
            "dsr": None,
            "n_trials_dsr": 0,
            "pbo": None,
            "n_variantes_pbo": 0,
            "concentracion": {},
            "leave_one_ticker_out": {},
            "sensibilidad_vecinos": {},
            "placebo": {},
            "label": "INCONCLUSIVE",
            "notes": list(notes),
        }
        if extra:
            base.update(extra)
        out_path.write_text(
            json.dumps(_limpiar(base), sort_keys=True, ensure_ascii=False, indent=2)
        )
        return base

    # --- 5. Discovery — discriminación -------------------------------------- #
    tablas_disc: List[pd.DataFrame] = []
    es_gans: List[pd.Series] = []
    for fecha in f_discovery:
        fc, fp, r30, r10, r20, r60 = tablas[fecha]
        if len(fp) == 0:
            continue
        validos = r30.notna()
        if int(validos.sum()) == 0:
            continue
        fp_v = fp.loc[validos].copy()
        r30_v = r30.loc[validos]
        es_g = (r30_v.rank(pct=True) >= (1.0 - pct_ganadores)).astype(bool)
        idx_comp = [f"{fecha.isoformat()}_{s}" for s in fp_v.index]
        fp_v.index = idx_comp
        es_g.index = idx_comp
        tablas_disc.append(fp_v)
        es_gans.append(es_g)

    if not tablas_disc:
        return _resultado_inconclusivo("ninguna_feature_discrimina")

    tabla_apilada = pd.concat(tablas_disc)
    es_ganador_apilado = pd.concat(es_gans)
    es_ganador_apilado = es_ganador_apilado.astype(bool)

    try:
        discriminacion = features.discriminacion_features(
            tabla_apilada, es_ganador_apilado
        )
    except Exception:
        return _resultado_inconclusivo("ninguna_feature_discrimina")

    try:
        features_disc = features.features_discriminantes(
            discriminacion, umbral=umbral_correlacion, max_features=max_features
        )
    except Exception:
        features_disc = []

    if not features_disc:
        return _resultado_inconclusivo("ninguna_feature_discrimina")

    # --- 6. Grilla ---------------------------------------------------------- #
    try:
        direcciones = grid.direccion_features(discriminacion, features_disc)
    except Exception:
        direcciones = {f: "alto" for f in features_disc}

    grid_variantes = grid.build_grid(features_disc, direcciones)
    n_variantes_grid_total = len(grid_variantes)

    # --- 7. Filtro de soporte y selección ----------------------------------- #
    def recolectar(variante: dict, fechas_lista: List[pd.Timestamp]) -> List[dict]:
        senales: List[dict] = []
        for fecha in fechas_lista:
            fc, fp, r30, r10, r20, r60 = tablas[fecha]
            if len(fp) == 0:
                continue
            try:
                sel = grid.aplicar_bucket(variante, fp)
            except Exception:
                continue
            try:
                sel_b = pd.Series(sel, index=fp.index).fillna(False).astype(bool)
            except Exception:
                continue
            for sym in fp.index[sel_b.values]:
                try:
                    r30v = float(r30.loc[sym])
                except Exception:
                    continue
                if pd.isna(r30v):
                    continue
                try:
                    r10v = float(r10.loc[sym])
                except Exception:
                    r10v = float("nan")
                try:
                    r20v = float(r20.loc[sym])
                except Exception:
                    r20v = float("nan")
                try:
                    r60v = float(r60.loc[sym])
                except Exception:
                    r60v = float("nan")
                senales.append(
                    {
                        "fecha": fecha,
                        "ticker": sym,
                        "retorno_30d": r30v,
                        "retorno_10d": r10v,
                        "retorno_20d": r20v,
                        "retorno_60d": r60v,
                    }
                )
        return senales

    sobrevivientes: List[dict] = []
    for var in grid_variantes:
        sens = recolectar(var, f_discovery)
        if len(sens) < min_senales_discovery:
            continue
        try:
            df_sens = pd.DataFrame(sens)
            conc = evaluation.concentracion_maxima(df_sens)
        except Exception:
            continue
        if conc["frac_max_ticker"] > max_frac_ticker:
            continue
        sobrevivientes.append(var)

    if not sobrevivientes:
        return _resultado_inconclusivo(
            "ninguna_variante_pasa_el_filtro_de_soporte",
            extra={
                "features_discriminantes": _lista_features(
                    features_disc, direcciones, discriminacion
                ) if False else _features_out(features_disc, direcciones, discriminacion),
                "direcciones": dict(direcciones),
                "n_variantes_grid_total": n_variantes_grid_total,
            },
        )

    medias_validation: Dict[str, float] = {}
    senales_validation_por_variante: Dict[str, List[dict]] = {}
    for var in sobrevivientes:
        vid = var["variant_id"]
        sens = recolectar(var, f_validation)
        senales_validation_por_variante[vid] = sens
        if sens:
            arr = np.array([s["retorno_30d"] for s in sens], dtype=float)
            arr = arr[~np.isnan(arr)]
            medias_validation[vid] = float(arr.mean()) if arr.size > 0 else float("nan")
        else:
            medias_validation[vid] = float("nan")

    candidatos_ord = sorted(sobrevivientes, key=lambda v: v["variant_id"])
    ganador: Optional[dict] = None
    mejor_media = -np.inf
    for var in candidatos_ord:
        m = medias_validation[var["variant_id"]]
        if pd.isna(m):
            continue
        if ganador is None or m > mejor_media:
            ganador = var
            mejor_media = m
    if ganador is None:
        ganador = candidatos_ord[0]
        mejor_media = float("nan")
    variant_id_ganador = ganador["variant_id"]

    # --- 8. Señales del ganador y baselines en locked ----------------------- #
    senales_ganador_locked = recolectar(ganador, f_locked)

    def senales_baseline(nombre: str) -> List[dict]:
        senales: List[dict] = []
        for fecha in f_locked:
            fc, fp, r30, r10, r20, r60 = tablas[fecha]
            if len(fp) == 0:
                continue
            try:
                if nombre == "momentum":
                    sel = baselines.baseline_momentum_simple(fp, pct=0.20)
                elif nombre == "buy_hold":
                    sel = baselines.baseline_buy_hold(list(fc.index))
                elif nombre == "rsi":
                    sel = baselines.baseline_rsi_simple(fp, pct=0.10)
                elif nombre == "combo":
                    sel = baselines.baseline_combo_ingenuo(fc)
                else:
                    continue
            except Exception:
                continue
            try:
                sel_b = pd.Series(sel, index=fp.index).fillna(False).astype(bool)
            except Exception:
                continue
            for sym in fp.index[sel_b.values]:
                try:
                    r30v = float(r30.loc[sym])
                except Exception:
                    continue
                if pd.isna(r30v):
                    continue
                try:
                    r10v = float(r10.loc[sym])
                except Exception:
                    r10v = float("nan")
                try:
                    r20v = float(r20.loc[sym])
                except Exception:
                    r20v = float("nan")
                try:
                    r60v = float(r60.loc[sym])
                except Exception:
                    r60v = float("nan")
                senales.append(
                    {
                        "fecha": fecha,
                        "ticker": sym,
                        "retorno_30d": r30v,
                        "retorno_10d": r10v,
                        "retorno_20d": r20v,
                        "retorno_60d": r60v,
                    }
                )
        return senales

    baselines_locked = {
        "baseline_momentum_simple": senales_baseline("momentum"),
        "baseline_buy_hold": senales_baseline("buy_hold"),
        "baseline_rsi_simple": senales_baseline("rsi"),
        "baseline_combo_ingenuo": senales_baseline("combo"),
    }

    # --- 9. Métricas descriptivas ------------------------------------------- #
    metricas_locked = {
        "ganador": _metricas(senales_ganador_locked),
        "baseline_momentum_simple": _metricas(
            baselines_locked["baseline_momentum_simple"]
        ),
        "baseline_buy_hold": _metricas(baselines_locked["baseline_buy_hold"]),
        "baseline_rsi_simple": _metricas(baselines_locked["baseline_rsi_simple"]),
        "baseline_combo_ingenuo": _metricas(
            baselines_locked["baseline_combo_ingenuo"]
        ),
    }

    # --- 10. Comparación vs baseline 1 -------------------------------------- #
    media_ganador = metricas_locked["ganador"]["media"]
    supera_los_4_baselines = True
    for nombre in [
        "baseline_momentum_simple",
        "baseline_buy_hold",
        "baseline_rsi_simple",
        "baseline_combo_ingenuo",
    ]:
        mb = metricas_locked[nombre]["media"]
        if media_ganador is None or mb is None:
            supera_los_4_baselines = False
            break
        if not (float(media_ganador) > float(mb)):
            supera_los_4_baselines = False
            break

    serie_ganador_locked = _serie_por_fecha(senales_ganador_locked)
    serie_base1_locked = _serie_por_fecha(baselines_locked["baseline_momentum_simple"])

    comp_boot_out: Dict[str, Any] = {
        "ci_media_bucket": [None, None],
        "frac_supera_baseline": None,
    }
    frac_boot: Optional[float] = None
    if len(serie_ganador_locked) > 0 and len(serie_base1_locked) > 0:
        comunes = serie_ganador_locked.index.intersection(serie_base1_locked.index)
        if len(comunes) >= 2:
            sg = serie_ganador_locked.loc[comunes]
            sb = serie_base1_locked.loc[comunes]
            try:
                comp = evaluation.comparacion_bootstrap(
                    sg,
                    sb,
                    tamano_bloque=2,
                    n_replicas=int(n_boot),
                    seed=int(seed),
                )
                ci = comp.get("ci_media_bucket", (float("nan"), float("nan")))
                frac_boot = float(comp.get("frac_supera_baseline", float("nan")))
                comp_boot_out = {
                    "ci_media_bucket": [
                        None if pd.isna(ci[0]) else float(ci[0]),
                        None if pd.isna(ci[1]) else float(ci[1]),
                    ],
                    "frac_supera_baseline": None
                    if pd.isna(frac_boot)
                    else float(frac_boot),
                }
            except Exception:
                frac_boot = None

    # --- 11. DSR ------------------------------------------------------------ #
    serie_ganador_validation = _serie_por_fecha(
        senales_validation_por_variante.get(variant_id_ganador, [])
    )
    dsr: Optional[float] = None
    if len(serie_ganador_validation) >= 2 and n_variantes_grid_total >= 1:
        try:
            dsr = float(
                evaluation.deflated_sharpe_ratio(
                    serie_ganador_validation, n_trials=int(n_variantes_grid_total)
                )
            )
        except Exception:
            dsr = None
    else:
        dsr = None

    # --- 12. PBO ------------------------------------------------------------ #
    pbo: Optional[float] = None
    n_variantes_pbo = 0
    fechas_dv = sorted(list(f_discovery) + list(f_validation))
    n_part = int(n_particiones_pbo)
    if n_part >= 2 and len(fechas_dv) >= n_part:
        tam = len(fechas_dv) // n_part
        if tam >= 1:
            usadas = fechas_dv[: n_part * tam]
            bloques = [usadas[i * tam : (i + 1) * tam] for i in range(n_part)]
            matriz_data: Dict[str, List[float]] = {}
            for var in sobrevivientes:
                vid = var["variant_id"]
                sens_dv = recolectar(var, fechas_dv)
                if not sens_dv:
                    continue
                por_fecha: Dict[pd.Timestamp, List[float]] = {}
                for s in sens_dv:
                    por_fecha.setdefault(s["fecha"], []).append(s["retorno_30d"])
                medias: List[float] = []
                ok = True
                for bloque in bloques:
                    vals: List[float] = []
                    for f in bloque:
                        if f in por_fecha:
                            vals.extend(por_fecha[f])
                    if not vals:
                        ok = False
                        break
                    arr = np.array(vals, dtype=float)
                    arr = arr[~np.isnan(arr)]
                    if arr.size == 0:
                        ok = False
                        break
                    medias.append(float(arr.mean()))
                if ok:
                    matriz_data[vid] = medias
            if len(matriz_data) >= 2:
                try:
                    cols_ord = sorted(matriz_data.keys())
                    matriz_pbo = pd.DataFrame(
                        {c: matriz_data[c] for c in cols_ord}
                    )
                    pbo = float(
                        evaluation.probabilidad_backtest_overfitting(
                            matriz_pbo, n_part
                        )
                    )
                    n_variantes_pbo = len(matriz_data)
                except Exception:
                    pbo = None
                    n_variantes_pbo = 0
                    notes.append(
                        "PBO no calculado: error en probabilidad_backtest_overfitting."
                    )
            else:
                notes.append(
                    "PBO no calculado: menos de 2 variantes con señales en todos los bloques."
                )
    else:
        notes.append("PBO no calculado: pocas particiones o fechas de discovery+validation.")

    # --- 13. Concentración y leave-one-ticker-out (locked, ganador) --------- #
    if senales_ganador_locked:
        df_gan = pd.DataFrame(senales_ganador_locked)
        try:
            conc_gan = evaluation.concentracion_maxima(df_gan)
        except Exception:
            conc_gan = {"frac_max_ticker": 0.0, "ticker_max": None}
        try:
            ltoo = evaluation.leave_one_ticker_out_signo(
                df_gan, columna_retorno="retorno_30d"
            )
        except Exception:
            ltoo = {
                "signo_original": 0,
                "n_tickers": 0,
                "reversiones": 0,
                "revierte_con_algun_ticker": False,
            }
    else:
        conc_gan = {"frac_max_ticker": 0.0, "ticker_max": None}
        ltoo = {
            "signo_original": 0,
            "n_tickers": 0,
            "reversiones": 0,
            "revierte_con_algun_ticker": False,
        }

    # --- 14. Sensibilidad a vecinos ----------------------------------------- #
    UMB = None
    try:
        UMB = list(grid.UMBRALES)
    except Exception:
        UMB = [0.60, 0.75, 0.90]

    detalles_vecinos: List[dict] = []
    medias_vecinos: List[float] = []
    if ganador.get("umbrales"):
        for feat, info in ganador["umbrales"].items():
            p = float(info["percentil"])
            idx_umb = None
            for i, u in enumerate(UMB):
                if abs(float(u) - p) < 1e-9:
                    idx_umb = i
                    break
            if idx_umb is None:
                continue
            pcts_vecinos: List[float] = []
            if idx_umb - 1 >= 0:
                pcts_vecinos.append(float(UMB[idx_umb - 1]))
            if idx_umb + 1 < len(UMB):
                pcts_vecinos.append(float(UMB[idx_umb + 1]))
            for pv in pcts_vecinos:
                nuevo_umbrales = {
                    k: {"direccion": v["direccion"], "percentil": float(v["percentil"])}
                    for k, v in ganador["umbrales"].items()
                }
                nuevo_umbrales[feat]["percentil"] = float(pv)
                var_vecino = {
                    "variant_id": "|".join(
                        f"{k}:{nuevo_umbrales[k]['direccion']}:{nuevo_umbrales[k]['percentil']:.2f}"
                        for k in nuevo_umbrales
                    ),
                    "umbrales": nuevo_umbrales,
                }
                sens_v = recolectar(var_vecino, f_locked)
                if sens_v:
                    arr = np.array([s["retorno_30d"] for s in sens_v], dtype=float)
                    arr = arr[~np.isnan(arr)]
                    m = float(arr.mean()) if arr.size > 0 else None
                else:
                    m = None
                if m is not None:
                    medias_vecinos.append(m)
                detalles_vecinos.append(
                    {
                        "feature": feat,
                        "percentil": float(pv),
                        "variant_id": var_vecino["variant_id"],
                        "media": m,
                        "n_senales": len(sens_v),
                    }
                )

    vecino_revierte_signo = False
    vecino_destruye_mas_50pct = False
    if media_ganador is not None and float(media_ganador) != 0.0:
        mg = float(media_ganador)
        for m in medias_vecinos:
            if np.sign(m) != np.sign(mg) and m != 0.0:
                vecino_revierte_signo = True
            if abs(m) < 0.5 * abs(mg):
                vecino_destruye_mas_50pct = True

    # --- 15. Placebo -------------------------------------------------------- #
    pool: List[float] = []
    for fecha in f_locked:
        fc, fp, r30, r10, r20, r60 = tablas[fecha]
        for sym in fp.index:
            try:
                r = float(r30.loc[sym])
            except Exception:
                continue
            if pd.notna(r):
                pool.append(r)

    n_senales_locked = len(senales_ganador_locked)
    potencia_confirmada = False
    percentil_placebo: Optional[float] = None
    placebo_distingue: Optional[bool] = None

    if (
        n_senales_locked > 0
        and len(pool) >= n_senales_locked
        and int(n_placebos) > 0
    ):
        try:
            placebos = evaluation.placebo_aleatorio(
                pd.Series(pool, dtype=float),
                n_senales=int(n_senales_locked),
                n_placebos=int(n_placebos),
                seed=int(seed),
            )
            potencia_confirmada = bool(float(np.std(placebos)) > 1e-8)
        except Exception:
            placebos = None
            potencia_confirmada = False
    else:
        placebos = None

    if potencia_confirmada and placebos is not None and media_ganador is not None:
        try:
            percentil_placebo = float(
                evaluation.percentil_real_vs_placebo(float(media_ganador), placebos)
            )
            placebo_distingue = percentil_placebo >= 0.95
        except Exception:
            percentil_placebo = None
            placebo_distingue = None

    # --- 16. Etiqueta ------------------------------------------------------- #
    frac_boot_para_etiqueta = (
        0.0 if (frac_boot is None or pd.isna(frac_boot)) else float(frac_boot)
    )
    dsr_para_etiqueta = (
        float("nan") if dsr is None or pd.isna(dsr) else float(dsr)
    )
    frac_max_para_etiqueta = (
        float(conc_gan["frac_max_ticker"])
        if conc_gan.get("frac_max_ticker") is not None
        else 1.0
    )

    try:
        label_base = evaluation.etiqueta(
            supera_los_4_baselines=bool(supera_los_4_baselines),
            frac_bootstrap_vs_baseline1=frac_boot_para_etiqueta,
            dsr=dsr_para_etiqueta,
            n_senales_locked=int(n_senales_locked),
            frac_max_ticker=frac_max_para_etiqueta,
            vecino_revierte_signo=bool(vecino_revierte_signo),
            vecino_destruye_mas_50pct=bool(vecino_destruye_mas_50pct),
            placebo_distingue=placebo_distingue,
        )
    except Exception:
        label_base = "INCONCLUSIVE"

    if bool(ltoo.get("revierte_con_algun_ticker", False)):
        label = "REJECTED"
    else:
        label = label_base

    # --- 17. results.json --------------------------------------------------- #
    features_discriminantes_out = _features_out(
        features_disc, direcciones, discriminacion
    )

    leave_one_out_out = {
        "signo_original": int(ltoo.get("signo_original", 0)),
        "n_tickers": int(ltoo.get("n_tickers", 0)),
        "reversiones": int(ltoo.get("reversiones", 0)),
        "revierte_con_algun_ticker": bool(ltoo.get("revierte_con_algun_ticker", False)),
    }

    results: Dict[str, Any] = {
        "experiment": "EXP-005",
        "n_simbolos_universo": len(simbolos),
        "n_simbolos_con_datos": len(simbolos_con_datos),
        "fechas_t0": fechas_t0_counts,
        "features_discriminantes": features_discriminantes_out,
        "direcciones": {k: str(v) for k, v in direcciones.items()},
        "n_variantes_grid_total": int(n_variantes_grid_total),
        "n_variantes_sobreviven_filtro_soporte": len(sobrevivientes),
        "variant_id_ganador": variant_id_ganador,
        "motivo": None,
        "metricas_locked": metricas_locked,
        "comparacion_bootstrap_vs_baseline1": comp_boot_out,
        "dsr": None if (dsr is None or pd.isna(dsr)) else float(dsr),
        "n_trials_dsr": int(n_variantes_grid_total),
        "pbo": pbo,
        "n_variantes_pbo": int(n_variantes_pbo),
        "concentracion": {
            "frac_max_ticker": (
                None
                if conc_gan.get("frac_max_ticker") is None
                else float(conc_gan["frac_max_ticker"])
            ),
            "ticker_max": conc_gan.get("ticker_max"),
        },
        "leave_one_ticker_out": leave_one_out_out,
        "sensibilidad_vecinos": {
            "vecino_revierte_signo": bool(vecino_revierte_signo),
            "vecino_destruye_mas_50pct": bool(vecino_destruye_mas_50pct),
            "detalle": detalles_vecinos,
        },
        "placebo": {
            "percentil": percentil_placebo,
            "potencia_confirmada": bool(potencia_confirmada),
            "placebo_distingue": placebo_distingue,
        },
        "label": str(label),
        "notes": list(notes),
    }

    out_path.write_text(
        json.dumps(_limpiar(results), sort_keys=True, ensure_ascii=False, indent=2)
    )
    return results


def _features_out(
    features_disc: List[str], direcciones: dict, discriminacion: pd.DataFrame
) -> List[dict]:
    """Construye la lista serializable de features discriminantes."""
    out: List[dict] = []
    for nombre in features_disc:
        direccion = str(direcciones.get(nombre, "alto"))
        dif = None
        corr = None
        try:
            fila = discriminacion.loc[nombre]
            v_dif = fila["diferencia_medianas"]
            v_corr = fila["correlacion_punto_biserial"]
            dif = None if pd.isna(v_dif) else float(v_dif)
            corr = None if pd.isna(v_corr) else float(v_corr)
        except Exception:
            pass
        out.append(
            {
                "feature": str(nombre),
                "direccion": direccion,
                "diferencia_medianas": dif,
                "correlacion_punto_biserial": corr,
            }
        )
    return out

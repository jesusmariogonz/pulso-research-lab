"""EXP-002 — orquestador: conecta señales, portafolio, backtest y evaluación."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from prl.data import macro_vintage
from prl.growth_max import backtest, evaluation, grid, portfolio, signals

UNIVERSO: list[str] = [
    "SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "EWJ",
    "XLK", "XLE", "XLF", "XLV", "XLP", "XLU", "XLY", "XLI", "XLB",
    "EWG", "EWQ", "EWU", "EWL", "EWI", "EWP", "EWN", "EWA", "EWH", "EWS",
    "EWZ", "EWW", "EWY", "EWT", "MCHI", "INDA", "EIDO", "EZA", "TUR", "EPOL",
    "MTUM", "QUAL", "USMV", "VLUE",
    "TLT", "IEF", "SHY", "BIL", "HYG", "LQD", "TIP", "EMB", "BNDX", "MBB",
    "GLD", "SLV", "USO", "UNG", "DBC", "DBA",
    "UUP", "FXE", "FXY", "FXB", "FXF", "FXC", "FXA",
    "VNQ", "VNQI",
]

_BENCH_RV = ["SPY", "EFA", "EEM"]
_BENCH_RF = ["TLT", "IEF", "LQD"]

_L_LIST = [3, 6, 12]
_W_LIST = [50, 100, 200]
_B_LIST = [55, 252]
_V_LIST = [20, 60]
_Z = 10

_NOTES = [
    "vol_target: aproximación de la volatilidad del portafolio ignorando correlaciones "
    "(raíz de la suma de (peso·vol)²)",
    "universo restringido a ETF/índices; sin acciones individuales ni otros activos",
    "régimen macro limitado a 3 series point-in-time (M2, FED_BALANCE, LEADING)",
]


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _ser(x: Any) -> Any:
    """Convierte recursivamente a tipos serializables en JSON (NaN/NaT → None)."""
    if x is None:
        return None
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        xf = float(x)
        if math.isnan(xf) or math.isinf(xf):
            return None
        return xf
    if isinstance(x, pd.Timestamp):
        return None if pd.isna(x) else x.isoformat()
    if isinstance(x, dict):
        return {str(k): _ser(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_ser(v) for v in x]
    return x


def _leer_precios(inputs_dir: Path, universo: list[str]) -> pd.DataFrame:
    """Arma la matriz de precios (columna adj_close) con unión ordenada de fechas."""
    cols: dict[str, pd.Series] = {}
    for t in universo:
        df = pd.read_parquet(inputs_dir / f"{t}.parquet")
        cols[t] = df["adj_close"].astype(float)
    precios = pd.DataFrame(cols)
    precios = precios.sort_index()
    return precios


def _serie_macro(inputs_dir: Path, nombre: str, fechas: pd.DatetimeIndex) -> pd.Series:
    """Serie point-in-time conocida de un vintage para cada fecha de corte."""
    v = pd.read_parquet(inputs_dir / f"{nombre}.parquet")
    conocida = macro_vintage.serie_conocida_en(v, fechas)
    return conocida["value"].astype(float)


def _combina_liquidez(a: pd.Series, b: pd.Series) -> pd.Series:
    """Promedio de signos de M2 y FED_BALANCE (promedio redondeado al signo)."""
    suma = a + b
    out = pd.Series(np.nan, index=a.index)
    ambas = a.notna() & b.notna()
    out.loc[ambas] = np.sign(suma.loc[ambas])
    solo_a = a.notna() & b.isna()
    out.loc[solo_a] = a.loc[solo_a]
    solo_b = a.isna() & b.notna()
    out.loc[solo_b] = b.loc[solo_b]
    return out


def _pesos_segun_construccion(
    construccion: str,
    param: float | None,
    senales: pd.DataFrame,
    vol: pd.DataFrame,
    mu: pd.DataFrame,
    var: pd.DataFrame,
) -> pd.DataFrame:
    """Despacha al constructor de pesos correspondiente."""
    if construccion == "equal":
        return portfolio.pesos_equal(senales)
    if construccion == "inv_vol":
        return portfolio.pesos_inv_vol(senales, vol)
    if construccion == "vol_target":
        return portfolio.pesos_vol_target(senales, vol, float(param))
    if construccion == "kelly_frac":
        return portfolio.pesos_kelly_frac(senales, mu, var, float(param))
    raise ValueError(f"construccion desconocida: {construccion}")


def _cash_serie(
    politica: str, index: pd.DatetimeIndex, cash_pct_regimen: pd.Series
) -> pd.Series:
    """Serie de cash % según la política pedida."""
    if politica == "cash_0":
        return pd.Series(0.0, index=index)
    if politica == "cash_5":
        return pd.Series(0.05, index=index)
    if politica == "cash_10":
        return pd.Series(0.10, index=index)
    if politica == "cash_20":
        return pd.Series(0.20, index=index)
    if politica == "cash_dinamico":
        return cash_pct_regimen.reindex(index)
    raise ValueError(f"cash_politica desconocida: {politica}")


# --------------------------------------------------------------------------- #
# Función pública auxiliar (testeable de forma aislada)
# --------------------------------------------------------------------------- #
def escalar_por_regimen(
    pesos_base: pd.DataFrame, regimen: pd.Series, k: float
) -> pd.DataFrame:
    """Escala toda la fila por ``k`` cuando hay contracción (régimen 3/4)."""
    contraccion = regimen.isin([3.0, 4.0]).astype(float)
    factor = 1.0 + (k - 1.0) * contraccion
    return pesos_base.mul(factor, axis=0)


# --------------------------------------------------------------------------- #
# Orquestador
# --------------------------------------------------------------------------- #
def run(
    inputs_dir,
    run_dir,
    discovery_end: str = "2015-12-31",
    validation_end: str = "2019-12-31",
    n_boot: int = 500,
    seed: int = 0,
) -> dict:
    """Ejecuta EXP-002 de punta a punta y escribe ``run_dir/results.json``."""
    inputs_dir = Path(inputs_dir)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Universo / precios / retornos -------------------------------------
    precios = _leer_precios(inputs_dir, UNIVERSO)
    retornos = precios.pct_change()
    idx = precios.index

    # 2. Tasa de cash ------------------------------------------------------
    dtb3 = pd.read_parquet(inputs_dir / "DTB3.parquet")["value"].astype(float)
    tasa_cash_anual = dtb3.reindex(idx).ffill()  # fracción (0.02 = 2 %)
    tasa_cash_anual = tasa_cash_anual / 100.0
    tasa_cash_diaria = tasa_cash_anual / 252.0

    # 3. Régimen macro point-in-time --------------------------------------
    m2 = _serie_macro(inputs_dir, "M2", idx)
    fed = _serie_macro(inputs_dir, "FED_BALANCE", idx)
    leading = _serie_macro(inputs_dir, "LEADING", idx)

    m2_sig = signals.signo_cambio_trailing(m2, 126)
    fed_sig = signals.signo_cambio_trailing(fed, 126)
    liquidez = _combina_liquidez(m2_sig, fed_sig)
    crecimiento = signals.signo_cambio_trailing(leading, 126)

    regimen = signals.regimen_macro(liquidez, crecimiento)
    es_rango = signals.es_regimen_de_rango(regimen)
    cash_pct_regimen = portfolio.cash_pct_dinamico(regimen)

    # 4. Señales por combinación única (L, W, B, V) -----------------------
    combos = sorted(
        {
            (v["L_meses"], v["W_dias"], v["B_dias"], v["V_dias"])
            for v in grid.build_grid()
        }
    )

    momentum_cache: dict[int, pd.DataFrame] = {}
    for Lm in _L_LIST:
        momentum_cache[Lm] = pd.DataFrame(
            {t: signals.ts_momentum_signal(precios[t], Lm) for t in precios.columns}
        )[precios.columns]

    trend_cache: dict[int, pd.DataFrame] = {}
    for Wd in _W_LIST:
        trend_cache[Wd] = pd.DataFrame(
            {t: signals.trend_signal(precios[t], Wd) for t in precios.columns}
        )[precios.columns]

    breakout_cache: dict[int, pd.DataFrame] = {}
    for Bd in _B_LIST:
        breakout_cache[Bd] = pd.DataFrame(
            {t: signals.breakout_signal(precios[t], Bd) for t in precios.columns}
        )[precios.columns]

    reversion_cache = pd.DataFrame(
        {t: signals.senal_reversion(precios[t], _Z) for t in precios.columns}
    )[precios.columns]

    vol_cache: dict[int, pd.DataFrame] = {}
    for Vd in _V_LIST:
        vol_cache[Vd] = pd.DataFrame(
            {t: signals.volatilidad_realizada(precios[t], Vd) for t in precios.columns}
        )[precios.columns]

    mu_cache: dict[int, pd.DataFrame] = {}
    var_cache: dict[int, pd.DataFrame] = {}
    for Vd in _V_LIST:
        mu_cache[Vd] = portfolio.retorno_esperado_trailing(retornos, Vd)
        var_cache[Vd] = portfolio.varianza_trailing(retornos, Vd)

    mask_rango = es_rango.reindex(idx).fillna(False).to_numpy(dtype=bool)[:, None]

    combos_data: dict[tuple, dict[str, pd.DataFrame]] = {}
    for Lm, Wd, Bd, Vd in combos:
        stacked = np.stack(
            [
                momentum_cache[Lm].to_numpy(),
                trend_cache[Wd].to_numpy(),
                breakout_cache[Bd].to_numpy(),
            ],
            axis=0,
        )
        cuenta = np.sum(~np.isnan(stacked), axis=0)
        suma = np.nansum(stacked, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            direc_vals = np.where(cuenta > 0, suma / np.maximum(cuenta, 1), np.nan)
        senal_vals = np.where(mask_rango, reversion_cache.to_numpy(), direc_vals)
        senal_final = pd.DataFrame(senal_vals, index=idx, columns=precios.columns)
        combos_data[(Lm, Wd, Bd, Vd)] = {
            "senal": senal_final,
            "vol": vol_cache[Vd],
            "mu": mu_cache[Vd],
            "var": var_cache[Vd],
        }

    # 5. Fecha de inicio del backtest -------------------------------------
    conteo = (~retornos.isna()).sum(axis=1)
    validas = conteo[conteo >= 40]
    fecha_inicio = validas.index[0] if len(validas) > 0 else idx[0]

    # Retornos con columna CASH
    retornos_con_cash = retornos.copy()
    retornos_con_cash["CASH"] = tasa_cash_diaria.to_numpy()

    # Precálculo de pesos base (se reutilizan entre variantes) ------------
    pesos_base_cache: dict[tuple, pd.DataFrame] = {}
    pesos_esc_cache: dict[tuple, pd.DataFrame] = {}
    for key_combo, data in combos_data.items():
        for construccion, param in grid.construccion_parametros():
            pb = _pesos_segun_construccion(
                construccion, param,
                data["senal"], data["vol"], data["mu"], data["var"],
            )
            ck = (key_combo, construccion, param)
            pesos_base_cache[ck] = pb
            for k in (0.5, 0.75):
                pesos_esc_cache[(ck, k)] = escalar_por_regimen(pb, regimen, k)

    d_end = pd.Timestamp(discovery_end)
    v_end = pd.Timestamp(validation_end)

    # 6. Iterar las 17 280 variantes --------------------------------------
    tienda: dict[str, dict[str, Any]] = {}
    for v in grid.build_grid():
        key_combo = (v["L_meses"], v["W_dias"], v["B_dias"], v["V_dias"])
        ck = (key_combo, v["construccion"], v["construccion_param"])
        pesos_esc = pesos_esc_cache[(ck, float(v["k"]))]
        cash_pct = _cash_serie(v["cash_politica"], idx, cash_pct_regimen)
        pesos_finales = portfolio.aplicar_leverage_y_cash(
            pesos_esc, float(v["leverage"]), cash_pct
        )

        pesos_con_cash = pesos_finales.copy()
        pesos_con_cash["CASH"] = cash_pct.to_numpy()

        costo_apal = portfolio.costo_apalancamiento_diario(
            float(v["leverage"]), tasa_cash_anual, float(v["spread"])
        )

        res = backtest.ejecutar_backtest(
            pesos_con_cash, retornos_con_cash, costo_apal, costo_por_lado=0.001
        )
        ret = res["ret"].loc[fecha_inicio:]
        disc = ret.loc[ret.index <= d_end]
        val = ret.loc[(ret.index > d_end) & (ret.index <= v_end)]

        tienda[v["variant_id"]] = {"disc": disc, "val": val, "offset": v}

    # 7. Selección --------------------------------------------------------
    lw_val: dict[str, float] = {}
    pl50: dict[str, float] = {}
    pl75: dict[str, float] = {}

    def _pp(serie: pd.Series, umbral: float) -> float:
        if len(serie) < 20:
            return 1.0
        try:
            return float(
                evaluation.probabilidad_perdida(
                    serie, umbral, tamano_bloque=20, n_replicas=n_boot, seed=seed
                )
            )
        except ValueError:
            return 1.0

    for vid, t in tienda.items():
        disc = t["disc"]
        val = t["val"]
        lw_val[vid] = float(evaluation.tasa_crecimiento_geometrica(val))
        comb = pd.concat([disc, val])
        pl50[vid] = _pp(comb, 0.5)
        pl75[vid] = _pp(comb, 0.75)

    ganador, motivo = evaluation.elegir_variante(lw_val, pl50, pl75)

    # Base de resultados ------------------------------------------------
    results: dict[str, Any] = {
        "experiment": "EXP-002",
        "variant_id_ganador": ganador,
        "motivo_seleccion": motivo,
        "n_variants": 17280,
        "fecha_inicio_backtest": fecha_inicio.isoformat(),
        "discovery_end": str(discovery_end),
        "validation_end": str(validation_end),
        "n_dias_locked_test": 0,
        "niveles": {},
        "comparacion_bootstrap_growth50": {},
        "label": "INCONCLUSIVE",
        "deflated_sharpe": None,
        "percentil_vs_placebo": None,
        "notes": list(_NOTES),
    }

    if ganador is None:
        payload = _ser(results)
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        (run_dir / "results.json").write_text(text, encoding="utf-8")
        return payload

    # 9. Niveles sobre locked_test ---------------------------------------
    v_gan: dict = tienda[ganador]["offset"]
    key_combo = (v_gan["L_meses"], v_gan["W_dias"], v_gan["B_dias"], v_gan["V_dias"])
    ck_gan = (key_combo, v_gan["construccion"], v_gan["construccion_param"])
    pesos_esc_gan = pesos_esc_cache[(ck_gan, float(v_gan["k"]))]

    niveles_spec: dict[str, tuple[str, float]] = {
        "Conservative": ("cash_20", 1.0),
        "Growth25": ("cash_10", 1.0),
        "Growth50": ("cash_5", 1.5),
        "Growth75": ("cash_0", 1.5),
        "Max": ("cash_0", 2.0),
    }

    ret_locked: dict[str, pd.Series] = {}
    niveles_out: dict[str, dict[str, Any]] = {}

    for nombre, (cp, L) in niveles_spec.items():
        cash_pct = _cash_serie(cp, idx, cash_pct_regimen)
        pesos_fin = portfolio.aplicar_leverage_y_cash(pesos_esc_gan, float(L), cash_pct)
        pesos_cc = pesos_fin.copy()
        pesos_cc["CASH"] = cash_pct.to_numpy()
        costo_apal = portfolio.costo_apalancamiento_diario(
            float(L), tasa_cash_anual, float(v_gan["spread"])
        )
        res = backtest.ejecutar_backtest(
            pesos_cc, retornos_con_cash, costo_apal, costo_por_lado=0.001
        )
        ret = res["ret"]
        ret_lk = ret.loc[ret.index > v_end]
        ret_locked[nombre] = ret_lk

        met = backtest.metricas(ret_lk)
        prob: dict[str, Any] = {}
        for u in (0.5, 0.75, 0.9, 0.99):
            prob[str(u)] = _pp(ret_lk, float(u))
        niveles_out[nombre] = {"metricas": met, "probabilidad_ruina": prob}

    # 10. Benchmark ------------------------------------------------------
    pesos_bench = pd.DataFrame(0.0, index=idx, columns=retornos.columns)
    for t in _BENCH_RV:
        if t in pesos_bench.columns:
            pesos_bench[t] = 0.6 / len(_BENCH_RV)
    for t in _BENCH_RF:
        if t in pesos_bench.columns:
            pesos_bench[t] = 0.4 / len(_BENCH_RF)
    pesos_bench["CASH"] = 0.0

    costo_cero = pd.Series(0.0, index=idx)
    res_bench = backtest.ejecutar_backtest(
        pesos_bench, retornos_con_cash, costo_cero, costo_por_lado=0.001
    )
    ret_bench_locked = res_bench["ret"].loc[res_bench["ret"].index > v_end]
    ret_locked["benchmark"] = ret_bench_locked

    # 11. Comparación y etiqueta ----------------------------------------
    comparacion = evaluation.comparacion_bootstrap(
        ret_locked["Growth50"],
        ret_bench_locked,
        tamano_bloque=20,
        n_replicas=n_boot,
        seed=seed,
    )
    prob_75_g50 = niveles_out["Growth50"]["probabilidad_ruina"]["0.75"]
    n_dias_locked = int(len(ret_locked["Growth50"]))
    label = evaluation.etiqueta(
        comparacion["ci_cagr_modelo"],
        float(comparacion["frac_supera_benchmark"]),
        float(prob_75_g50),
        n_dias_locked,
    )

    # 12. Placebo y DSR --------------------------------------------------
    ret_g50 = ret_locked["Growth50"]
    if len(ret_g50) >= 2:
        placebo = evaluation.placebo_circular(ret_g50, n_placebos=n_boot, seed=seed)
        percentil = evaluation.percentil_real_vs_placebo(
            evaluation.tasa_crecimiento_geometrica(ret_g50), placebo
        )
    else:
        percentil = 0.0

    ret_val_gan = tienda[ganador]["val"]
    if len(ret_val_gan) >= 2:
        dsr = evaluation.deflated_sharpe_ratio(ret_val_gan, n_trials=17280)
    else:
        dsr = float("nan")

    results.update(
        {
            "n_dias_locked_test": n_dias_locked,
            "niveles": niveles_out,
            "comparacion_bootstrap_growth50": {
                "ci_cagr_modelo": tuple(comparacion["ci_cagr_modelo"]),
                "frac_supera_benchmark": float(comparacion["frac_supera_benchmark"]),
            },
            "label": label,
            "deflated_sharpe": float(dsr),
            "percentil_vs_placebo": float(percentil),
        }
    )

    payload = _ser(results)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    (run_dir / "results.json").write_text(text, encoding="utf-8")
    return payload

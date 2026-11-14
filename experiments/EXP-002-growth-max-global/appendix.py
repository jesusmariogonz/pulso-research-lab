"""Apéndice EXPLORATORIO de EXP-002 (post-hoc: NO está en el pre-registro).

Re-ejecuta el mismo pipeline de `prl.growth_max.exp002` sobre los datos
congelados reales y calcula diagnósticos adicionales para el reporte técnico:
curvas de capital, rendimientos por año, drawdowns, derivación paso a paso del
Deflated Sharpe, sensibilidad por dimensión de la grilla (17 280 variantes),
Reality Check de White, número efectivo de intentos (muestra), catálogo de
datos y dos placebos (el pre-registrado y uno mejor especificado que rota el
régimen macro en vez del retorno ya realizado).

    python experiments/EXP-002-growth-max-global/appendix.py <inputs_dir> <out_dir>

Determinista (semillas fijas). Verifica primero que reproduce EXACTAMENTE las
métricas publicadas en `results_published.json`; si no coincide, aborta (no
publica nada inconsistente). Toda cifra de este archivo la produce código;
ningún modelo de lenguaje interviene en su cálculo.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from prl.growth_max import backtest, evaluation, grid, portfolio, signals
from prl.growth_max.exp002 import (
    UNIVERSO, _BENCH_RF, _BENCH_RV, _cash_serie, _combina_liquidez,
    _leer_precios, _pesos_segun_construccion, _serie_macro, escalar_por_regimen,
)

GAMMA = 0.5772156649015329
NIVELES_SPEC = {
    "Conservative": ("cash_20", 1.0), "Growth25": ("cash_10", 1.0),
    "Growth50": ("cash_5", 1.5), "Growth75": ("cash_0", 1.5), "Max": ("cash_0", 2.0),
}


def _ser(x):
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        xf = float(x)
        return None if (math.isnan(xf) or math.isinf(xf)) else xf
    if isinstance(x, pd.Timestamp):
        return None if pd.isna(x) else x.isoformat()
    if isinstance(x, dict):
        return {str(k): _ser(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_ser(v) for v in x]
    return x


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _pasos_dsr(n_trials: int, sr_std: float, sr: float) -> dict:
    N = float(n_trials)
    z1 = float(norm.ppf(1.0 - 1.0 / N)) if n_trials > 1 else 0.0
    z2 = float(norm.ppf(1.0 - 1.0 / (N * math.e))) if n_trials > 1 else 0.0
    part1, part2 = (1.0 - GAMMA) * z1, GAMMA * z2
    expected_max_z = part1 + part2
    sr0 = sr_std * expected_max_z if n_trials > 1 else 0.0
    diff = sr - sr0
    z_stat = diff / sr_std
    dsr = float(norm.cdf(z_stat))
    return dict(n_trials=n_trials, z1=z1, z2=z2, part1=part1, part2=part2, expected_max_z=expected_max_z,
                sr0=sr0, diff=diff, z_stat=z_stat, dsr=dsr,
                sr0_daily=sr0, sr0_annualized=sr0 * math.sqrt(252))


def main(inputs_dir: str, out_dir: str) -> dict:
    inputs_dir = Path(inputs_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    publicado = json.loads((Path(__file__).resolve().parent / "results_published.json").read_text())

    discovery_end = publicado["discovery_end"]
    validation_end = publicado["validation_end"]
    seed = 0
    n_boot = 10000

    # ------------------------------------------------------------------ #
    # 1. Reconstruir el pipeline (igual que exp002.run, pasos 1-6)
    # ------------------------------------------------------------------ #
    log("Leyendo precios reales...")
    precios = _leer_precios(inputs_dir, UNIVERSO)
    retornos = precios.pct_change()
    idx = precios.index

    dtb3 = pd.read_parquet(inputs_dir / "DTB3.parquet")["value"].astype(float)
    tasa_cash_anual = (dtb3.reindex(idx).ffill()) / 100.0
    tasa_cash_diaria = tasa_cash_anual / 252.0

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

    _L_LIST, _W_LIST, _B_LIST, _V_LIST, _Z = [3, 6, 12], [50, 100, 200], [55, 252], [20, 60], 10
    combos = sorted({(v["L_meses"], v["W_dias"], v["B_dias"], v["V_dias"]) for v in grid.build_grid()})

    momentum_cache = {Lm: pd.DataFrame({t: signals.ts_momentum_signal(precios[t], Lm) for t in precios.columns})[precios.columns] for Lm in _L_LIST}
    trend_cache = {Wd: pd.DataFrame({t: signals.trend_signal(precios[t], Wd) for t in precios.columns})[precios.columns] for Wd in _W_LIST}
    breakout_cache = {Bd: pd.DataFrame({t: signals.breakout_signal(precios[t], Bd) for t in precios.columns})[precios.columns] for Bd in _B_LIST}
    reversion_cache = pd.DataFrame({t: signals.senal_reversion(precios[t], _Z) for t in precios.columns})[precios.columns]
    vol_cache = {Vd: pd.DataFrame({t: signals.volatilidad_realizada(precios[t], Vd) for t in precios.columns})[precios.columns] for Vd in _V_LIST}
    mu_cache = {Vd: portfolio.retorno_esperado_trailing(retornos, Vd) for Vd in _V_LIST}
    var_cache = {Vd: portfolio.varianza_trailing(retornos, Vd) for Vd in _V_LIST}
    mask_rango = es_rango.reindex(idx).fillna(False).to_numpy(dtype=bool)[:, None]

    log("Construyendo señales por combo...")
    combos_data = {}
    for Lm, Wd, Bd, Vd in combos:
        stacked = np.stack([momentum_cache[Lm].to_numpy(), trend_cache[Wd].to_numpy(), breakout_cache[Bd].to_numpy()], axis=0)
        cuenta = np.sum(~np.isnan(stacked), axis=0)
        suma = np.nansum(stacked, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            direc_vals = np.where(cuenta > 0, suma / np.maximum(cuenta, 1), np.nan)
        senal_vals = np.where(mask_rango, reversion_cache.to_numpy(), direc_vals)
        combos_data[(Lm, Wd, Bd, Vd)] = {
            "senal": pd.DataFrame(senal_vals, index=idx, columns=precios.columns),
            "vol": vol_cache[Vd], "mu": mu_cache[Vd], "var": var_cache[Vd],
        }

    conteo = (~retornos.isna()).sum(axis=1)
    validas = conteo[conteo >= 40]
    fecha_inicio = validas.index[0] if len(validas) > 0 else idx[0]
    retornos_con_cash = retornos.copy()
    retornos_con_cash["CASH"] = tasa_cash_diaria.to_numpy()

    log("Precalculando pesos base y escalados (288 combos x 2 k)...")
    pesos_base_cache, pesos_esc_cache = {}, {}
    for key_combo, data in combos_data.items():
        for construccion, param in grid.construccion_parametros():
            pb = _pesos_segun_construccion(construccion, param, data["senal"], data["vol"], data["mu"], data["var"])
            ck = (key_combo, construccion, param)
            pesos_base_cache[ck] = pb
            for k in (0.5, 0.75):
                pesos_esc_cache[(ck, k)] = escalar_por_regimen(pb, regimen, k)

    d_end = pd.Timestamp(discovery_end)
    v_end = pd.Timestamp(validation_end)

    # ------------------------------------------------------------------ #
    # 2. Localizar la variante ganadora y verificar reproducción
    # ------------------------------------------------------------------ #
    vid_ganador = publicado["variant_id_ganador"]
    v_gan = next(v for v in grid.build_grid() if v["variant_id"] == vid_ganador)
    log(f"Variante ganadora: {vid_ganador}")

    def pesos_finales_de(v):
        key_combo = (v["L_meses"], v["W_dias"], v["B_dias"], v["V_dias"])
        ck = (key_combo, v["construccion"], v["construccion_param"])
        pesos_esc = pesos_esc_cache[(ck, float(v["k"]))]
        cash_pct = _cash_serie(v["cash_politica"], idx, cash_pct_regimen)
        pesos_fin = portfolio.aplicar_leverage_y_cash(pesos_esc, float(v["leverage"]), cash_pct)
        costo_apal = portfolio.costo_apalancamiento_diario(float(v["leverage"]), tasa_cash_anual, float(v["spread"]))
        return pesos_fin, cash_pct, costo_apal

    def backtest_full(pesos_fin, cash_pct, costo_apal):
        pesos_cc = pesos_fin.copy()
        pesos_cc["CASH"] = cash_pct.to_numpy()
        return backtest.ejecutar_backtest(pesos_cc, retornos_con_cash, costo_apal, costo_por_lado=0.001)

    # v_gan trae sus PROPIOS leverage/cash_politica/spread (los de la selección,
    # que son exactamente los del nivel "Conservative": cash_20, 1.0x). Los
    # niveles de apetito (paso 9 de exp002.run) sustituyen cash_politica y
    # leverage por los de cada nivel, reusando siempre v_gan["spread"].
    pesos_fin_gan, cash_gan, costo_gan = pesos_finales_de(v_gan)
    res_gan = backtest_full(pesos_fin_gan, cash_gan, costo_gan)
    ret_gan_full = res_gan["ret"].loc[fecha_inicio:]
    ret_gan_locked = ret_gan_full.loc[ret_gan_full.index > v_end]
    met_gan_locked = backtest.metricas(ret_gan_locked)

    pub_cons = publicado["niveles"]["Conservative"]["metricas"]
    for k in ["cagr", "max_drawdown", "calmar", "sharpe", "sortino", "n_days"]:
        a, b_ = met_gan_locked[k], pub_cons[k]
        if abs(a - b_) > max(1e-6, abs(b_) * 1e-6):
            raise RuntimeError(f"NO REPRODUCE results_published.json en Conservative.{k} (pesos crudos del ganador): {a} vs {b_}")
    log("Verificación OK: pesos crudos del ganador reproducen el nivel Conservative.")

    appendix: dict = {}

    # ------------------------------------------------------------------ #
    # 3. Niveles de apetito completos + benchmark, sobre el periodo COMPLETO
    # ------------------------------------------------------------------ #
    log("Recalculando curvas completas de los 5 niveles...")
    curvas_full = {}
    for nombre, (cp, L) in NIVELES_SPEC.items():
        cash_pct = _cash_serie(cp, idx, cash_pct_regimen)
        key_combo_gan = (v_gan["L_meses"], v_gan["W_dias"], v_gan["B_dias"], v_gan["V_dias"])
        pesos_esc_gan = pesos_esc_cache[((key_combo_gan, v_gan["construccion"], v_gan["construccion_param"]), float(v_gan["k"]))]
        pesos_fin = portfolio.aplicar_leverage_y_cash(pesos_esc_gan, float(L), cash_pct)
        costo_apal = portfolio.costo_apalancamiento_diario(float(L), tasa_cash_anual, float(v_gan["spread"]))
        res = backtest_full(pesos_fin, cash_pct, costo_apal)
        curvas_full[nombre] = res["ret"].loc[fecha_inicio:]

    pesos_bench = pd.DataFrame(0.0, index=idx, columns=retornos.columns)
    for t in _BENCH_RV:
        pesos_bench[t] = 0.6 / len(_BENCH_RV)
    for t in _BENCH_RF:
        pesos_bench[t] = 0.4 / len(_BENCH_RF)
    pesos_bench["CASH"] = 0.0
    idx_bench = idx[idx >= fecha_inicio]
    res_bench = backtest.ejecutar_backtest(
        pesos_bench.loc[idx_bench], retornos_con_cash.loc[idx_bench],
        pd.Series(0.0, index=idx_bench), costo_por_lado=0.001,
    )
    ret_bench_full = res_bench["ret"]
    curvas_full["benchmark"] = ret_bench_full

    for nombre in NIVELES_SPEC:
        r_locked = curvas_full[nombre].loc[curvas_full[nombre].index > v_end]
        met = backtest.metricas(r_locked)
        pub = publicado["niveles"][nombre]["metricas"]
        for k in ["cagr", "max_drawdown", "calmar", "sharpe", "sortino", "n_days"]:
            a, b_ = met[k], pub[k]
            if abs(a - b_) > max(1e-6, abs(b_) * 1e-6):
                raise RuntimeError(f"NO REPRODUCE results_published.json en {nombre}.{k}: {a} vs {b_}")
    log("Verificación OK: los 5 niveles reproducen exactamente results_published.json.")

    def curva_de(ret_series, muestreo="W-FRI"):
        equity = (1.0 + ret_series).cumprod()
        picos = equity.cummax()
        underwater = equity / picos - 1.0
        eq_w = equity.resample(muestreo).last().dropna()
        uw_w = underwater.resample(muestreo).last().dropna()
        return {"dates": [d.strftime("%Y-%m-%d") for d in eq_w.index], "equity": eq_w.tolist(), "underwater": uw_w.tolist()}

    appendix["curves"] = {k: curva_de(v) for k, v in curvas_full.items()}
    log("Curvas listas.")

    # ------------------------------------------------------------------ #
    # 4. Rendimiento por año calendario
    # ------------------------------------------------------------------ #
    anual = {nombre: (1.0 + r).groupby(r.index.year).prod() - 1.0 for nombre, r in curvas_full.items()}
    anios = sorted(set().union(*[set(s.index) for s in anual.values()]))
    appendix["annual"] = [
        {"year": int(y), **{k: (float(anual[k].get(y)) if y in anual[k].index else None) for k in anual}}
        for y in anios
    ]

    # ------------------------------------------------------------------ #
    # 5. Drawdowns (picos -> mínimo -> recuperación)
    # ------------------------------------------------------------------ #
    def drawdowns_de(ret_series, top=5):
        equity = (1.0 + ret_series).cumprod()
        picos = equity.cummax()
        dd = equity / picos - 1.0
        out = []
        i = 0
        vals = dd.values
        idx_ = dd.index
        n = len(vals)
        while i < n:
            if vals[i] < -1e-9:
                j = i
                while j < n and vals[j] < -1e-9:
                    j += 1
                k_min = i + int(np.argmin(vals[i:j]))
                peak_i = i - 1 if i > 0 else 0
                rec_i = j if j < n else None
                out.append({
                    "peak": idx_[peak_i].strftime("%Y-%m-%d"),
                    "trough": idx_[k_min].strftime("%Y-%m-%d"),
                    "recovery": idx_[rec_i].strftime("%Y-%m-%d") if rec_i is not None else None,
                    "depth": float(vals[k_min]),
                    "days_to_trough": int(k_min - peak_i),
                    "days_to_recover": int(rec_i - peak_i) if rec_i is not None else None,
                })
                i = j
            else:
                i += 1
        out.sort(key=lambda x: x["depth"])
        return out[:top]

    appendix["drawdowns"] = {k: drawdowns_de(v) for k, v in curvas_full.items() if k in ("Growth50", "benchmark", "Max", "Conservative")}

    # ------------------------------------------------------------------ #
    # 6. DSR paso a paso (igual que exp002.run: sobre el retorno de
    #    VALIDACIÓN de la variante ganadora -antes de escalar por nivel-,
    #    n_trials = 17280)
    # ------------------------------------------------------------------ #
    log("Derivando DSR paso a paso...")
    ret_val_gan = ret_gan_full.loc[(ret_gan_full.index > d_end) & (ret_gan_full.index <= v_end)]
    x = ret_val_gan.to_numpy(dtype=float)
    n = len(x)
    mean_daily = float(np.mean(x))
    std_daily = float(np.std(x, ddof=1))
    sr = mean_daily / std_daily
    g3 = float(ret_val_gan.skew())
    g4 = float(ret_val_gan.kurt()) + 3.0
    term_one, term_skew, term_kurt = 1.0, -g3 * sr, (g4 - 1.0) / 4.0 * sr ** 2
    numerator = term_one + term_skew + term_kurt
    denominator = n - 1
    variance_sr = numerator / denominator
    sr_std = math.sqrt(variance_sr)

    principal = _pasos_dsr(17280, sr_std, sr)
    dsr_check = evaluation.deflated_sharpe_ratio(ret_val_gan, n_trials=17280)
    if abs(principal["dsr"] - dsr_check) > 1e-9 or abs(principal["dsr"] - publicado["deflated_sharpe"]) > 1e-6:
        raise RuntimeError(f"DSR no reproduce: paso-a-paso={principal['dsr']} codigo={dsr_check} publicado={publicado['deflated_sharpe']}")
    log(f"DSR verificado: {principal['dsr']:.6g}")

    sensibilidad_n = [_pasos_dsr(nt, sr_std, sr) for nt in (1, 100, 1000, 17280)]

    appendix["dsr_steps"] = {
        "n": n, "mean_daily": mean_daily, "std_daily": std_daily, "sr": sr,
        "skew": g3, "kurtosis": g4, "term_one": term_one, "term_skew": term_skew, "term_kurt": term_kurt,
        "numerator": numerator, "denominator": denominator, "variance_sr": variance_sr, "sr_std": sr_std,
        "gamma": GAMMA, **principal, "sensitivity_n_trials": sensibilidad_n,
    }

    # ------------------------------------------------------------------ #
    # 7. Placebo pre-registrado: reproducir + demostrar que no tiene poder
    # ------------------------------------------------------------------ #
    log("Verificando el placebo pre-registrado y su poder estadístico...")
    ret_g50_locked = curvas_full["Growth50"].loc[curvas_full["Growth50"].index > v_end]
    placebo_pub = evaluation.placebo_circular(ret_g50_locked, n_placebos=n_boot, seed=seed)
    valor_real_g50 = evaluation.tasa_crecimiento_geometrica(ret_g50_locked)
    percentil_check = evaluation.percentil_real_vs_placebo(valor_real_g50, placebo_pub)
    diff_percentil = abs(percentil_check - publicado["percentil_vs_placebo"])
    # OJO: esta métrica compara el CAGR real contra 10 000 rotaciones circulares
    # del MISMO conjunto de retornos. El producto que define el CAGR es
    # conmutativo: toda rotación da el valor EXACTO, salvo por el orden en que
    # el punto flotante acumula el redondeo (~1e-16). Por eso una
    # reimplementación matemáticamente idéntica a la de exp002.run (esta) no
    # reproduce el percentil publicado bit a bit: la cifra es ruido de
    # redondeo, no una señal real. Se documenta tal cual.
    if diff_percentil > 1e-6:
        log(f"AVISO (esperado): percentil del placebo pre-registrado no reproduce bit a bit "
            f"({percentil_check:.4f} aquí vs {publicado['percentil_vs_placebo']:.4f} publicado) — "
            f"es la prueba de que la métrica es ruido de redondeo, ver sección de limitaciones.")

    appendix["placebo_preregistrado"] = {
        "percentil": percentil_check, "percentil_publicado": publicado["percentil_vs_placebo"],
        "diff_vs_publicado": diff_percentil, "valor_real": valor_real_g50,
        "placebo_min": float(placebo_pub.min()), "placebo_max": float(placebo_pub.max()),
        "placebo_std": float(placebo_pub.std()), "max_abs_diff_vs_real": float(np.max(np.abs(placebo_pub - valor_real_g50))),
    }

    # ------------------------------------------------------------------ #
    # 8. Placebo alternativo: rota el RÉGIMEN (no el retorno ya realizado)
    # ------------------------------------------------------------------ #
    log("Calculando placebo alternativo (rotación del régimen macro)...")
    rng_pl = np.random.default_rng(seed)
    key_combo_gan = (v_gan["L_meses"], v_gan["W_dias"], v_gan["B_dias"], v_gan["V_dias"])
    pb_gan = pesos_base_cache[(key_combo_gan, v_gan["construccion"], v_gan["construccion_param"])]
    n_total_dias = len(regimen)
    n_placebo_regimen = 2000
    placebo_regimen_cagr = np.empty(n_placebo_regimen, dtype=float)
    cash_pct_g50 = _cash_serie("cash_5", idx, cash_pct_regimen)
    costo_apal_g50 = portfolio.costo_apalancamiento_diario(1.5, tasa_cash_anual, float(v_gan["spread"]))
    for i in range(n_placebo_regimen):
        shift = int(rng_pl.integers(1, n_total_dias))
        regimen_rot = pd.Series(np.roll(regimen.to_numpy(), shift), index=regimen.index)
        pesos_esc_rot = escalar_por_regimen(pb_gan, regimen_rot, float(v_gan["k"]))
        pesos_fin_rot = portfolio.aplicar_leverage_y_cash(pesos_esc_rot, 1.5, cash_pct_g50)
        res_rot = backtest_full(pesos_fin_rot, cash_pct_g50, costo_apal_g50)
        ret_rot = res_rot["ret"].loc[fecha_inicio:]
        ret_rot_locked = ret_rot.loc[ret_rot.index > v_end]
        placebo_regimen_cagr[i] = evaluation.tasa_crecimiento_geometrica(ret_rot_locked)
    percentil_regimen = float(np.mean(placebo_regimen_cagr <= valor_real_g50))
    appendix["placebo_regimen"] = {
        "n_placebo": n_placebo_regimen, "valor_real": valor_real_g50, "percentil": percentil_regimen,
        "placebo_p05": float(np.percentile(placebo_regimen_cagr, 5)),
        "placebo_p25": float(np.percentile(placebo_regimen_cagr, 25)),
        "placebo_p50": float(np.percentile(placebo_regimen_cagr, 50)),
        "placebo_p75": float(np.percentile(placebo_regimen_cagr, 75)),
        "placebo_p95": float(np.percentile(placebo_regimen_cagr, 95)),
    }
    log(f"Placebo-régimen listo: percentil={percentil_regimen:.3f}")

    # ------------------------------------------------------------------ #
    # 9. Recorrido de las 17 280 variantes en validación: sensibilidad por
    #    dimensión, Reality Check de White, número efectivo de intentos
    # ------------------------------------------------------------------ #
    todas = grid.build_grid()
    n_total = len(todas)
    log(f"Recorriendo {n_total} variantes para obtener retornos de validación...")

    val_idx = None
    VAL = None
    sharpe_diario = np.empty(n_total, dtype=float)
    growth_val = np.empty(n_total, dtype=float)
    dims = {k: [] for k in ["L_meses", "W_dias", "B_dias", "V_dias", "construccion", "cash_politica", "leverage", "spread", "k"]}

    t0 = time.time()
    for i, v in enumerate(todas):
        key_combo = (v["L_meses"], v["W_dias"], v["B_dias"], v["V_dias"])
        ck = (key_combo, v["construccion"], v["construccion_param"])
        pesos_esc = pesos_esc_cache[(ck, float(v["k"]))]
        cash_pct = _cash_serie(v["cash_politica"], idx, cash_pct_regimen)
        pesos_fin = portfolio.aplicar_leverage_y_cash(pesos_esc, float(v["leverage"]), cash_pct)
        costo_apal = portfolio.costo_apalancamiento_diario(float(v["leverage"]), tasa_cash_anual, float(v["spread"]))
        pesos_cc = pesos_fin.copy()
        pesos_cc["CASH"] = cash_pct.to_numpy()
        res = backtest.ejecutar_backtest(pesos_cc, retornos_con_cash, costo_apal, costo_por_lado=0.001)
        ret = res["ret"].loc[fecha_inicio:]
        val = ret.loc[(ret.index > d_end) & (ret.index <= v_end)]

        if VAL is None:
            val_idx = val.index
            VAL = np.empty((n_total, len(val_idx)), dtype=float)
        VAL[i] = val.to_numpy()

        xv = val.to_numpy(dtype=float)
        mu, sd = float(np.mean(xv)), float(np.std(xv, ddof=1))
        sharpe_diario[i] = mu / sd if sd > 0 else np.nan
        equity_final = float(np.prod(1.0 + xv))
        dias_cal = (val_idx[-1] - val_idx[0]).days
        growth_val[i] = equity_final ** (365.25 / dias_cal) - 1.0 if dias_cal > 0 and equity_final > 0 else np.nan

        for k in dims:
            dims[k].append(v[k] if k != "construccion" else f"{v['construccion']}:{v['construccion_param']}")

        if i % 4000 == 0:
            log(f"  {i}/{n_total} ({time.time()-t0:.0f}s)")

    log(f"Listo: {n_total} variantes en {time.time()-t0:.0f}s.")

    bench_val = ret_bench_full.loc[(ret_bench_full.index > d_end) & (ret_bench_full.index <= v_end)].reindex(val_idx)
    bench_x = bench_val.to_numpy(dtype=float)
    bench_eq_final = float(np.prod(1.0 + bench_x))
    dias_cal_bench = (val_idx[-1] - val_idx[0]).days
    bench_growth = bench_eq_final ** (365.25 / dias_cal_bench) - 1.0

    log("Calculando sensibilidad por dimensión...")
    df_dims = pd.DataFrame(dims)
    df_dims["growth_val"] = growth_val
    df_dims["supera_benchmark"] = growth_val > bench_growth

    def resumen_grupo(sub):
        return {
            "n": int(len(sub)), "growth_median": float(sub["growth_val"].median()),
            "growth_q25": float(sub["growth_val"].quantile(0.25)), "growth_q75": float(sub["growth_val"].quantile(0.75)),
            "share_supera_benchmark": float(sub["supera_benchmark"].mean()),
        }

    sensibilidad = {"all": resumen_grupo(df_dims)}
    for col in ["L_meses", "W_dias", "B_dias", "V_dias", "construccion", "cash_politica", "leverage", "spread", "k"]:
        sensibilidad[col] = {str(val): resumen_grupo(df_dims[df_dims[col] == val]) for val in sorted(df_dims[col].unique(), key=str)}

    idx_best = int(np.nanargmax(growth_val))
    idx_worst = int(np.nanargmin(growth_val))
    sensibilidad["best_variant"] = {"id": todas[idx_best]["variant_id"], "growth_val": float(growth_val[idx_best])}
    sensibilidad["worst_variant"] = {"id": todas[idx_worst]["variant_id"], "growth_val": float(growth_val[idx_worst])}
    sensibilidad["benchmark_growth_val"] = float(bench_growth)
    appendix["sensitivity"] = sensibilidad

    log("Reality Check de White (bootstrap del máximo)...")
    n_boot_rc = 2000
    pos_rc = evaluation.posiciones_bootstrap_bloques(len(val_idx), 20, n_boot_rc, seed=0)
    diff_real = VAL.mean(axis=1) - bench_x.mean()
    obs_max = float(diff_real.max())
    boot_max = np.empty(n_boot_rc, dtype=float)
    t0 = time.time()
    for r in range(n_boot_rc):
        p = pos_rc[r]
        boot_max[r] = (VAL[:, p].mean(axis=1) - bench_x[p].mean()).max()
        if r % 1000 == 0:
            log(f"  RC {r}/{n_boot_rc} ({time.time()-t0:.0f}s)")
    p_value_rc = float((1 + np.sum(boot_max >= obs_max)) / (1 + n_boot_rc))
    appendix["reality_check"] = {
        "n_variantes": n_total, "n_boot": n_boot_rc, "observado_max_diff": obs_max,
        "p_value": p_value_rc, "mejor_variante": todas[int(np.argmax(diff_real))]["variant_id"],
    }
    log(f"Reality Check listo: p={p_value_rc:.4f}")

    log("Número efectivo de intentos (muestra)...")
    rng = np.random.default_rng(0)
    n_muestra = 400
    muestra_idx = rng.choice(n_total, size=n_muestra, replace=False)
    corr = np.corrcoef(VAL[muestra_idx])
    eigvals = np.clip(np.linalg.eigvalsh(corr), 0, None)
    top_share = float(eigvals.max() / eigvals.sum())
    n_eff = float((eigvals.sum() ** 2) / np.sum(eigvals ** 2))
    mean_pairwise_corr = float((corr.sum() - n_muestra) / (n_muestra * (n_muestra - 1)))

    sr_trials = sharpe_diario[muestra_idx]
    sr_trials = sr_trials[~np.isnan(sr_trials)]
    sr_trials_std = float(np.std(sr_trials, ddof=1))
    sr_gan = sharpe_diario[next(i for i, v in enumerate(todas) if v["variant_id"] == v_gan["variant_id"])]
    sr0_cross, dsr_cross = _pasos_dsr(n_total, sr_trials_std, sr_gan)["sr0"], None
    _p = _pasos_dsr(n_total, sr_trials_std, sr_gan)
    sr0_cross, dsr_cross = _p["sr0"], _p["dsr"]

    appendix["trials"] = {
        "n_muestra": n_muestra, "mean_pairwise_corr": mean_pairwise_corr, "top_eigenvalue_share": top_share,
        "n_eff_participation": n_eff, "sr_trials_std_daily": sr_trials_std,
        "sr_trials_min_daily": float(sr_trials.min()), "sr_trials_max_daily": float(sr_trials.max()),
        "sr0_cross_trial_n_total": sr0_cross, "dsr_cross_trial_sigma_n_total": dsr_cross,
    }

    # ------------------------------------------------------------------ #
    # 10. Sensibilidad a costos de transacción (ganador, Growth50, locked test)
    # ------------------------------------------------------------------ #
    log("Sensibilidad a costos de transacción...")
    key_combo_gan = (v_gan["L_meses"], v_gan["W_dias"], v_gan["B_dias"], v_gan["V_dias"])
    pesos_esc_gan = pesos_esc_cache[((key_combo_gan, v_gan["construccion"], v_gan["construccion_param"]), float(v_gan["k"]))]
    cash_pct_g50 = _cash_serie("cash_5", idx, cash_pct_regimen)
    pesos_fin_g50 = portfolio.aplicar_leverage_y_cash(pesos_esc_gan, 1.5, cash_pct_g50)
    costo_apal_g50 = portfolio.costo_apalancamiento_diario(1.5, tasa_cash_anual, float(v_gan["spread"]))
    pesos_cc_g50 = pesos_fin_g50.copy()
    pesos_cc_g50["CASH"] = cash_pct_g50.to_numpy()

    cost_sens = {}
    for bps in (0, 10, 20, 30, 40, 50):
        res_c = backtest.ejecutar_backtest(pesos_cc_g50, retornos_con_cash, costo_apal_g50, costo_por_lado=bps / 10000.0)
        ret_c_locked = res_c["ret"].loc[fecha_inicio:].pipe(lambda s: s.loc[s.index > v_end])
        cost_sens[str(bps)] = backtest.metricas(ret_c_locked)
    appendix["cost_sensitivity"] = cost_sens

    # ------------------------------------------------------------------ #
    # 11. Entradas y salidas de régimen (contracción = regimen in {3,4})
    # ------------------------------------------------------------------ #
    log("Analizando entradas/salidas de régimen de contracción...")
    contraccion = regimen.isin([3.0, 4.0]).reindex(idx).fillna(False)
    cambios = contraccion.astype(int).diff().fillna(0)
    entradas = contraccion.index[cambios == 1]
    salidas = contraccion.index[cambios == -1]

    def fwd_spy(fechas, horizontes=(20, 60, 120)):
        out = {}
        precios_spy = precios["SPY"]
        for h in horizontes:
            vals = []
            for f in fechas:
                try:
                    pos = precios_spy.index.get_loc(f)
                except KeyError:
                    continue
                if pos + h < len(precios_spy):
                    vals.append(precios_spy.iloc[pos + h] / precios_spy.iloc[pos] - 1.0)
            vals = np.array(vals, dtype=float)
            out[f"fwd_{h}d"] = {
                "n": int(len(vals)), "mean": float(np.mean(vals)) if len(vals) else None,
                "median": float(np.median(vals)) if len(vals) else None,
                "share_negative": float(np.mean(vals < 0)) if len(vals) else None,
            }
        return out

    appendix["regime_events"] = {
        "n_entradas_contraccion": int(len(entradas)), "n_salidas_contraccion": int(len(salidas)),
        "dias_en_contraccion": int(contraccion.sum()), "fraccion_en_contraccion": float(contraccion.mean()),
        "spy_despues_de_entrar_a_contraccion": fwd_spy(entradas),
        "spy_despues_de_salir_de_contraccion": fwd_spy(salidas),
        "spy_linea_base": fwd_spy(precios["SPY"].index[::5]),
    }

    # ------------------------------------------------------------------ #
    # 12. Catálogo de datos (desde manifest.json + catalog.yaml)
    # ------------------------------------------------------------------ #
    log("Armando catálogo de datos...")
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
    catalog = yaml.safe_load((ROOT / "data" / "catalog.yaml").read_text())
    cat_entries = {it["id"]: it for it in catalog["series"]}

    serie_catalogo = []
    for sid in list(UNIVERSO) + ["DTB3", "M2", "FED_BALANCE", "LEADING"]:
        m = manifest["series"].get(sid, {})
        c = cat_entries.get(sid, {})
        serie_catalogo.append({
            "id": sid, "source": m.get("source", c.get("source")), "symbol": c.get("symbol", ""),
            "role": m.get("role", c.get("role", "")), "desde": m.get("primera_fecha"), "hasta": m.get("ultima_fecha"),
            "filas": m.get("filas"), "sha256": m.get("sha256", ""), "notas": c.get("notes", c.get("notas", "")),
        })
    appendix["series"] = serie_catalogo

    (out_dir / "appendix.json").write_text(json.dumps(_ser(appendix), indent=2, ensure_ascii=False))
    log("appendix.json final escrito.")
    return appendix


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from prl.data import macro_vintage
from prl.growth_max import (
    backtest,
    evaluation,
    grid as grid_mod,
    portfolio,
    signals,
)

UNIVERSO = [
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

_NIVELES = [
    ("Conservative", "cash_20", 1.0),
    ("Growth25", "cash_10", 1.0),
    ("Growth50", "cash_5", 1.5),
    ("Growth75", "cash_0", 1.5),
    ("Max", "cash_0", 2.0),
]

_CASH_FIJO = {"cash_0": 0.0, "cash_5": 0.05, "cash_10": 0.10, "cash_20": 0.20}
_Z_DIAS = 10
_COSTO_LADO = 0.001
_UMBRALES_RUINA = (0.5, 0.75, 0.9, 0.99)


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------


def _clean(o):
    """Convierte recursivamente a tipos JSON-serializables (NaN/inf -> None)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    if isinstance(o, np.ndarray):
        return [_clean(x) for x in o.tolist()]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(o, pd.Timestamp):
        return None if pd.isna(o) else o.isoformat()
    return o


def _bootstrap_indices(n: int, block: int, n_rep: int, seed: int) -> np.ndarray:
    """Índices (pareados) de block bootstrap: forma (n_rep, n)."""
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_rep, n_blocks))
    offsets = np.arange(block)
    pos = (starts[:, :, None] + offsets[None, None, :]).reshape(n_rep, -1)
    return pos[:, :n].astype(np.int64)


def _prob_loss(r: np.ndarray, indices: np.ndarray, umbrales) -> dict:
    """Fracción de réplicas con |max drawdown| >= umbral (vectorizado)."""
    r = np.asarray(r, dtype=float)
    rb = r[indices]
    eq = np.cumprod(1.0 + rb, axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    dd = eq / peak - 1.0
    with np.errstate(invalid="ignore"):
        mdd = np.abs(np.nanmin(dd, axis=1))
    return {t: float(np.mean(mdd >= t)) for t in umbrales}


def _cargar_precios(inputs_dir: Path) -> pd.DataFrame:
    """Lee los .parquet del universo y arma la matriz de precios (unión de fechas)."""
    columnas = {}
    for ticker in UNIVERSO:
        serie = pd.read_parquet(inputs_dir / f"{ticker}.parquet")["adj_close"]
        serie = serie.sort_index()
        serie.name = ticker
        columnas[ticker] = serie
    precios = pd.DataFrame(columnas)
    return precios.sort_index()


def _cargar_macro(inputs_dir: Path, fechas: pd.DatetimeIndex, nombre: str) -> pd.Series:
    """Serie macro point-in-time conocida en cada fecha de corte."""
    vint = pd.read_parquet(inputs_dir / f"{nombre}.parquet")
    conocida = macro_vintage.serie_conocida_en(vint, fechas)
    serie = conocida["value"]
    if not serie.index.equals(pd.DatetimeIndex(fechas)):
        serie = serie.reindex(fechas)
    return serie


def _liquidez_combinada(a: pd.Series, b: pd.Series) -> pd.Series:
    """Signo combinado (media redondeada) de dos señales de liquidez."""
    x = a.to_numpy(dtype=float)
    y = b.to_numpy(dtype=float)
    suma = np.nansum(np.vstack([x, y]), axis=0)
    cnt = (~np.isnan(x)).astype(int) + (~np.isnan(y)).astype(int)
    out = np.where(
        cnt == 0,
        np.nan,
        np.where(suma > 0, 1.0, np.where(suma < 0, -1.0, 0.0)),
    )
    return pd.Series(out, index=a.index, dtype=float)


def _composite3(mom: pd.DataFrame, trend: pd.DataFrame, brk: pd.DataFrame) -> pd.DataFrame:
    """Promedio igualitario por fila de las tres señales direccionales (ignora NaN)."""
    arr = np.stack([mom.to_numpy(), trend.to_numpy(), brk.to_numpy()], axis=2)
    cnt = np.sum(~np.isnan(arr), axis=2)
    sm = np.nansum(arr, axis=2)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(cnt > 0, sm / np.maximum(cnt, 1), np.nan)
    return pd.DataFrame(media, index=mom.index, columns=mom.columns)


def _prob_perdida_segura(ret: pd.Series, umbral: float, n_boot: int, seed: int) -> float:
    """probabilidad_perdida con tamaño de bloque acotado a la longitud disponible."""
    if len(ret) < 3:
        return float("nan")
    bloque = min(20, len(ret) - 1)
    try:
        return evaluation.probabilidad_perdida(
            ret, umbral, tamano_bloque=bloque, n_replicas=n_boot, seed=seed
        )
    except Exception:  # pragma: no cover - defensivo
        return float("nan")


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------


def run(
    inputs_dir,
    run_dir,
    discovery_end="2015-12-31",
    validation_end="2019-12-31",
    n_boot=500,
    seed=0,
) -> dict:
    """Orquesta EXP-002 y escribe run_dir/results.json (determinista)."""
    inputs_dir = Path(inputs_dir)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    d_end = pd.Timestamp(discovery_end)
    v_end = pd.Timestamp(validation_end)

    notes = [
        "vol_target aproxima la volatilidad del portafolio sin correlaciones",
        "universo limitado a ETFs de índice/activos cotizados",
        "régimen macro limitado a 3 series point-in-time (M2, FED_BALANCE, LEADING)",
    ]

    # 1. Precios y retornos -------------------------------------------------
    precios = _cargar_precios(inputs_dir)
    idx = precios.index
    try:
        retornos = precios.pct_change(fill_method=None)
    except TypeError:  # pragma: no cover - compatibilidad pandas antiguo
        retornos = precios.pct_change()

    # 2. Tasa de cash -------------------------------------------------------
    dtb = pd.read_parquet(inputs_dir / "DTB3.parquet")["value"].sort_index()
    dtb = dtb.reindex(idx).ffill()
    tasa_anual = dtb / 100.0
    tasa_cash_diaria = tasa_anual / 252.0

    # 3. Régimen macro point-in-time ---------------------------------------
    m2 = _cargar_macro(inputs_dir, idx, "M2")
    fb = _cargar_macro(inputs_dir, idx, "FED_BALANCE")
    leading = _cargar_macro(inputs_dir, idx, "LEADING")

    liq = _liquidez_combinada(
        signals.signo_cambio_trailing(m2, 126),
        signals.signo_cambio_trailing(fb, 126),
    )
    crec = signals.signo_cambio_trailing(leading, 126)
    regimen = signals.regimen_macro(liq, crec)
    es_rango = signals.es_regimen_de_rango(regimen)
    cash_pct_regimen = portfolio.cash_pct_dinamico(regimen)

    # 5. Fecha de inicio del backtest --------------------------------------
    count = retornos.notna().sum(axis=1)
    elegibles = count[count >= 40]
    fecha_inicio = elegibles.index[0] if len(elegibles) else idx[0]
    bt_mask = np.asarray(idx >= fecha_inicio, dtype=bool)
    bt_index = idx[bt_mask]
    n = len(bt_index)

    retornos_bt = retornos.loc[bt_index]
    tasa_cash_diaria_bt = tasa_cash_diaria.loc[bt_index]
    tasa_anual_bt = tasa_anual.loc[bt_index]
    es_rango_bt = es_rango.loc[bt_index].astype(bool)
    regimen_bt = regimen.loc[bt_index]
    cash_dyn = cash_pct_regimen.loc[bt_index].to_numpy(dtype=float)

    R = np.nan_to_num(retornos_bt.to_numpy(dtype=float), nan=0.0)
    rate_d = np.nan_to_num(tasa_cash_diaria_bt.to_numpy(dtype=float), nan=0.0)
    rate_a = tasa_anual_bt.to_numpy(dtype=float)

    # máscaras temporales (numpy bool)
    val_mask = np.asarray(bt_index > d_end, dtype=bool) & np.asarray(
        bt_index <= v_end, dtype=bool
    )
    locked_mask = np.asarray(bt_index > v_end, dtype=bool)
    dv_mask = np.asarray(bt_index <= v_end, dtype=bool)
    val_index = bt_index[val_mask]
    locked_index = bt_index[locked_mask]

    n_dv = int(dv_mask.sum())
    if n_dv > 2:
        bloque_dv = 20 if n_dv > 20 else max(2, n_dv - 1)
        dv_indices = _bootstrap_indices(n_dv, bloque_dv, n_boot, seed)
    else:
        dv_indices = None

    # cachés globales de señales -------------------------------------------
    mom_df = {
        L: pd.DataFrame({a: signals.ts_momentum_signal(precios[a], L) for a in UNIVERSO})
        for L in (3, 6, 12)
    }
    trend_df = {
        W: pd.DataFrame({a: signals.trend_signal(precios[a], W) for a in UNIVERSO})
        for W in (50, 100, 200)
    }
    brk_df = {
        B: pd.DataFrame({a: signals.breakout_signal(precios[a], B) for a in UNIVERSO})
        for B in (55, 252)
    }
    rev_df = pd.DataFrame(
        {a: signals.senal_reversion(precios[a], _Z_DIAS) for a in UNIVERSO}
    )
    vol_df = {
        V: pd.DataFrame(
            {a: signals.volatilidad_realizada(precios[a], V) for a in UNIVERSO}
        )
        for V in (20, 60)
    }
    mu_df = {V: portfolio.retorno_esperado_trailing(retornos, V) for V in (20, 60)}
    var_df = {V: portfolio.varianza_trailing(retornos, V) for V in (20, 60)}

    # ------------------------------------------------------------------
    # Motores vectorizados de backtest (equivalentes a ejecutar_backtest)
    # ------------------------------------------------------------------

    def _apal(L: float, spread: float) -> np.ndarray:
        """Costo de apalancamiento diario (0 si L == 1)."""
        if L == 1.0:
            return np.zeros(n)
        return (L - 1.0) * (rate_a / 252.0 + spread / 252.0)

    def _prep(W: np.ndarray):
        """Precalcula pesos rezagados, retorno bruto base y turnover base."""
        Ws = np.zeros_like(W)
        if n > 1:
            Ws[1:] = W[:-1]
        A = (Ws * R).sum(axis=1)
        dv = np.zeros(n)
        if n > 0:
            dv[0] = np.abs(W[0]).sum()
            if n > 1:
                dv[1:] = np.abs(np.diff(W, axis=0)).sum(axis=1)
        return Ws, A, dv

    def _ret_const(A: np.ndarray, dv: np.ndarray, cash: float, L: float,
                   spread: float) -> np.ndarray:
        f = L * (1.0 - cash)
        cp = np.full(n, float(cash))
        cp[0] = 0.0
        bruto = f * A + cp * rate_d
        turnover = np.zeros(n)
        if n > 1:
            turnover[1:] = f * dv[:-1]
        return bruto - turnover * _COSTO_LADO - _apal(L, spread)

    def _ret_dyn(Ws: np.ndarray, L: float, spread: float) -> np.ndarray:
        factor = L * (1.0 - cash_dyn)
        fpre = np.zeros(n)
        cp = np.zeros(n)
        if n > 1:
            fpre[1:] = factor[:-1]
            cp[1:] = cash_dyn[:-1]
        wa = Ws * fpre[:, None]
        bruto = (wa * R).sum(axis=1) + cp * rate_d
        turnover = np.zeros(n)
        if n > 1:
            turnover[1:] = np.abs(np.diff(wa, axis=0)).sum(axis=1) + np.abs(np.diff(cp))
        return bruto - turnover * _COSTO_LADO - _apal(L, spread)

    # ------------------------------------------------------------------
    # Construcción de señales y pesos base por combinación
    # ------------------------------------------------------------------

    def _build_combo(combo):
        L, W, B, V = combo
        mom = mom_df[L].loc[bt_index]
        trend = trend_df[W].loc[bt_index]
        brk = brk_df[B].loc[bt_index]
        direccional = _composite3(mom, trend, brk)
        rev = rev_df.loc[bt_index]
        mask = es_rango_bt.to_numpy(dtype=bool)[:, None]
        overlay = np.where(mask, rev.to_numpy(), direccional.to_numpy())
        senal = pd.DataFrame(overlay, index=bt_index, columns=UNIVERSO)
        return (
            senal,
            vol_df[V].loc[bt_index],
            mu_df[V].loc[bt_index],
            var_df[V].loc[bt_index],
        )

    contraccion = regimen_bt.isin([3.0, 4.0]).to_numpy(dtype=bool)

    def _bases_for(senal, vol, mu, var):
        """Pesos base (gross <= 1) por método de construcción."""
        bases = {}
        bases[("equal", None)] = portfolio.pesos_equal(senal)
        bases[("inv_vol", None)] = portfolio.pesos_inv_vol(senal, vol)
        for obj in (0.10, 0.15, 0.20):
            bases[("vol_target", obj)] = portfolio.pesos_vol_target(senal, vol, obj)
        for frac in (0.25, 0.50, 1.00):
            kw = portfolio.pesos_kelly_frac(senal, mu, var, frac)
            for k in (0.5, 0.75):
                if contraccion.any():
                    mult = np.where(contraccion, k, 1.0)
                    bases[("kelly_frac", frac, k)] = kw.mul(
                        pd.Series(mult, index=bt_index), axis=0
                    )
                else:
                    bases[("kelly_frac", frac, k)] = kw
        return bases

    def _base_key(g):
        c = g["construccion"]
        if c == "kelly_frac":
            return (c, float(g["construccion_param"]), float(g["k"]))
        return (c, g["construccion_param"])

    # ------------------------------------------------------------------
    # 6/7. Recorrido de la grilla agrupado por combinación de señal
    # ------------------------------------------------------------------
    grid = grid_mod.build_grid()
    grouped: dict = {}
    combo_seq: list = []
    for g in grid:
        key = (g["L_meses"], g["W_dias"], g["B_dias"], g["V_dias"])
        if key not in grouped:
            grouped[key] = []
            combo_seq.append(key)
        grouped[key].append(g)

    log_wealth: dict = {}
    prob50: dict = {}
    prob75: dict = {}

    for combo in combo_seq:
        senal_c, vol_c, mu_c, var_c = _build_combo(combo)
        bases = _bases_for(senal_c, vol_c, mu_c, var_c)

        parts: dict = {}
        stats: dict = {}

        for g in grouped[combo]:
            bk = _base_key(g)
            if bk not in parts:
                W = np.nan_to_num(bases[bk].to_numpy(dtype=float), nan=0.0)
                parts[bk] = _prep(W)
            Ws, A, dv = parts[bk]

            cash_name = g["cash_politica"]
            L = float(g["leverage"])
            spread = float(g["spread"])
            key = (bk, cash_name, L, spread)
            if key not in stats:
                if cash_name == "cash_dinamico":
                    ret = _ret_dyn(Ws, L, spread)
                else:
                    ret = _ret_const(A, dv, _CASH_FIJO[cash_name], L, spread)

                r_val = ret[val_mask]
                if len(r_val) > 1:
                    logv = evaluation.tasa_crecimiento_geometrica(
                        pd.Series(r_val, index=val_index)
                    )
                else:
                    logv = float("nan")

                if dv_indices is not None:
                    p = _prob_loss(ret[dv_mask], dv_indices, (0.5, 0.75))
                    pl50, pl75 = p[0.5], p[0.75]
                else:
                    pl50 = pl75 = float("nan")
                stats[key] = (logv, pl50, pl75)

            logv, pl50, pl75 = stats[key]
            vid = g["variant_id"]
            log_wealth[vid] = logv
            prob50[vid] = pl50
            prob75[vid] = pl75

    ganador, motivo = evaluation.elegir_variante(log_wealth, prob50, prob75)

    # ------------------------------------------------------------------
    # 8. Sin ganador -> resultados mínimos (locked test intacto)
    # ------------------------------------------------------------------
    if ganador is None:
        results = {
            "experiment": "EXP-002",
            "variant_id_ganador": None,
            "motivo_seleccion": motivo,
            "n_variants": len(grid),
            "fecha_inicio_backtest": bt_index[0].strftime("%Y-%m-%d") if n else None,
            "discovery_end": discovery_end,
            "validation_end": validation_end,
            "n_dias_locked_test": None,
            "niveles": {},
            "comparacion_bootstrap_growth50": None,
            "label": "INCONCLUSIVE",
            "deflated_sharpe": None,
            "percentil_vs_placebo": None,
            "notes": notes,
        }
        payload = _clean(results)
        (run_dir / "results.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return payload

    win = next((g for g in grid if g["variant_id"] == ganador), None)
    if win is None or len(locked_index) < 3:
        results = {
            "experiment": "EXP-002",
            "variant_id_ganador": ganador,
            "motivo_seleccion": motivo,
            "n_variants": len(grid),
            "fecha_inicio_backtest": bt_index[0].strftime("%Y-%m-%d") if n else None,
            "discovery_end": discovery_end,
            "validation_end": validation_end,
            "n_dias_locked_test": int(len(locked_index)),
            "niveles": {},
            "comparacion_bootstrap_growth50": None,
            "label": "INCONCLUSIVE",
            "deflated_sharpe": None,
            "percentil_vs_placebo": None,
            "notes": notes,
        }
        payload = _clean(results)
        (run_dir / "results.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return payload

    # ------------------------------------------------------------------
    # 9-12. Evaluación del ganador y niveles de apetito en locked_test
    # ------------------------------------------------------------------
    combo_win = (win["L_meses"], win["W_dias"], win["B_dias"], win["V_dias"])
    senal_w, vol_w, mu_w, var_w = _build_combo(combo_win)
    bases_w = _bases_for(senal_w, vol_w, mu_w, var_w)
    base_win = bases_w[_base_key(win)]

    retornos_locked = retornos_bt.loc[locked_index]
    tasa_cash_locked = tasa_cash_diaria.loc[locked_index]
    tasa_anual_locked = tasa_anual.loc[locked_index]
    retornos_locked_cash = retornos_locked.copy()
    retornos_locked_cash["CASH"] = tasa_cash_locked.to_numpy(dtype=float)

    base_locked = base_win.loc[locked_index]
    spread_win = float(win["spread"])

    niveles: dict = {}
    ret_locked_growth50: pd.Series | None = None
    prob_ruina_75_growth50 = float("nan")

    for nombre_nivel, politica, L_nivel in _NIVELES:
        cash_locked = pd.Series(
            _CASH_FIJO[politica], index=locked_index, dtype=float
        )
        pesos_lvl = portfolio.aplicar_leverage_y_cash(base_locked, L_nivel, cash_locked)
        pesos_lvl = pesos_lvl.copy()
        pesos_lvl["CASH"] = cash_locked.to_numpy(dtype=float)
        if L_nivel == 1.0:
            costo_apal = pd.Series(0.0, index=locked_index)
        else:
            costo_apal = (L_nivel - 1.0) * (
                tasa_anual_locked / 252.0 + spread_win / 252.0
            )
        res = backtest.ejecutar_backtest(
            pesos_lvl,
            retornos_locked_cash,
            costo_apal,
            costo_por_lado=_COSTO_LADO,
        )
        ret_lvl = res["ret"]
        metricas = backtest.metricas(ret_lvl)
        ruina = {
            str(th): _prob_perdida_segura(ret_lvl, th, n_boot, seed)
            for th in _UMBRALES_RUINA
        }
        niveles[nombre_nivel] = {"metricas": metricas, "probabilidad_ruina": ruina}
        if nombre_nivel == "Growth50":
            ret_locked_growth50 = ret_lvl
            prob_ruina_75_growth50 = ruina["0.75"]

    if ret_locked_growth50 is None:  # pragma: no cover - defensivo
        ret_locked_growth50 = pd.Series(0.0, index=locked_index)

    # 10. Benchmark --------------------------------------------------------
    pesos_bench = pd.DataFrame(
        0.0, index=locked_index, columns=retornos_locked.columns, dtype=float
    )
    for a in ("SPY", "EFA", "EEM"):
        if a in pesos_bench.columns:
            pesos_bench[a] = 0.6 / 3.0
    for a in ("TLT", "IEF", "LQD"):
        if a in pesos_bench.columns:
            pesos_bench[a] = 0.4 / 3.0
    costo_bench = pd.Series(0.0, index=locked_index)
    res_bench = backtest.ejecutar_backtest(
        pesos_bench, retornos_locked, costo_bench, costo_por_lado=_COSTO_LADO
    )
    ret_bench = res_bench["ret"]

    # 11. Comparación y etiqueta ------------------------------------------
    try:
        comparacion = evaluation.comparacion_bootstrap(
            ret_locked_growth50,
            ret_bench,
            tamano_bloque=min(20, max(2, len(ret_locked_growth50) - 1)),
            n_replicas=n_boot,
            seed=seed,
        )
    except Exception:  # pragma: no cover - defensivo
        comparacion = {
            "ci_cagr_modelo": (float("nan"), float("nan")),
            "frac_supera_benchmark": float("nan"),
        }

    label = evaluation.etiqueta(
        comparacion["ci_cagr_modelo"],
        comparacion["frac_supera_benchmark"],
        prob_ruina_75_growth50,
        n_dias_locked_test=len(ret_locked_growth50),
    )

    # 12. Placebo y DSR ----------------------------------------------------
    cagr_real = evaluation.tasa_crecimiento_geometrica(ret_locked_growth50)
    if len(ret_locked_growth50) >= 2:
        placebo = evaluation.placebo_circular(
            ret_locked_growth50, n_placebos=n_boot, seed=seed
        )
        percentil = evaluation.percentil_real_vs_placebo(cagr_real, placebo)
    else:  # pragma: no cover - defensivo
        percentil = float("nan")

    W_win = np.nan_to_num(base_win.to_numpy(dtype=float), nan=0.0)
    Ws_w, A_w, dv_w = _prep(W_win)
    cash_win = win["cash_politica"]
    if cash_win == "cash_dinamico":
        ret_win_full = _ret_dyn(Ws_w, float(win["leverage"]), spread_win)
    else:
        ret_win_full = _ret_const(
            A_w, dv_w, _CASH_FIJO[cash_win], float(win["leverage"]), spread_win
        )
    ret_win_val = pd.Series(ret_win_full[val_mask], index=val_index)
    try:
        dsr = evaluation.deflated_sharpe_ratio(ret_win_val, n_trials=len(grid))
    except Exception:  # pragma: no cover - defensivo
        dsr = float("nan")

    results = {
        "experiment": "EXP-002",
        "variant_id_ganador": ganador,
        "motivo_seleccion": motivo,
        "n_variants": len(grid),
        "fecha_inicio_backtest": bt_index[0].strftime("%Y-%m-%d"),
        "discovery_end": discovery_end,
        "validation_end": validation_end,
        "n_dias_locked_test": int(len(ret_locked_growth50)),
        "niveles": niveles,
        "comparacion_bootstrap_growth50": {
            "ci_cagr_modelo": list(comparacion["ci_cagr_modelo"]),
            "frac_supera_benchmark": comparacion["frac_supera_benchmark"],
        },
        "label": label,
        "deflated_sharpe": dsr,
        "percentil_vs_placebo": percentil,
        "notes": notes,
    }
    payload = _clean(results)
    (run_dir / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return payload

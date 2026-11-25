import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from prl.short_pressure import evaluation


# --------------------------------------------------------------------------- #
# bootstrap_bloques
# --------------------------------------------------------------------------- #


def test_bootstrap_bloques_forma_y_reproducibilidad():
    df = pd.DataFrame({"a": range(6), "b": [100 + i for i in range(6)]})
    out1 = evaluation.bootstrap_bloques(df, tamano_bloque=2, n_replicas=5, seed=0)
    out2 = evaluation.bootstrap_bloques(df, tamano_bloque=2, n_replicas=5, seed=0)
    assert out1.shape == (5, 6, 2)
    np.testing.assert_array_equal(out1, out2)
    assert np.all(out1[:, :, 1] - 100 == out1[:, :, 0])


def test_bootstrap_bloques_n_menor_que_bloque():
    df = pd.DataFrame({"a": [1.0]})
    with pytest.raises(ValueError):
        evaluation.bootstrap_bloques(df, tamano_bloque=2, n_replicas=5, seed=0)


# --------------------------------------------------------------------------- #
# comparacion_bootstrap
# --------------------------------------------------------------------------- #


def test_comparacion_bootstrap_identico_y_mejor():
    idx = pd.date_range("2020-01-01", periods=6, freq="10D")
    base = pd.Series([0.01, 0.02, -0.01, 0.03, 0.0, 0.01], index=idx)

    identico = evaluation.comparacion_bootstrap(base, base, tamano_bloque=2, n_replicas=50, seed=0)
    assert identico["frac_supera_baseline"] == 0.0

    mejor = base + 0.05
    comp = evaluation.comparacion_bootstrap(mejor, base, tamano_bloque=2, n_replicas=50, seed=0)
    assert comp["frac_supera_baseline"] == 1.0


def test_comparacion_bootstrap_indices_distintos():
    a = pd.Series([0.01, 0.02], index=pd.date_range("2020-01-01", periods=2))
    b = pd.Series([0.01, 0.02], index=pd.date_range("2021-01-01", periods=2))
    with pytest.raises(ValueError):
        evaluation.comparacion_bootstrap(a, b, tamano_bloque=1, n_replicas=10, seed=0)


# --------------------------------------------------------------------------- #
# deflated_sharpe_ratio
# --------------------------------------------------------------------------- #


def test_deflated_sharpe_ratio_n_trials_1_y_monotonia():
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.normal(0.001, 0.01, 60))

    n = len(returns)
    mu = returns.mean()
    sd = returns.std(ddof=1)
    sr = mu / sd
    g3 = returns.skew()
    g4 = returns.kurt() + 3.0
    sr_std = math.sqrt((1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr**2) / (n - 1))
    esperado = float(norm.cdf(sr / sr_std))

    dsr_1 = evaluation.deflated_sharpe_ratio(returns, n_trials=1)
    assert dsr_1 == pytest.approx(esperado, abs=1e-9)

    dsr_grande = evaluation.deflated_sharpe_ratio(returns, n_trials=140)
    assert dsr_grande <= dsr_1


# --------------------------------------------------------------------------- #
# probabilidad_backtest_overfitting
# --------------------------------------------------------------------------- #


def test_pbo_n_particiones_impar():
    df = pd.DataFrame({"v0": range(8)})
    with pytest.raises(ValueError):
        evaluation.probabilidad_backtest_overfitting(df, n_particiones=3)


def _matriz_diagonal(valor_alto=10.0, valor_bajo=1.0):
    cols = {f"v{i}": [valor_bajo] * 4 for i in range(4)}
    for i in range(4):
        cols[f"v{i}"][i] = valor_alto
    return pd.DataFrame(cols)


def test_pbo_habilidad_genuina_da_cero():
    df = pd.DataFrame({"w": [10.0, 9.0, 11.0, 8.0], "x": [1.0, 3.0, 2.0, 4.0], "y": [2.0, 1.0, 3.0, 2.0]})
    assert evaluation.probabilidad_backtest_overfitting(df, n_particiones=4) == 0.0


def test_pbo_adversarial_da_uno():
    df = _matriz_diagonal()
    assert evaluation.probabilidad_backtest_overfitting(df, n_particiones=4) == 1.0


def test_pbo_determinista():
    df = _matriz_diagonal()
    a = evaluation.probabilidad_backtest_overfitting(df, n_particiones=4)
    b = evaluation.probabilidad_backtest_overfitting(df, n_particiones=4)
    assert a == b


# --------------------------------------------------------------------------- #
# concentracion_maxima
# --------------------------------------------------------------------------- #


def test_concentracion_maxima_basico():
    tickers = ["AAA"] * 25 + [f"T{i}" for i in range(75)]
    out = evaluation.concentracion_maxima(pd.DataFrame({"ticker": tickers}))
    assert out["frac_max_ticker"] == pytest.approx(0.25)
    assert out["ticker_max"] == "AAA"


def test_concentracion_maxima_vacio():
    out = evaluation.concentracion_maxima(pd.DataFrame({"ticker": []}))
    assert out == {"frac_max_ticker": 0.0, "ticker_max": None}


def test_concentracion_maxima_empate_alfabetico():
    df = pd.DataFrame({"ticker": ["BBB", "BBB", "AAA", "AAA"]})
    out = evaluation.concentracion_maxima(df)
    assert out["ticker_max"] == "AAA"
    assert out["frac_max_ticker"] == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# leave_one_ticker_out_signo
# --------------------------------------------------------------------------- #


def test_leave_one_ticker_out_revierte():
    df = pd.DataFrame({"ticker": ["A", "B", "C", "D"], "retorno_10d": [-10.0, 1.0, 1.0, 1.0]})
    out = evaluation.leave_one_ticker_out_signo(df)
    assert out["signo_original"] == -1
    assert out["revierte_con_algun_ticker"] is True
    assert out["reversiones"] == 1


def test_leave_one_ticker_out_robusto():
    df = pd.DataFrame({"ticker": ["A", "B", "C", "D"], "retorno_10d": [5.0, 6.0, 7.0, 8.0]})
    out = evaluation.leave_one_ticker_out_signo(df)
    assert out["signo_original"] == 1
    assert out["revierte_con_algun_ticker"] is False
    assert out["reversiones"] == 0


def test_leave_one_ticker_out_columna_por_defecto_es_retorno_10d():
    df = pd.DataFrame({"ticker": ["A", "B"], "retorno_10d": [1.0, 2.0], "retorno_30d": [-1.0, -2.0]})
    out = evaluation.leave_one_ticker_out_signo(df)
    assert out["signo_original"] == 1  # usa retorno_10d por defecto, no retorno_30d


# --------------------------------------------------------------------------- #
# placebo_aleatorio / percentil_real_vs_placebo
# --------------------------------------------------------------------------- #


def test_placebo_aleatorio_forma_y_reproducibilidad():
    pool = pd.Series(np.arange(20, dtype=float))
    p1 = evaluation.placebo_aleatorio(pool, n_senales=5, n_placebos=50, seed=0)
    p2 = evaluation.placebo_aleatorio(pool, n_senales=5, n_placebos=50, seed=0)
    assert p1.shape == (50,)
    np.testing.assert_array_equal(p1, p2)


def test_placebo_aleatorio_n_senales_invalido():
    pool = pd.Series(np.arange(5, dtype=float))
    with pytest.raises(ValueError):
        evaluation.placebo_aleatorio(pool, n_senales=10, n_placebos=10, seed=0)


def test_percentil_real_vs_placebo():
    placebos = np.array([1, 2, 3, 4, 5])
    assert evaluation.percentil_real_vs_placebo(3, placebos) == pytest.approx(0.6)


# --------------------------------------------------------------------------- #
# etiqueta (distinta de EXP-005: multi-horizonte, no "supera_los_4_baselines")
# --------------------------------------------------------------------------- #


def _base_validated():
    return dict(
        n_horizontes_superados=2,
        mejor_frac_bootstrap=0.85,
        dsr=0.97,
        n_senales_locked=25,
        frac_max_ticker=0.10,
        vecino_revierte_signo=False,
        vecino_destruye_mas_50pct=False,
        placebo_distingue=True,
    )


def test_etiqueta_validated():
    assert evaluation.etiqueta(**_base_validated()) == "VALIDATED"


def test_etiqueta_rejected_por_cada_condicion():
    base = _base_validated()
    casos = [
        {**base, "n_horizontes_superados": 0},
        {**base, "dsr": 0.3},
        {**base, "frac_max_ticker": 0.25},
        {**base, "placebo_distingue": False},
    ]
    for caso in casos:
        assert evaluation.etiqueta(**caso) == "REJECTED"


def test_etiqueta_un_horizonte_no_basta_para_validated():
    out = evaluation.etiqueta(**{**_base_validated(), "n_horizontes_superados": 1})
    assert out == "INCONCLUSIVE"


def test_etiqueta_nan_dsr_no_lanza_excepcion():
    out = evaluation.etiqueta(**{**_base_validated(), "dsr": float("nan")})
    assert out == "INCONCLUSIVE"


def test_etiqueta_placebo_none_no_bloquea_validated():
    out = evaluation.etiqueta(**{**_base_validated(), "placebo_distingue": None})
    assert out == "VALIDATED"

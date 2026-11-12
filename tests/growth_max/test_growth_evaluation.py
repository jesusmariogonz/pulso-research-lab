import numpy as np
import pandas as pd
import pytest

from prl.growth_max.evaluation import (
    bootstrap_bloques_retornos,
    comparacion_bootstrap,
    deflated_sharpe_ratio,
    elegir_variante,
    etiqueta,
    percentil_real_vs_placebo,
    placebo_circular,
    probabilidad_perdida,
    tasa_crecimiento_geometrica,
)


def _idx(n):
    return pd.bdate_range("2015-01-01", periods=n)


def _serie(valores):
    return pd.Series(valores, index=_idx(len(valores)))


# ---------------------------------------------------------------------------
# tasa_crecimiento_geometrica
# ---------------------------------------------------------------------------


def test_tasa_crecimiento_geometrica_coincide_con_calculo_manual():
    n = 252
    r = 0.0008
    ret = _serie([r] * n)
    out = tasa_crecimiento_geometrica(ret)
    equity_final = (1 + r) ** n
    dias_calendario = (ret.index[-1] - ret.index[0]).days
    esperado = equity_final ** (365.25 / dias_calendario) - 1
    assert out == pytest.approx(esperado)


# ---------------------------------------------------------------------------
# bootstrap_bloques_retornos
# ---------------------------------------------------------------------------


def test_bootstrap_bloques_forma_y_reproducibilidad():
    df = pd.DataFrame({"A": np.linspace(0, 1, 100), "B": np.linspace(10, 11, 100)}, index=_idx(100))
    out1 = bootstrap_bloques_retornos(df, tamano_bloque=10, n_replicas=5, seed=42)
    out2 = bootstrap_bloques_retornos(df, tamano_bloque=10, n_replicas=5, seed=42)
    assert out1.shape == (5, 100, 2)
    assert np.array_equal(out1, out2)


def test_bootstrap_bloques_rechaza_ventana_mayor_que_n():
    df = pd.DataFrame({"A": [0.01] * 5}, index=_idx(5))
    with pytest.raises(ValueError):
        bootstrap_bloques_retornos(df, tamano_bloque=10, n_replicas=5, seed=0)


def test_bootstrap_bloques_pareado_misma_posicion_en_ambas_columnas():
    # Col A = índice de fila (0..99); col B = índice de fila * 100.
    # Si el bootstrap es pareado, B_remuestreada debe ser siempre A_remuestreada*100.
    n = 100
    df = pd.DataFrame({"A": np.arange(n, dtype=float), "B": np.arange(n, dtype=float) * 100}, index=_idx(n))
    out = bootstrap_bloques_retornos(df, tamano_bloque=7, n_replicas=10, seed=1)
    a = out[:, :, 0]
    b = out[:, :, 1]
    assert np.allclose(b, a * 100)


# ---------------------------------------------------------------------------
# probabilidad_perdida
# ---------------------------------------------------------------------------


def test_probabilidad_perdida_siempre_cayendo_da_uno():
    ret = _serie([-0.05] * 60)
    p = probabilidad_perdida(ret, umbral=0.5, tamano_bloque=10, n_replicas=50, seed=0)
    assert p == 1.0


def test_probabilidad_perdida_sin_drawdown_da_cero():
    ret = _serie([0.001] * 60)
    p = probabilidad_perdida(ret, umbral=0.01, tamano_bloque=10, n_replicas=50, seed=0)
    assert p == 0.0


# ---------------------------------------------------------------------------
# comparacion_bootstrap
# ---------------------------------------------------------------------------


def test_comparacion_bootstrap_series_identicas_nunca_supera():
    ret = _serie(list(np.random.default_rng(0).normal(0.0005, 0.01, 80)))
    out = comparacion_bootstrap(ret, ret.copy(), tamano_bloque=10, n_replicas=50, seed=0)
    assert out["frac_supera_benchmark"] == 0.0


def test_comparacion_bootstrap_modelo_uniformemente_mejor_siempre_supera():
    base = list(np.random.default_rng(1).normal(0.0, 0.01, 80))
    benchmark = _serie(base)
    modelo = _serie([r + 0.01 for r in base])
    out = comparacion_bootstrap(modelo, benchmark, tamano_bloque=10, n_replicas=50, seed=0)
    assert out["frac_supera_benchmark"] == 1.0
    assert "ci_cagr_modelo" in out and len(out["ci_cagr_modelo"]) == 2


# ---------------------------------------------------------------------------
# deflated_sharpe_ratio
# ---------------------------------------------------------------------------


def test_deflated_sharpe_ratio_no_aumenta_con_mas_intentos():
    ret = _serie(list(np.random.default_rng(2).normal(0.001, 0.01, 300)))
    dsr_1 = deflated_sharpe_ratio(ret, n_trials=1)
    dsr_100 = deflated_sharpe_ratio(ret, n_trials=100)
    assert dsr_100 <= dsr_1


# ---------------------------------------------------------------------------
# elegir_variante
# ---------------------------------------------------------------------------


def test_elegir_variante_filtro_50_gana_sin_importar_log_wealth():
    log_wealth = {"A": 0.05, "B": 0.20}
    prob_50 = {"A": 0.10, "B": 0.30}
    prob_75 = {"A": 0.05, "B": 0.10}
    ganador, motivo = elegir_variante(log_wealth, prob_50, prob_75)
    assert ganador == "A"
    assert motivo == "filtro_50"


def test_elegir_variante_relaja_a_75_si_ninguna_pasa_50():
    log_wealth = {"A": 0.05, "B": 0.20}
    prob_50 = {"A": 0.30, "B": 0.25}
    prob_75 = {"A": 0.10, "B": 0.05}
    ganador, motivo = elegir_variante(log_wealth, prob_50, prob_75)
    assert ganador == "B"
    assert motivo == "filtro_75_relajado"


def test_elegir_variante_ninguna_pasa_ningun_filtro():
    log_wealth = {"A": 0.05}
    prob_50 = {"A": 0.30}
    prob_75 = {"A": 0.25}
    ganador, motivo = elegir_variante(log_wealth, prob_50, prob_75)
    assert ganador is None
    assert motivo == "ninguna_variante_pasa_el_filtro_de_ruina"


# ---------------------------------------------------------------------------
# placebo_circular / percentil_real_vs_placebo
# ---------------------------------------------------------------------------


def test_placebo_circular_forma_y_reproducibilidad():
    ret = _serie(list(np.random.default_rng(3).normal(0.0005, 0.01, 60)))
    out1 = placebo_circular(ret, n_placebos=20, seed=7)
    out2 = placebo_circular(ret, n_placebos=20, seed=7)
    assert out1.shape == (20,)
    assert np.array_equal(out1, out2)


def test_placebo_circular_rechaza_series_muy_cortas():
    with pytest.raises(ValueError):
        placebo_circular(_serie([0.01]), n_placebos=5, seed=0)


def test_percentil_real_vs_placebo():
    placebos = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert percentil_real_vs_placebo(3.0, placebos) == pytest.approx(0.6)
    assert percentil_real_vs_placebo(0.0, np.array([])) == 0.0


# ---------------------------------------------------------------------------
# etiqueta
# ---------------------------------------------------------------------------


def test_etiqueta_inconclusive_por_locked_test_corto():
    assert etiqueta((0.05, 0.10), 0.90, 0.05, n_dias_locked_test=500) == "INCONCLUSIVE"


def test_etiqueta_rejected_por_no_superar_benchmark():
    assert etiqueta((0.05, 0.10), 0.40, 0.05, n_dias_locked_test=800) == "REJECTED"


def test_etiqueta_rejected_por_probabilidad_de_ruina():
    assert etiqueta((0.05, 0.10), 0.90, 0.25, n_dias_locked_test=800) == "REJECTED"


def test_etiqueta_validated():
    assert etiqueta((0.01, 0.10), 0.85, 0.05, n_dias_locked_test=800) == "VALIDATED"


def test_etiqueta_inconclusive_caso_intermedio():
    assert etiqueta((0.01, 0.10), 0.60, 0.05, n_dias_locked_test=800) == "INCONCLUSIVE"


def test_etiqueta_nan_en_ci_no_lanza_excepcion_y_da_inconclusive():
    out = etiqueta((np.nan, 0.10), 0.90, 0.05, n_dias_locked_test=800)
    assert out == "INCONCLUSIVE"

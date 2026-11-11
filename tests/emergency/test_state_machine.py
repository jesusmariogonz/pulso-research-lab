import numpy as np
import pandas as pd

from prl.emergency import state_machine as sm


def _s(valores):
    return pd.Series(valores, index=pd.bdate_range("2020-01-01", periods=len(valores)), dtype=float)


def test_exposicion_por_nivel():
    assert [sm.exposure_for_level(i) for i in range(5)] == [1.0, 0.75, 0.5, 0.25, 0.0]


def test_niveles_crudos_por_umbral():
    score = _s([-1, 0.4, 0.5, 1.0, 1.49, 2.0, 3.9, 4.0, 9.0, np.nan])
    assert list(sm.raw_levels(score, theta=1.0)) == [0, 0, 0, 1, 1, 2, 3, 4, 4, 0]
    assert sm.raw_levels(_s([0.5]), theta=0.5).iloc[0] == 1


def test_una_sola_senal_no_cambia_el_nivel_si_no_dura_k_dias():
    score = _s([0, 0, 0, 3.5, 3.5, 0, 0, 0, 0, 0, 0, 0])
    niveles = sm.assign_levels(score, theta=1.0, k=3, m=5)
    assert (niveles == 0).all()


def test_sube_cuando_la_senal_dura_k_dias():
    score = _s([0, 0, 0, 3.5, 3.5, 3.5, 3.5])
    niveles = sm.assign_levels(score, theta=1.0, k=3, m=5)
    assert list(niveles) == [0, 0, 0, 0, 0, 3, 3]


def test_sube_por_escalones_segun_el_minimo_de_la_ventana():
    score = _s([2, 2, 2, 3, 3, 3])
    niveles = sm.assign_levels(score, theta=1.0, k=3, m=5)
    assert list(niveles) == [0, 0, 2, 2, 2, 3]


def test_baja_solo_tras_m_dias_seguidos_mas_bajos():
    score = _s([3, 3, 3] + [1] * 6)
    niveles = sm.assign_levels(score, theta=1.0, k=3, m=5)
    # sube a 3 en el día 2; los 1 empiezan en el día 3; la ventana de 5 días
    # sin 3 se completa en el día 7 -> baja a 1.
    assert list(niveles) == [0, 0, 3, 3, 3, 3, 3, 1, 1]


def test_devuelve_enteros_con_el_indice_de_entrada():
    score = _s([0, 1, 2, 3])
    niveles = sm.assign_levels(score, theta=1.0, k=2, m=2)
    assert niveles.index.equals(score.index)
    assert np.issubdtype(niveles.dtype, np.integer)


def test_sin_look_ahead_en_los_niveles():
    rng = np.random.default_rng(0)
    score = _s(rng.normal(1, 1.5, 400))
    full = sm.assign_levels(score, theta=1.0, k=3, m=10)
    corte = sm.assign_levels(score.iloc[:250], theta=1.0, k=3, m=10)
    assert list(full.iloc[:250]) == list(corte)

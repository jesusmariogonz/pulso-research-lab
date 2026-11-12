import pandas as pd
import pytest

from prl.data.macro_vintage import (
    parse_vintage_observations,
    serie_conocida_en,
    ultimo_valor_conocido,
    validar_vintages,
)

HOY_SIEMPRE_VIGENTE = pd.Timestamp("9999-12-31")


def _fila(obs_date, value, realtime_start, realtime_end=HOY_SIEMPRE_VIGENTE):
    return {
        "obs_date": pd.Timestamp(obs_date),
        "value": value,
        "realtime_start": pd.Timestamp(realtime_start),
        "realtime_end": pd.Timestamp(realtime_end),
    }


def _df(filas):
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# ultimo_valor_conocido
# ---------------------------------------------------------------------------


def test_reconstruccion_basica_de_una_revision():
    df = _df(
        [
            _fila("2020-01-01", 100.0, "2020-02-12", "2020-03-14"),
            _fila("2020-01-01", 100.2, "2020-03-15"),
        ]
    )

    antes = ultimo_valor_conocido(df, "2020-02-01")
    assert antes == {"obs_date": None, "value": None, "antiguedad_dias": None}

    tras_primera_publicacion = ultimo_valor_conocido(df, "2020-02-20")
    assert tras_primera_publicacion["value"] == 100.0
    assert tras_primera_publicacion["obs_date"] == pd.Timestamp("2020-01-01")

    tras_revision = ultimo_valor_conocido(df, "2020-04-01")
    assert tras_revision["value"] == 100.2
    assert tras_revision["obs_date"] == pd.Timestamp("2020-01-01")


def test_frontera_de_look_ahead():
    df = _df(
        [
            _fila("2020-01-01", 100.0, "2020-02-12", "2020-03-14"),
            # Esta fila es la más reciente por obs_date, pero su realtime_start
            # es futuro respecto a la fecha de corte que consultamos abajo:
            # NUNCA debe filtrarse al resultado.
            _fila("2020-06-01", 999.0, "2030-01-01"),
        ]
    )
    r = ultimo_valor_conocido(df, "2020-02-20")
    assert r["value"] == 100.0
    assert r["obs_date"] == pd.Timestamp("2020-01-01")


def test_elige_el_obs_date_mas_reciente_entre_los_ya_conocidos():
    df = _df(
        [
            _fila("2020-01-01", 1.0, "2020-02-12"),
            _fila("2020-02-01", 2.0, "2020-03-12"),
            _fila("2020-03-01", 3.0, "2020-04-12"),
        ]
    )
    # 2020-03-20: ya se conocen enero y febrero, pero NO marzo (publica el 04-12).
    r = ultimo_valor_conocido(df, "2020-03-20")
    assert r["obs_date"] == pd.Timestamp("2020-02-01")
    assert r["value"] == 2.0


def test_nada_conocido_todavia_no_lanza_excepcion():
    df = _df([_fila("2020-01-01", 1.0, "2020-02-12")])
    r = ultimo_valor_conocido(df, "2019-01-01")
    assert r == {"obs_date": None, "value": None, "antiguedad_dias": None}


def test_bordes_inclusivos_de_la_ventana_vigente():
    df = _df([_fila("2020-01-01", 1.0, "2020-02-12", "2020-03-14")])
    r_inicio = ultimo_valor_conocido(df, "2020-02-12")
    r_fin = ultimo_valor_conocido(df, "2020-03-14")
    assert r_inicio["value"] == 1.0
    assert r_fin["value"] == 1.0


def test_antiguedad_dias_es_no_negativa_y_correcta():
    df = _df([_fila("2020-01-01", 1.0, "2020-02-12")])
    r = ultimo_valor_conocido(df, "2020-02-20")
    assert r["antiguedad_dias"] == (pd.Timestamp("2020-02-20") - pd.Timestamp("2020-01-01")).days
    assert r["antiguedad_dias"] >= 0


# ---------------------------------------------------------------------------
# serie_conocida_en (vectorizada) == ultimo_valor_conocido fila por fila
# ---------------------------------------------------------------------------


def test_serie_conocida_en_coincide_con_version_escalar():
    df = _df(
        [
            _fila("2020-01-01", 1.0, "2020-02-12", "2020-03-14"),
            _fila("2020-01-01", 1.5, "2020-03-15"),
            _fila("2020-02-01", 2.0, "2020-03-12"),
        ]
    )
    fechas = pd.bdate_range("2020-01-01", "2020-04-01")
    out = serie_conocida_en(df, fechas)

    assert list(out.index) == list(fechas)
    for f in fechas:
        esperado = ultimo_valor_conocido(df, f)
        fila = out.loc[f]
        if esperado["value"] is None:
            assert pd.isna(fila["value"])
            assert pd.isna(fila["obs_date_origen"])
            assert pd.isna(fila["antiguedad_dias"])
        else:
            assert fila["value"] == esperado["value"]
            assert fila["obs_date_origen"] == esperado["obs_date"]
            assert fila["antiguedad_dias"] == esperado["antiguedad_dias"]


# ---------------------------------------------------------------------------
# parse_vintage_observations
# ---------------------------------------------------------------------------


def test_parse_filtra_valores_sin_dato():
    raw = [
        {"date": "2020-01-01", "value": "100.0", "realtime_start": "2020-02-12", "realtime_end": "9999-12-31"},
        {"date": "2020-02-01", "value": ".", "realtime_start": "2020-03-12", "realtime_end": "9999-12-31"},
    ]
    out = parse_vintage_observations(raw)
    assert len(out) == 1
    assert out.iloc[0]["value"] == 100.0


def test_parse_devuelve_vacio_con_columnas_para_lista_vacia():
    out = parse_vintage_observations([])
    assert len(out) == 0
    assert set(out.columns) == {"obs_date", "value", "realtime_start", "realtime_end"}


def test_parse_rechaza_realtime_start_antes_de_obs_date():
    raw = [{"date": "2020-06-01", "value": "1.0", "realtime_start": "2020-01-01", "realtime_end": "9999-12-31"}]
    with pytest.raises(ValueError):
        parse_vintage_observations(raw)


def test_parse_rechaza_realtime_start_posterior_a_realtime_end():
    raw = [{"date": "2020-01-01", "value": "1.0", "realtime_start": "2020-06-01", "realtime_end": "2020-01-01"}]
    with pytest.raises(ValueError):
        parse_vintage_observations(raw)


# ---------------------------------------------------------------------------
# validar_vintages
# ---------------------------------------------------------------------------


def test_validar_vintages_sin_problemas():
    df = _df(
        [
            _fila("2020-01-01", 1.0, "2020-02-12", "2020-03-14"),
            _fila("2020-01-01", 1.5, "2020-03-15"),
            _fila("2020-02-01", 2.0, "2020-03-12"),
        ]
    )
    assert validar_vintages(df) == []


def test_validar_vintages_detecta_realtime_start_antes_de_obs_date():
    df = _df([_fila("2020-06-01", 1.0, "2020-01-01")])
    problemas = validar_vintages(df)
    assert any("REALTIME_START_ANTES_DE_OBS_DATE" in p for p in problemas)


def test_validar_vintages_detecta_ventanas_superpuestas():
    df = _df(
        [
            _fila("2020-01-01", 1.0, "2020-02-12", "2020-04-01"),
            _fila("2020-01-01", 1.5, "2020-03-15"),
        ]
    )
    problemas = validar_vintages(df)
    assert any("VENTANAS_INCONSISTENTES" in p for p in problemas)


def test_validar_vintages_detecta_hueco_entre_ventanas():
    # 2020-03-14 cierra la primera versión; la siguiente no abre hasta
    # 2020-03-20: seis días sin ninguna versión vigente para ese obs_date.
    df = _df(
        [
            _fila("2020-01-01", 1.0, "2020-02-12", "2020-03-14"),
            _fila("2020-01-01", 1.5, "2020-03-20"),
        ]
    )
    problemas = validar_vintages(df)
    assert any("VENTANAS_INCONSISTENTES" in p for p in problemas)


def test_validar_vintages_ventanas_contiguas_no_marca_problema():
    df = _df(
        [
            _fila("2020-01-01", 1.0, "2020-02-12", "2020-03-14"),
            _fila("2020-01-01", 1.5, "2020-03-15"),
        ]
    )
    assert validar_vintages(df) == []


def test_validar_vintages_detecta_obs_date_sin_version_vigente():
    df = _df([_fila("2020-01-01", 1.0, "2020-02-12", "2020-03-14")])
    problemas = validar_vintages(df)
    assert any("OBS_DATE_SIN_VERSION_VIGENTE" in p for p in problemas)

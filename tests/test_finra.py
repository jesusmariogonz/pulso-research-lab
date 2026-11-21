import pandas as pd
import pytest

from prl.data.finra import (
    fecha_publicacion,
    generar_candidatos_settlement,
    parse_short_interest_csv,
    parse_short_volume_diario,
    ultimo_short_interest_vigente,
)

SHORT_VOLUME_MUESTRA = """Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
20261115|A|375361|51|1022954|B,Q,N
20261115|AA|2525696|2667|5219684|B,Q,N
"""


def test_parse_short_volume_diario():
    df = parse_short_volume_diario(SHORT_VOLUME_MUESTRA)
    assert list(df["symbol"]) == ["A", "AA"]
    assert df["date"].iloc[0] == pd.Timestamp("2026-11-15")
    assert df["short_volume_ratio"].iloc[0] == pytest.approx(375361 / 1022954)


def test_parse_short_volume_diario_descarta_linea_de_pie():
    """El archivo real trae una línea de pie con el conteo de
    registros (un solo campo, sin pipes, ej. "12343") — debe
    descartarse, no romper el parseo ni colarse como una fila más."""
    texto = SHORT_VOLUME_MUESTRA + "2\n"
    df = parse_short_volume_diario(texto)
    assert len(df) == 2
    assert list(df["symbol"]) == ["A", "AA"]


def test_parse_short_volume_diario_total_cero_da_nan_no_error():
    texto = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n20261115|ZZZ|0|0|0|B\n"
    df = parse_short_volume_diario(texto)
    assert pd.isna(df["short_volume_ratio"].iloc[0])


SHORT_INTEREST_MUESTRA = (
    '"accountingYearMonthNumber"|"symbolCode"|"issueName"|"issuerServicesGroupExchangeCode"|'
    '"marketClassCode"|"currentShortPositionQuantity"|"previousShortPositionQuantity"|'
    '"stockSplitFlag"|"averageDailyVolumeQuantity"|"daysToCoverQuantity"|"revisionFlag"|'
    '"changePercent"|"changePreviousNumber"|"settlementDate"\n'
    '"20261015"|"A"|"Agilent Technologies Inc."|"A"|"NYSE"|"5025670"|"5240309"||"2076655"|'
    '"2.42"||"-4.10"|"-214639"|"2026-10-15"\n'
)


def test_parse_short_interest_csv():
    df = parse_short_interest_csv(SHORT_INTEREST_MUESTRA)
    assert df["symbol"].iloc[0] == "A"
    assert df["days_to_cover"].iloc[0] == 2.42
    assert df["short_interest"].iloc[0] == 5025670
    assert df["settlement_date"].iloc[0] == pd.Timestamp("2026-10-15")


def test_generar_candidatos_settlement_da_dos_por_mes():
    candidatos = generar_candidatos_settlement(pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-31"))
    assert len(candidatos) == 6  # 2 por mes x 3 meses


def test_generar_candidatos_settlement_mueve_el_15_si_cae_fin_de_semana():
    # 2026-11-15 es domingo -> debe mover al viernes 2026-11-13
    candidatos = generar_candidatos_settlement(pd.Timestamp("2026-11-01"), pd.Timestamp("2026-11-30"))
    assert pd.Timestamp("2026-11-13") in candidatos
    assert pd.Timestamp("2026-11-15") not in candidatos


def test_fecha_publicacion_es_7_dias_habiles_despues():
    # 2026-10-15 es jueves -> +7 días hábiles = 2026-10-26 (lunes)
    assert fecha_publicacion(pd.Timestamp("2026-10-15")) == pd.Timestamp("2026-10-26")


def _snapshot(valor):
    return pd.DataFrame({"symbol": ["A"], "short_interest": [valor]})


def test_ultimo_short_interest_vigente_nunca_usa_el_que_aun_no_se_publico():
    """El test más importante del módulo: evita look-ahead. Settlement
    2026-10-15 se publica hasta 2026-10-26 (7 días hábiles después) —
    un as_of ANTES de esa fecha de publicación debe devolver el
    snapshot ANTERIOR (settlement 2026-09-15), no el nuevo."""
    snapshots = {
        pd.Timestamp("2026-09-15"): _snapshot(100),
        pd.Timestamp("2026-10-15"): _snapshot(200),
    }

    antes_de_publicarse = ultimo_short_interest_vigente(snapshots, pd.Timestamp("2026-10-20"))
    assert antes_de_publicarse["short_interest"].iloc[0] == 100

    despues_de_publicarse = ultimo_short_interest_vigente(snapshots, pd.Timestamp("2026-10-27"))
    assert despues_de_publicarse["short_interest"].iloc[0] == 200


def test_ultimo_short_interest_vigente_sin_nada_publicado_da_none():
    snapshots = {pd.Timestamp("2026-10-15"): _snapshot(200)}
    assert ultimo_short_interest_vigente(snapshots, pd.Timestamp("2026-10-16")) is None

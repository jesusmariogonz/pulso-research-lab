import json

import pandas as pd
import pytest

from prl.data import build


def _df(dates, closes):
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"close": closes, "adj_close": closes}, index=idx)


@pytest.fixture(autouse=True)
def entorno_aislado(tmp_path, monkeypatch):
    catalogo = {
        "series": [
            {"id": "FOO", "source": "yahoo", "symbol": "FOO", "role": "x", "notes": ""},
            {"id": "BAR", "source": "yahoo", "symbol": "BAR", "role": "x", "notes": ""},
        ],
        "universes": [],
    }
    # `cargar_catalogo` resuelve su default `path=CATALOGO` en tiempo de
    # definición (no en cada llamada), así que monkeypatchear `build.CATALOGO`
    # no lo afecta — se parchea la función misma.
    monkeypatch.setattr(build, "cargar_catalogo", lambda path=None: catalogo)
    monkeypatch.setattr(build, "RAW", tmp_path / "raw")
    monkeypatch.setattr(build, "MANIFIESTO", tmp_path / "manifest.json")
    monkeypatch.setattr(build, "REPORTE", tmp_path / "quality_report.md")
    yield


def test_construir_sin_only_descarga_todo(monkeypatch):
    monkeypatch.setattr(build, "descargar_yahoo", lambda symbol, inicio=None: _df(["2020-01-01", "2020-01-02"], [1.0, 2.0]))
    m = build.construir()
    assert set(m["series"]) == {"FOO", "BAR"}


def test_construir_con_only_no_borra_series_de_una_corrida_previa(monkeypatch):
    """Bug real encontrado el 2026-11-21 (EXP-004): correr construir(only=[...])
    para un subconjunto del catálogo borraba el manifiesto entero, perdiendo
    el hash/procedencia de series ya congeladas por una corrida anterior con
    un `only` distinto (en producción: las 207 series de EXP-001/EXP-002
    desaparecieron al correr el universo nuevo de EXP-004)."""
    monkeypatch.setattr(build, "descargar_yahoo", lambda symbol, inicio=None: _df(["2020-01-01", "2020-01-02"], [1.0, 2.0]))

    primera = build.construir(only=["FOO"])
    assert set(primera["series"]) == {"FOO"}

    segunda = build.construir(only=["BAR"])
    assert set(segunda["series"]) == {"FOO", "BAR"}, "la segunda corrida debe conservar FOO, no solo tener BAR"

    en_disco = json.loads(build.MANIFIESTO.read_text())
    assert set(en_disco["series"]) == {"FOO", "BAR"}


def test_construir_actualiza_una_serie_que_ya_existia(monkeypatch):
    monkeypatch.setattr(build, "descargar_yahoo", lambda symbol, inicio=None: _df(["2020-01-01", "2020-01-02"], [1.0, 2.0]))
    build.construir(only=["FOO"])

    monkeypatch.setattr(build, "descargar_yahoo", lambda symbol, inicio=None: _df(["2020-01-01", "2020-01-02", "2020-01-03"], [1.0, 2.0, 3.0]))
    segunda = build.construir(only=["FOO"])

    assert segunda["series"]["FOO"]["filas"] == 3, "re-correr la misma serie debe actualizar su entrada, no duplicarla ni dejar la vieja"


def test_construir_limpia_una_fallida_si_ahora_tiene_exito(monkeypatch):
    def falla(symbol, inicio=None):
        raise ValueError("boom")

    monkeypatch.setattr(build, "descargar_yahoo", falla)
    primera = build.construir(only=["FOO"])
    assert "FOO" in primera["fallidas"]
    assert "FOO" not in primera["series"]

    monkeypatch.setattr(build, "descargar_yahoo", lambda symbol, inicio=None: _df(["2020-01-01"], [1.0]))
    segunda = build.construir(only=["FOO"])
    assert "FOO" not in segunda["fallidas"], "una serie que antes falló y ahora tiene éxito no debe seguir en fallidas"
    assert "FOO" in segunda["series"]


def _df_yahoo_crudo(dates, closes):
    """Shape crudo que entrega yfinance (columnas con mayúscula), antes de
    que descargar_yahoo las renombre."""
    idx = pd.to_datetime(dates)
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [100] * len(closes)},
        index=idx,
    )


def test_descargar_yahoo_lanza_error_si_el_dato_mas_reciente_esta_viejo(monkeypatch):
    hoy = pd.Timestamp.now().normalize()
    vieja = hoy - pd.Timedelta(days=build.UMBRAL_DATOS_VIEJOS_DIAS + 1)
    monkeypatch.setattr("yfinance.download", lambda *a, **k: _df_yahoo_crudo([vieja], [100.0]))

    with pytest.raises(RuntimeError, match="días de atraso"):
        build.descargar_yahoo("SPY")


def test_descargar_yahoo_acepta_datos_dentro_del_umbral(monkeypatch):
    hoy = pd.Timestamp.now().normalize()
    reciente = hoy - pd.Timedelta(days=build.UMBRAL_DATOS_VIEJOS_DIAS)
    monkeypatch.setattr("yfinance.download", lambda *a, **k: _df_yahoo_crudo([reciente], [100.0]))

    df = build.descargar_yahoo("SPY")

    assert df.index.max() == reciente

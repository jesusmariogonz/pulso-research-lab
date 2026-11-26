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
    monkeypatch.setattr(build.time, "sleep", lambda s: None)
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


def test_descargar_yahoo_reintenta_tras_dato_viejo_y_al_final_trae_datos_frescos(monkeypatch):
    monkeypatch.setattr(build.time, "sleep", lambda s: None)
    hoy = pd.Timestamp.now().normalize()
    vieja = hoy - pd.Timedelta(days=build.UMBRAL_DATOS_VIEJOS_DIAS + 1)
    llamadas = {"n": 0}

    def descarga(*a, **k):
        llamadas["n"] += 1
        fecha = vieja if llamadas["n"] == 1 else hoy
        return _df_yahoo_crudo([fecha], [100.0])

    monkeypatch.setattr("yfinance.download", descarga)

    df = build.descargar_yahoo("SPY")

    assert df.index.max() == hoy
    assert llamadas["n"] == 2


def test_descargar_yahoo_agota_reintentos_si_siempre_llega_vacio(monkeypatch):
    monkeypatch.setattr(build.time, "sleep", lambda s: None)
    llamadas = {"n": 0}

    def descarga(*a, **k):
        llamadas["n"] += 1
        return pd.DataFrame()

    monkeypatch.setattr("yfinance.download", descarga)

    with pytest.raises(RuntimeError, match="no devolvió datos"):
        build.descargar_yahoo("CWEN-A")
    assert llamadas["n"] == build.DESCARGA_REINTENTOS


def _catalogo_con_universo(tmp_path, miembros):
    """Catálogo con una serie explícita (FOO, crítica) y un universo (sus
    miembros NO son críticos — pueden fallar sin tumbar la corrida)."""
    universo_dir = tmp_path / "data" / "universes"
    universo_dir.mkdir(parents=True, exist_ok=True)
    (universo_dir / "uni1.txt").write_text("\n".join(miembros))
    return {
        "series": [{"id": "FOO", "source": "yahoo", "symbol": "FOO", "role": "x", "notes": ""}],
        "universes": [{"id": "uni1", "file": "universes/uni1.txt", "notes": ""}],
    }


def _descargar_con_fallidos(fallidos: set[str]):
    def descargar(symbol, inicio=None):
        if symbol in fallidos:
            raise RuntimeError(f"{symbol}: possibly delisted")
        return _df(["2020-01-01"], [1.0])
    return descargar


def test_main_falla_si_una_serie_critica_del_catalogo_falla(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "cargar_catalogo", lambda path=None: _catalogo_con_universo(tmp_path, ["A", "B"]))
    monkeypatch.setattr(build, "descargar_yahoo", _descargar_con_fallidos({"FOO"}))

    assert build.main([]) == 1


def test_main_no_falla_si_solo_fallan_pocos_simbolos_de_universo(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "cargar_catalogo", lambda path=None: _catalogo_con_universo(tmp_path, ["A", "B", "C"]))
    monkeypatch.setattr(build, "descargar_yahoo", _descargar_con_fallidos({"A"}))

    assert build.main([]) == 0, "un símbolo de universo fallido (churn normal) no debe tumbar la corrida"


def test_main_falla_si_fallan_demasiados_simbolos_de_universo(tmp_path, monkeypatch):
    miembros = [f"SYM{i}" for i in range(build.UMBRAL_FALLIDAS_UNIVERSO + 5)]
    fallidos = set(miembros[: build.UMBRAL_FALLIDAS_UNIVERSO + 1])
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "cargar_catalogo", lambda path=None: _catalogo_con_universo(tmp_path, miembros))
    monkeypatch.setattr(build, "descargar_yahoo", _descargar_con_fallidos(fallidos))

    assert build.main([]) == 1, "demasiados fallos de universo a la vez huele a bloqueo sistémico, no a churn"


class _RespuestaFalsa:
    def __init__(self, status_code, text, ok=None):
        self.status_code = status_code
        self.text = text
        self.ok = ok if ok is not None else (200 <= status_code < 300)

    def json(self):
        import json as _json
        return _json.loads(self.text)


def test_descargar_fred_vintage_incluye_el_cuerpo_de_la_respuesta_en_el_error(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "clave-de-prueba")
    cuerpo = '{"error_code":400,"error_message":"clave invalida"}'
    monkeypatch.setattr("requests.get", lambda *a, **k: _RespuestaFalsa(400, cuerpo))

    with pytest.raises(RuntimeError, match="clave invalida"):
        build.descargar_fred_vintage("CPIAUCSL")

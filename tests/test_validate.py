import pandas as pd

from prl.data.validate import validar_serie


def _serie(valores, inicio="2020-01-01", **extra):
    idx = pd.bdate_range(inicio, periods=len(valores))
    df = pd.DataFrame({"close": valores, "adj_close": valores}, index=idx)
    for k, v in extra.items():
        df[k] = v
    return df


def codigos(res):
    return {h["codigo"] for h in res["hallazgos"]}


def test_serie_limpia_no_tiene_hallazgos():
    res = validar_serie(_serie([100 + i * 0.1 for i in range(50)]), {"role": "equity_etf"})
    assert res["hallazgos"] == []


def test_detecta_fechas_duplicadas_y_desorden():
    df = _serie([1.0, 2.0, 3.0])
    df = pd.concat([df, df.iloc[[0]]])
    res = validar_serie(df, {"role": "equity_etf"})
    assert {"FECHAS_DUPLICADAS", "INDICE_NO_MONOTONO"} <= codigos(res)


def test_detecta_precio_no_positivo_pero_lo_permite_en_tasas():
    df = _serie([1.0, 0.0, 2.0])
    assert "PRECIO_NO_POSITIVO" in codigos(validar_serie(df, {"role": "equity_etf"}))
    assert "PRECIO_NO_POSITIVO" not in codigos(validar_serie(df, {"role": "yield"}))


def test_detecta_retorno_extremo():
    res = validar_serie(_serie([100, 100.5, 40, 41]), {"role": "equity_etf"})
    assert "RETORNOS_EXTREMOS" in codigos(res)


def test_detecta_hueco_largo():
    idx = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-03-02"])
    df = pd.DataFrame({"close": [1.0, 1.01, 1.02], "adj_close": [1.0, 1.01, 1.02]}, index=idx)
    assert "HUECOS" in codigos(validar_serie(df, {"role": "equity_etf"}))


def test_detecta_racha_de_precios_identicos():
    df = _serie([10, 10.1] + [10.2] * 8 + [10.3])
    assert "RACHA_DE_PRECIOS_IDENTICOS" in codigos(validar_serie(df, {"role": "equity_etf"}))


def test_detecta_high_menor_que_low():
    df = _serie([10, 10.1, 10.2], high=[10, 10.1, 9.0], low=[9.9, 10.0, 10.1])
    assert "HIGH_MENOR_QUE_LOW" in codigos(validar_serie(df, {"role": "equity_etf"}))

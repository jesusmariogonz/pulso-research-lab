from prl.data.equity_universe import (
    construir_universo,
    normalizar_simbolo_yahoo,
    parse_sp500_csv,
    parse_wikipedia_tabla_simbolos,
)


def test_normaliza_simbolos_con_clase_de_accion():
    assert normalizar_simbolo_yahoo("BRK.B") == "BRK-B"
    assert normalizar_simbolo_yahoo("BF.B") == "BF-B"
    assert normalizar_simbolo_yahoo("AAPL") == "AAPL"
    assert normalizar_simbolo_yahoo("aapl") == "AAPL"
    assert normalizar_simbolo_yahoo("  msft ") == "MSFT"


SP500_CSV_MUESTRA = """Symbol,Security,GICS Sector,GICS Sub-Industry,Headquarters Location,Date added,CIK,Founded
MMM,3M,Industrials,Industrial Conglomerates,"Saint Paul, Minnesota",1957-03-04,66740,1902
AOS,A. O. Smith,Industrials,Building Products,"Milwaukee, Wisconsin",2017-07-26,91142,1916
BRK.B,Berkshire Hathaway,Financials,Multi-Sector Holdings,"Omaha, Nebraska",2010-02-16,1067983,1839
"""


def test_parse_sp500_csv():
    simbolos = parse_sp500_csv(SP500_CSV_MUESTRA)
    assert simbolos == ["MMM", "AOS", "BRK.B"]


WIKI_TABLA_MUESTRA = """
<html><body>
<table class="wikitable sortable">
<tr><th>Symbol</th><th>Company</th><th>Sector</th></tr>
<tr><td>AAON</td><td>AAON Inc</td><td>Industrials</td></tr>
<tr><td>ACIW</td><td>ACI Worldwide</td><td>Information Technology</td></tr>
<tr><td>BRK.B</td><td>Berkshire (ejemplo repetido para probar dedupe)</td><td>Financials</td></tr>
</table>
</body></html>
"""


def test_parse_wikipedia_tabla_simbolos():
    simbolos = parse_wikipedia_tabla_simbolos(WIKI_TABLA_MUESTRA)
    assert simbolos == ["AAON", "ACIW", "BRK.B"]


def test_construir_universo_normaliza_deduplica_y_ordena():
    sp500 = ["MMM", "AOS", "BRK.B"]
    sp400 = ["AAON", "brk.b"]  # BRK.B repetido (mayúsculas distintas) a propósito
    sp600 = ["ACIW"]

    universo = construir_universo(sp500, sp400, sp600)

    assert universo == ["AAON", "ACIW", "AOS", "BRK-B", "MMM"]  # ordenado, sin duplicar BRK-B
    assert len(universo) == 5


def test_construir_universo_vacio_da_lista_vacia():
    assert construir_universo([], [], []) == []

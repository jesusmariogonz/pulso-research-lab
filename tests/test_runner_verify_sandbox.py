import json
from pathlib import Path

import pandas as pd
import pytest

from prl import runner
from prl.llm.deepseek import Budget, DeepSeek, PresupuestoAgotado
from prl.sandbox import CodigoNoPermitido, ejecutar, revisar_codigo
from prl.verify import verificar_borrador

RESULTS = {
    "primera_fecha": "1993-01-29",
    "n_observaciones": 8500,
    "cagr": 0.1015,
    "max_drawdown": -0.5519,
    "periodos": [{"x": 0.0152}],
}


# ---------------- verify ----------------
def test_acepta_cifras_respaldadas_en_fraccion_o_porcentaje():
    md = "CAGR 10.15% y MaxDD de -55.2%. Desde 1993-01-29, 8,500 observaciones."
    r = verificar_borrador(md, RESULTS)
    assert r.ok, r.no_respaldadas


def test_rechaza_cifra_inventada():
    r = verificar_borrador("El CAGR fue 12.7% y el Sharpe 0.82.", RESULTS)
    assert not r.ok
    assert "12.7%" in r.no_respaldadas and "0.82" in r.no_respaldadas


def test_acepta_anios_y_enteros_pequenos_pero_no_otros_enteros():
    assert verificar_borrador("En 2008 hubo 3 episodios.", RESULTS).ok
    assert not verificar_borrador("Hubo 47 episodios.", RESULTS).ok


def test_una_fecha_que_no_esta_en_results_se_marca():
    r = verificar_borrador("El mínimo fue el 2009-03-09.", RESULTS)
    assert not r.ok


# ---------------- sandbox ----------------
@pytest.mark.parametrize("codigo", [
    "import os\n",
    "import requests\n",
    "import subprocess\n",
    "from socket import socket\n",
    "eval('1+1')\n",
    "import pandas as pd\npd.io.common.os.system('x')\n",
    "x = (1).__class__\n",
])
def test_revision_estatica_rechaza_codigo_peligroso(codigo):
    with pytest.raises(CodigoNoPermitido):
        revisar_codigo(codigo)


def test_ejecucion_sin_secretos_en_el_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "no-debe-verse")
    codigo = (
        "import json\n"
        "json.dump({'ok': 1}, open('results.json', 'w'))\n"
    )
    e = ejecutar(codigo, tmp_path)
    assert e.ok and json.loads((tmp_path / "results.json").read_text()) == {"ok": 1}


# ---------------- budget ----------------
def test_presupuesto_corta_las_llamadas():
    b = Budget(max_llamadas=1, max_tokens_salida_total=100)
    b.antes_de_llamar(50)
    b.despues_de_llamar(50)
    with pytest.raises(PresupuestoAgotado):
        b.antes_de_llamar(10)


# ---------------- runner (con LLM falso) ----------------
class FalsoDS(DeepSeek):
    def __init__(self, bitacora, respuestas):
        super().__init__(bitacora=bitacora, budget=Budget())
        self._r = list(respuestas)

    def chat(self, mensajes, **kw):
        self.budget.antes_de_llamar(kw.get("max_tokens", 1))
        self.budget.despues_de_llamar(10)
        return self._r.pop(0)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    idx = pd.bdate_range("2020-01-01", periods=300)
    pd.DataFrame({"adj_close": [100 + i * 0.1 for i in range(300)]}, index=idx).rename_axis("date").to_parquet(raw / "SPY.parquet")
    exp = tmp_path / "experiments" / "EXP-T"
    exp.mkdir(parents=True)
    (exp / "PREREGISTRATION.md").write_text("**Estado:** `LOCKED`\n")
    (exp / "spec.yaml").write_text("id: EXP-T\nseries: [SPY]\ntarea: 'calcula n'\nresults_schema: {n_observaciones: entero}\n")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "RAW", raw)
    monkeypatch.setattr(runner, "MANIFIESTO", tmp_path / "data" / "manifest.json")
    return exp


CODIGO_OK = (
    "```python\nimport pandas as pd, json\n"
    "d = pd.read_parquet('inputs/SPY.parquet')\n"
    "json.dump({'n_observaciones': int(len(d))}, open('results.json','w'))\n```"
)


def test_no_corre_si_el_preregistro_no_esta_bloqueado(entorno):
    (entorno / "PREREGISTRATION.md").write_text("**Estado:** `DRAFT`\n")
    with pytest.raises(runner.ExperimentoNoBloqueado):
        runner.correr(entorno)


def test_flujo_completo_aprobado(entorno, tmp_path):
    ds = FalsoDS(tmp_path / "log.jsonl", [CODIGO_OK, "Resumen: hay 300 observaciones."])
    v = runner.correr(entorno, cliente=ds)
    assert v["estado"] == "APROBADO_PARA_REVISION", v
    assert v["llamadas"] == 2


def test_borrador_con_cifra_inventada_se_rechaza_tras_el_reintento(entorno, tmp_path):
    ds = FalsoDS(tmp_path / "log.jsonl", [CODIGO_OK, "Hay 999 observaciones.", "Siguen siendo 999."])
    v = runner.correr(entorno, cliente=ds)
    assert v["estado"] == "FALLIDO" and "sin respaldo" in v["motivo"]


def test_codigo_peligroso_se_rechaza_y_reintenta(entorno, tmp_path):
    malo = "```python\nimport os\nos.system('x')\n```"
    ds = FalsoDS(tmp_path / "log.jsonl", [malo, CODIGO_OK, "Hay 300 observaciones."])
    v = runner.correr(entorno, cliente=ds)
    assert v["estado"] == "APROBADO_PARA_REVISION", v


def test_modo_calculo_fijo_no_pide_codigo_al_llm_y_usa_la_etiqueta_del_codigo(entorno, tmp_path, monkeypatch):
    modulo = tmp_path / "mod_calculo_falso.py"
    modulo.write_text(
        "import json\n"
        "def run(inputs_dir, run_dir, **kw):\n"
        "    r = {'n': 300, 'label': 'INCONCLUSIVE', 'param': kw.get('p')}\n"
        "    (run_dir / 'results.json').write_text(json.dumps(r))\n"
        "    return r\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    (entorno / "spec.yaml").write_text(
        "id: EXP-T\nseries: [SPY]\nmodulo_calculo: mod_calculo_falso\nparametros: {p: 7}\n"
    )
    ds = FalsoDS(tmp_path / "log.jsonl", ["Resultado INCONCLUSIVE con 300 observaciones."])
    v = runner.correr(entorno, cliente=ds)
    assert v["estado"] == "APROBADO_PARA_REVISION", v
    assert v["modo"] == "calculo_fijo" and v["etiqueta"] == "INCONCLUSIVE"
    assert v["llamadas"] == 1  # solo el borrador

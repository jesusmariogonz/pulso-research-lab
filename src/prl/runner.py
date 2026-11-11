"""Orquestador de un experimento:

    python -m prl.runner experiments/EXP-000-smoke

Flujo (cada paso deja evidencia en runs/<exp>/<fecha>/):
  1. Exige que el PREREGISTRATION.md esté BLOQUEADO (Estado: LOCKED).
  2. DeepSeek escribe analysis.py a partir de spec.yaml.
  3. El código se revisa y corre aislado (sandbox.py) sobre inputs/ congelados.
  4. results.json se valida contra el esquema de la spec.
  5. DeepSeek redacta draft.md SOLO con cifras de results.json.
  6. verify.py (sin LLM) rechaza cualquier cifra que no esté respaldada.
  7. verdict.json resume todo (estado, llamadas, tokens, hash del manifiesto).

El LLM no decide etiquetas ni cambia la spec: eso es humano/código.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from prl.llm.deepseek import Budget, DeepSeek, PresupuestoAgotado
from prl.sandbox import CodigoNoPermitido, ejecutar
from prl.verify import verificar_borrador

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
MANIFIESTO = ROOT / "data" / "manifest.json"

SISTEMA = (
    "Eres un analista cuantitativo riguroso. Sigues METHODOLOGY.md del Research Lab: "
    "sin look-ahead, sin inventar cifras, resultados negativos igual de valiosos que positivos. "
    "Responde exactamente en el formato que se te pida."
)


class ExperimentoNoBloqueado(RuntimeError):
    pass


def exigir_bloqueado(exp_dir: Path) -> None:
    pre = (exp_dir / "PREREGISTRATION.md").read_text(encoding="utf-8")
    if not re.search(r"\*\*Estado:\*\*\s*`LOCKED`", pre):
        raise ExperimentoNoBloqueado(
            f"{exp_dir.name}: el pre-registro no está bloqueado (Estado: `LOCKED`). No se ejecuta nada."
        )


def extraer_bloque(texto: str, lenguaje: str) -> str:
    m = re.search(rf"```{lenguaje}\s*\n(.*?)```", texto, re.S)
    if not m:
        raise ValueError(f"la respuesta no trae un bloque ```{lenguaje}")
    return m.group(1)


def _prompt_codigo(spec: dict) -> str:
    esquema = json.dumps(spec["results_schema"], ensure_ascii=False, indent=2)
    series = ", ".join(spec["series"])
    return f"""Escribe un script de Python (pandas/numpy) que resuelva esta tarea y escriba `results.json`.

TAREA:
{spec['tarea'].strip()}

DATOS (solo lectura): archivos `inputs/<ID>.parquet` para: {series}.
Cada uno tiene índice de fechas `date` y columnas open, high, low, close, adj_close, volume
(las series FRED tienen una sola columna `value`). Usa `adj_close` para retornos.
Lee con `pd.read_parquet("inputs/SPY.parquet")`.

REGLAS DURAS:
- Solo imports de: pandas, numpy, scipy, statsmodels, math, json, pathlib, datetime, collections, itertools, statistics, typing, warnings.
- Prohibido: red, subprocess, os, sys, exec/eval, variables de entorno, escribir fuera de `results.json`.
- Sin look-ahead. No imprimas los datos.
- Escribe `results.json` (json.dump) con EXACTAMENTE estas claves (fracciones como decimales, p. ej. 0.153; fechas como "YYYY-MM-DD"):
{esquema}

Responde SOLO con un bloque ```python con el script completo."""


def _prompt_borrador(spec: dict, results: dict, rechazadas: list[str] | None) -> str:
    extra = ""
    if rechazadas:
        extra = (
            "\nTU BORRADOR ANTERIOR FUE RECHAZADO: estas cifras NO existen en results.json: "
            f"{', '.join(rechazadas)}. Elimínalas o sustitúyelas por cifras que SÍ estén en results.json. "
            "No calcules cifras nuevas (nada de sumas, restas, razones ni promedios propios).\n"
        )
    return f"""Redacta un borrador en español (Markdown) del resultado de este experimento.

SPEC:
{yaml.safe_dump(spec, allow_unicode=True)}

results.json:
{json.dumps(results, ensure_ascii=False, indent=2)}
{extra}
REGLAS DURAS:
- Usa ÚNICAMENTE cifras que aparezcan en results.json, tal cual (puedes expresar una fracción como porcentaje).
- NO calcules cifras nuevas ni cites datos de memoria (nada de "históricamente..." con números).
- No afirmes causalidad ni recomiendes invertir. Es descriptivo/experimental.
- Etiqueta el resultado como `EXPERIMENTAL`. Indica el período de datos con las fechas de results.json.
- Secciones: Resumen · Datos y período · Resultados · Limitaciones.
Responde SOLO con el Markdown."""


def _validar_esquema(results: dict, spec: dict) -> list[str]:
    return [k for k in spec["results_schema"] if k not in results]


def correr(exp_dir: Path, cliente: DeepSeek | None = None, ahora: datetime | None = None) -> dict:
    exp_dir = Path(exp_dir).resolve()
    exigir_bloqueado(exp_dir)
    spec = yaml.safe_load((exp_dir / "spec.yaml").read_text(encoding="utf-8"))
    spec_texto = (exp_dir / "spec.yaml").read_text(encoding="utf-8")

    ahora = ahora or datetime.now(timezone.utc)
    run_dir = ROOT / "runs" / exp_dir.name / ahora.strftime("%Y%m%dT%H%M%SZ")
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    shutil.copy(exp_dir / "spec.yaml", run_dir / "spec.yaml")
    for sid in spec["series"]:
        shutil.copy(RAW / f"{sid}.parquet", run_dir / "inputs" / f"{sid}.parquet")
    manifiesto_sha = hashlib.sha256(MANIFIESTO.read_bytes()).hexdigest() if MANIFIESTO.exists() else None

    ds = cliente or DeepSeek(bitacora=run_dir / "llm_log.jsonl", budget=Budget())
    veredicto: dict = {"experimento": exp_dir.name, "manifiesto_sha256": manifiesto_sha, "estado": "FALLIDO", "motivo": None}

    try:
        # --- 1. Código ---
        mensajes = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": _prompt_codigo(spec)}]
        results = None
        for intento in range(2):
            respuesta = ds.chat(mensajes, max_tokens=8000, etiqueta=f"codigo_intento_{intento + 1}")
            try:
                codigo = extraer_bloque(respuesta, "python")
                ejec = ejecutar(codigo, run_dir)
                falta = None
                if ejec.ok and (run_dir / "results.json").exists():
                    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
                    falta = _validar_esquema(results, spec)
                    if not falta:
                        break
                    error = f"results.json no trae las claves: {falta}"
                else:
                    error = ejec.stderr or "el script no produjo results.json"
            except (CodigoNoPermitido, ValueError) as e:
                error = str(e)
            results = None
            mensajes += [
                {"role": "assistant", "content": respuesta},
                {"role": "user", "content": f"Falló: {error}\nCorrige y responde de nuevo SOLO con el bloque ```python completo."},
            ]
        if results is None:
            veredicto["motivo"] = "no se obtuvo un results.json válido tras 2 intentos"
            return _cerrar(run_dir, veredicto, ds)

        # --- 2. Borrador con verificación de cifras ---
        rechazadas: list[str] | None = None
        for intento in range(2):
            md = ds.chat(
                [{"role": "system", "content": SISTEMA}, {"role": "user", "content": _prompt_borrador(spec, results, rechazadas)}],
                max_tokens=4000,
                etiqueta=f"borrador_intento_{intento + 1}",
            )
            (run_dir / "draft.md").write_text(md, encoding="utf-8")
            ver = verificar_borrador(md, results, spec_texto)
            veredicto["verificacion"] = {"ok": ver.ok, "no_respaldadas": ver.no_respaldadas, "cifras_revisadas": ver.revisadas}
            if ver.ok:
                veredicto["estado"] = "APROBADO_PARA_REVISION"
                break
            rechazadas = ver.no_respaldadas
        else:
            veredicto["motivo"] = "el borrador contiene cifras sin respaldo en results.json (rechazado)"
    except PresupuestoAgotado as e:
        veredicto["motivo"] = f"presupuesto agotado: {e}"
    except Exception as e:  # noqa: BLE001 - se deja constancia, nunca se esconde
        veredicto["motivo"] = f"{type(e).__name__}: {str(e)[:500]}"
    return _cerrar(run_dir, veredicto, ds)


def _cerrar(run_dir: Path, veredicto: dict, ds: DeepSeek) -> dict:
    veredicto["llamadas"] = ds.budget.llamadas
    veredicto["tokens_salida"] = ds.budget.tokens_salida
    veredicto["modelo"] = ds.modelo
    (run_dir / "verdict.json").write_text(json.dumps(veredicto, indent=2, ensure_ascii=False), encoding="utf-8")
    return veredicto


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("uso: python -m prl.runner experiments/EXP-XXX")
        return 2
    v = correr(Path(argv[0]))
    print(json.dumps(v, indent=2, ensure_ascii=False))
    return 0 if v["estado"] == "APROBADO_PARA_REVISION" else 1


if __name__ == "__main__":
    raise SystemExit(main())

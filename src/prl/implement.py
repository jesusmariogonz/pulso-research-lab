"""Ciclo de implementación guiado por tests (TDD automático con DeepSeek).

    python -m prl.implement features [--max-iter 6]
    python -m prl.implement macro_vintage [--max-iter 6]

Cada módulo conocido (ver registro `MODULOS`) declara su propio contrato
(IMPLEMENTATION_SPEC.md del experimento correspondiente), test y archivo
destino. El LLM recibe el contrato y los tests, escribe el módulo, se corren
los tests SIN secretos en el entorno, y si fallan se le devuelve la salida
de pytest. Se repite hasta pasar o agotar el tope (iteraciones y presupuesto
de tokens).

Lo que el LLM NO puede hacer: editar tests, spec o pre-registro (solo se
escribe el archivo del módulo) ni usar imports fuera de la lista blanca.
Pasar los tests NO sustituye la revisión humana del PR.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from prl.llm.deepseek import Budget, DeepSeek, PresupuestoAgotado
from prl.sandbox import CodigoNoPermitido, revisar_codigo

ROOT = Path(__file__).resolve().parents[2]
# El razonamiento del modelo cuenta contra max_tokens: con 12k las respuestas se
# truncaban antes de cerrar el bloque de código (backtest, 11-nov-2026).
TOKENS_POR_RESPUESTA = 32000

# Cada módulo declara su propio contrato (spec), archivo destino y test —
# así un experimento nuevo no necesita tocar la lógica del ciclo, solo
# agregar su entrada aquí. "spec" se manda completo al LLM igual que antes
# (son contratos cortos pensados para eso).
_EXP001 = ROOT / "experiments" / "EXP-001-emergency-model" / "IMPLEMENTATION_SPEC.md"
_EXP002 = ROOT / "experiments" / "EXP-002-growth-max-global" / "IMPLEMENTATION_SPEC.md"
MODULOS: dict[str, dict[str, Path]] = {
    nombre: {"spec": _EXP001, "destino": ROOT / "src" / "prl" / "emergency" / f"{nombre}.py", "test": ROOT / "tests" / "emergency" / f"test_{nombre}.py"}
    for nombre in ("features", "state_machine", "backtest", "grid", "inputs", "evaluation", "exp001", "daily", "robustness")
}
MODULOS["macro_vintage"] = {"spec": _EXP002, "destino": ROOT / "src" / "prl" / "data" / "macro_vintage.py", "test": ROOT / "tests" / "test_macro_vintage.py"}

SISTEMA = (
    "Eres un ingeniero cuantitativo senior. Implementas módulos de Python para que pasen un conjunto de "
    "tests y cumplan un contrato. No inventes requisitos: el contrato y los tests mandan. "
    "Código claro, tipado, sin look-ahead."
)


def _prompt(modulo: str, destino_rel: str, spec: str, tests: str, codigo_previo: str | None, salida_pytest: str | None) -> str:
    previo = ""
    if codigo_previo:
        previo = f"\nCÓDIGO ACTUAL de {destino_rel}:\n```python\n{codigo_previo}\n```\n"
    fallo = f"\nSALIDA DE PYTEST DEL INTENTO ANTERIOR (corrige lo que falla):\n{salida_pytest}\n" if salida_pytest else ""
    return f"""Implementa el módulo `{destino_rel}`.

CONTRATO (solo la sección de `{modulo}` y las reglas transversales te aplican):
{spec}

TESTS que deben pasar (no los modifiques):
```python
{tests}
```
{previo}{fallo}
Responde SOLO con un bloque ```python con el archivo completo (`from __future__ import annotations` permitido).
Imports permitidos: pandas, numpy, scipy, math, json, pathlib, itertools, datetime, typing, dataclasses, y `prl` (otros módulos del paquete)."""


def _correr_tests(test: Path) -> tuple[bool, str]:
    # Entorno vacío: el código generado no ve ningún secreto (ni la llave del LLM).
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider", str(test)],
        cwd=ROOT, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
        capture_output=True, text=True, timeout=900,
    )
    return p.returncode == 0, (p.stdout + p.stderr)[-3500:]


def implementar(modulo: str, max_iter: int = 6, cliente: DeepSeek | None = None, ahora: datetime | None = None) -> dict:
    if modulo not in MODULOS:
        raise ValueError(f"módulo desconocido: {modulo} (válidos: {sorted(MODULOS)})")
    entrada = MODULOS[modulo]
    destino, test, spec_path = entrada["destino"], entrada["test"], entrada["spec"]
    destino_rel = str(destino.relative_to(ROOT))
    spec, tests = spec_path.read_text(encoding="utf-8"), test.read_text(encoding="utf-8")

    ahora = ahora or datetime.now(timezone.utc)
    run_dir = ROOT / "runs" / "implement" / modulo / ahora.strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    ds = cliente or DeepSeek(bitacora=run_dir / "llm_log.jsonl", budget=Budget(max_llamadas=max_iter, max_tokens_salida_total=max_iter * TOKENS_POR_RESPUESTA))

    destino.parent.mkdir(parents=True, exist_ok=True)
    (destino.parent / "__init__.py").touch()
    veredicto = {"modulo": modulo, "destino": destino_rel, "estado": "FALLIDO", "iteraciones": 0, "motivo": None}
    codigo_previo = destino.read_text(encoding="utf-8") if destino.exists() else None
    salida = None
    try:
        for i in range(1, max_iter + 1):
            veredicto["iteraciones"] = i
            resp = ds.chat(
                [{"role": "system", "content": SISTEMA}, {"role": "user", "content": _prompt(modulo, destino_rel, spec, tests, codigo_previo, salida)}],
                max_tokens=TOKENS_POR_RESPUESTA, etiqueta=f"{modulo}_iter_{i}",
            )
            m = re.search(r"```python\s*\n(.*?)```", resp, re.S)
            if not m:
                if ds.ultimo_finish_reason == "length":
                    salida = "Tu respuesta se TRUNCÓ por longitud antes de cerrar el bloque de código. Piensa menos y responde directo con el archivo completo, sin explicaciones."
                else:
                    salida = "La respuesta no traía un bloque ```python."
                continue
            codigo = m.group(1)
            try:
                revisar_codigo(codigo, frozenset({"prl", "__future__"}))
            except CodigoNoPermitido as e:
                salida = f"Código rechazado por la revisión de seguridad: {e}"
                continue
            destino.write_text(codigo, encoding="utf-8")
            codigo_previo = codigo
            ok, salida = _correr_tests(test)
            (run_dir / "ultimo_pytest.txt").write_text(salida, encoding="utf-8")
            if ok:
                veredicto["estado"] = "TESTS_PASAN"
                break
        else:
            veredicto["motivo"] = f"los tests no pasaron tras {max_iter} iteraciones"
    except PresupuestoAgotado as e:
        veredicto["motivo"] = f"presupuesto agotado: {e}"
    except Exception as e:  # noqa: BLE001
        veredicto["motivo"] = f"{type(e).__name__}: {str(e)[:500]}"
    veredicto.update(llamadas=ds.budget.llamadas, tokens_salida=ds.budget.tokens_salida, modelo=ds.modelo)
    (run_dir / "verdict.json").write_text(json.dumps(veredicto, indent=2, ensure_ascii=False), encoding="utf-8")
    return veredicto


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("uso: python -m prl.implement <features|state_machine|backtest> [--max-iter N]")
        return 2
    max_iter = int(argv[argv.index("--max-iter") + 1]) if "--max-iter" in argv else 6
    v = implementar(argv[0], max_iter=max_iter)
    print(json.dumps(v, indent=2, ensure_ascii=False))
    return 0 if v["estado"] == "TESTS_PASAN" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Ejecución aislada del código generado por el LLM.

Capas (defensa en profundidad — ninguna sola es la garantía):
  1. Revisión estática (AST): lista blanca de imports y nombres prohibidos.
  2. Proceso hijo con entorno VACÍO (sin DEEPSEEK_API_KEY ni ningún secreto)
     y directorio de trabajo = el de la corrida.
  3. Sin red: si el sistema lo permite se usa `unshare -rn`; si no, la
     revisión estática ya prohíbe cualquier módulo de red.
  4. Tiempo máximo.

El código generado SOLO puede leer `inputs/` y escribir `results.json`.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

IMPORTS_PERMITIDOS = {
    "pandas", "numpy", "scipy", "statsmodels", "math", "json", "pathlib",
    "datetime", "collections", "itertools", "functools", "statistics",
    "typing", "dataclasses", "warnings", "arch",
}
NOMBRES_PROHIBIDOS = {"exec", "eval", "compile", "__import__", "input", "breakpoint", "globals", "locals", "getattr", "setattr", "delattr"}
ATRIBUTOS_PROHIBIDOS = {"system", "popen", "remove", "unlink", "rmdir", "rmtree", "rename", "environ", "getenv"}


class CodigoNoPermitido(ValueError):
    pass


def revisar_codigo(codigo: str) -> None:
    try:
        arbol = ast.parse(codigo)
    except SyntaxError as e:
        raise CodigoNoPermitido(f"sintaxis inválida: {e}") from e
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                raiz = a.name.split(".")[0]
                if raiz not in IMPORTS_PERMITIDOS:
                    raise CodigoNoPermitido(f"import no permitido: {a.name}")
        elif isinstance(nodo, ast.ImportFrom):
            raiz = (nodo.module or "").split(".")[0]
            if raiz not in IMPORTS_PERMITIDOS:
                raise CodigoNoPermitido(f"import no permitido: {nodo.module}")
        elif isinstance(nodo, ast.Name) and nodo.id in NOMBRES_PROHIBIDOS:
            raise CodigoNoPermitido(f"nombre prohibido: {nodo.id}")
        elif isinstance(nodo, ast.Attribute) and nodo.attr in ATRIBUTOS_PROHIBIDOS:
            raise CodigoNoPermitido(f"atributo prohibido: .{nodo.attr}")
        elif isinstance(nodo, ast.Attribute) and nodo.attr.startswith("__"):
            raise CodigoNoPermitido(f"atributo dunder prohibido: .{nodo.attr}")


@dataclass
class Ejecucion:
    ok: bool
    stdout: str
    stderr: str
    codigo_salida: int


def _prefijo_sin_red() -> list[str]:
    if shutil.which("unshare"):
        prueba = subprocess.run(["unshare", "-rn", "true"], capture_output=True)
        if prueba.returncode == 0:
            return ["unshare", "-rn"]
    return []


def ejecutar(codigo: str, dir_corrida: Path, timeout_s: int = 600) -> Ejecucion:
    revisar_codigo(codigo)
    script = dir_corrida / "analysis.py"
    script.write_text(codigo, encoding="utf-8")
    comando = _prefijo_sin_red() + [sys.executable, "-I", str(script)]
    try:
        p = subprocess.run(
            comando, cwd=dir_corrida, env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return Ejecucion(False, "", f"tiempo excedido ({timeout_s}s)", -1)
    return Ejecucion(p.returncode == 0, p.stdout[-4000:], p.stderr[-4000:], p.returncode)

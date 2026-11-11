"""Verificador de cifras (SIN LLM). Regla: toda cifra que aparezca en el
borrador debe existir en results.json (con tolerancia de redondeo) o ser
una cifra "estructural" permitida (años, fechas citadas de results/spec,
enteros pequeños de conteo). Si no, el borrador se rechaza.

Esto es lo que impide que un LLM invente o "recuerde" una estadística.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FECHA = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUM = re.compile(r"(?<![\w.])[-−+]?\d[\d,]*(?:\.\d+)?%?")


def _hojas_numericas(obj) -> list[float]:
    out: list[float] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out += _hojas_numericas(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += _hojas_numericas(v)
    elif isinstance(obj, str):
        for m in _NUM.finditer(obj):
            try:
                out.append(float(m.group().replace(",", "").replace("%", "").replace("−", "-")))
            except ValueError:
                pass
    return out


def _decimales(token: str) -> int:
    t = token.replace(",", "").replace("%", "")
    return len(t.split(".")[1]) if "." in t else 0


def _a_float(token: str) -> float:
    return float(token.replace(",", "").replace("%", "").replace("−", "-").lstrip("+"))


@dataclass
class Resultado:
    ok: bool
    no_respaldadas: list[str]
    revisadas: int


def verificar_borrador(texto: str, results: dict, spec_texto: str = "") -> Resultado:
    hojas = _hojas_numericas(results)
    # También valen las magnitudes absolutas y los fracciones expresadas en %.
    candidatos = set()
    for h in hojas:
        candidatos.update({h, abs(h), h * 100, abs(h) * 100})

    texto_fechas_validas = json.dumps(results, ensure_ascii=False) + " " + spec_texto
    sin_fechas = texto
    for f in _FECHA.findall(texto):
        if f in texto_fechas_validas:
            sin_fechas = sin_fechas.replace(f, " ")

    # Se ignoran encabezados con identificadores tipo EXP-001 / H1 / H0.
    sin_fechas = re.sub(r"\b(?:EXP|H|v|V)-?\d+\b", " ", sin_fechas)

    no_resp: list[str] = []
    revisadas = 0
    for m in _NUM.finditer(sin_fechas):
        tok = m.group()
        try:
            val = _a_float(tok)
        except ValueError:
            continue
        revisadas += 1
        # Permitidos estructurales: años y enteros pequeños (conteos como "3 episodios").
        if re.fullmatch(r"(19|20)\d{2}", tok.lstrip("+-−")):
            continue
        if re.fullmatch(r"\d", tok):
            continue
        tol = 0.5 * 10 ** (-_decimales(tok)) + 1e-9
        if tok.endswith("%"):
            # un % puede venir de una fracción (0.153 -> 15.3%) o ya en %.
            if any(abs(val - c) <= tol for c in candidatos):
                continue
        elif any(abs(val - c) <= tol for c in candidatos):
            continue
        no_resp.append(tok)

    return Resultado(ok=not no_resp, no_respaldadas=sorted(set(no_resp)), revisadas=revisadas)

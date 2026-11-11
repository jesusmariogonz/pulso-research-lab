"""Cliente mínimo de DeepSeek (API compatible con OpenAI) con:

  * tope duro de llamadas y de tokens de salida POR CORRIDA (Budget);
  * bitácora completa de cada llamada (llm_log.jsonl) para auditar;
  * la llave se lee SOLO de la variable de entorno DEEPSEEK_API_KEY y
    nunca se escribe en la bitácora, en errores ni en archivos.

El LLM NO calcula ni recuerda estadísticas: ver METHODOLOGY.md §5.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODELO_POR_DEFECTO = os.environ.get("PRL_MODEL", "deepseek-flash")


class PresupuestoAgotado(RuntimeError):
    pass


@dataclass
class Budget:
    max_llamadas: int = int(os.environ.get("PRL_MAX_CALLS", "6"))
    max_tokens_salida_total: int = int(os.environ.get("PRL_MAX_OUTPUT_TOKENS", "60000"))
    llamadas: int = 0
    tokens_salida: int = 0

    def antes_de_llamar(self, max_tokens: int) -> None:
        if self.llamadas >= self.max_llamadas:
            raise PresupuestoAgotado(f"se alcanzó el tope de {self.max_llamadas} llamadas por corrida")
        if self.tokens_salida + max_tokens > self.max_tokens_salida_total:
            raise PresupuestoAgotado("la llamada podría exceder el tope de tokens de salida por corrida")

    def despues_de_llamar(self, tokens_salida: int) -> None:
        self.llamadas += 1
        self.tokens_salida += tokens_salida


@dataclass
class DeepSeek:
    bitacora: Path
    budget: Budget = field(default_factory=Budget)
    modelo: str = MODELO_POR_DEFECTO

    def chat(self, mensajes: list[dict], *, max_tokens: int = 8000, temperature: float = 0.0, etiqueta: str = "") -> str:
        llave = os.environ.get("DEEPSEEK_API_KEY")
        if not llave:
            raise RuntimeError("falta DEEPSEEK_API_KEY en el entorno")
        self.budget.antes_de_llamar(max_tokens)

        cuerpo = {"model": self.modelo, "messages": mensajes, "max_tokens": max_tokens, "temperature": temperature}
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {llave}", "Content-Type": "application/json"},
            json=cuerpo,
            timeout=600,
        )
        if r.status_code != 200:
            # Se registra el cuerpo del error (no contiene la llave) y se falla.
            self._registrar({"etiqueta": etiqueta, "error_http": r.status_code, "cuerpo": r.text[:2000]})
            raise RuntimeError(f"DeepSeek respondió HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
        texto = data["choices"][0]["message"].get("content") or ""
        uso = data.get("usage", {})
        self.budget.despues_de_llamar(int(uso.get("completion_tokens", 0)))
        self._registrar(
            {
                "etiqueta": etiqueta,
                "modelo": data.get("model", self.modelo),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "prompt_sha256": hashlib.sha256(json.dumps(mensajes, ensure_ascii=False).encode()).hexdigest(),
                "mensajes": mensajes,
                "respuesta": texto,
                "uso": uso,
                "segundos": round(time.time() - t0, 2),
            }
        )
        return texto

    def _registrar(self, registro: dict) -> None:
        self.bitacora.parent.mkdir(parents=True, exist_ok=True)
        with self.bitacora.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")

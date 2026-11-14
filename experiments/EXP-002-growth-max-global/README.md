# EXP-002 · Growth-Max Global — espacio del experimento

Índice único de todo lo que existe sobre este experimento. **Estado: REJECTED** (etiqueta calculada por código con los criterios pre-registrados).
Reporte público (pendiente de publicar en el sitio): https://jgonzalez.app/pulso-mercado/research/exp-002-growth-max-global

## Resultado en una línea
La variante ganadora (seleccionada solo con discovery 2006–2015 y validation 2016–2019, sin tocar el locked test) **no superó al benchmark 60/40 fuera de muestra** (2020–2026): en el nivel Growth50 solo le ganó en el 8.4% de las réplicas bootstrap, muy por debajo del 80% exigido para `VALIDATED`. Deflated Sharpe ≈ 0 tras corregir por los 17 280 intentos.

## Documentos (en este directorio)
| Archivo | Qué es |
|---|---|
| `PREREGISTRATION.md` | Pre-registro (v1.5, LOCKED antes de ver datos reales): universo de 65 instrumentos, señales, construcción de portafolio, grilla de 17 280 variantes, split discovery/validation/locked test, criterios de etiqueta. |
| `IMPLEMENTATION_SPEC.md` | Contrato de implementación por módulo (lo que DeepSeek debe cumplir). |
| `DATA_INFRA_MACRO_VINTAGE.md` | Diseño de la infraestructura de datos macro point-in-time (ALFRED) que sostiene el régimen macro del experimento. |
| `results_published.json` | Métricas publicadas: copia exacta de `runs/EXP-002-growth-max-global/20261113T202608Z/results.json`. |
| `LOG.md` | Bitácora cronológica: decisiones, errores, correcciones. |

## Código y pruebas
- Módulos: `src/prl/data/macro_vintage.py`, `src/prl/growth_max/{signals,portfolio,backtest,grid,evaluation,exp002}.py`. Escritos por DeepSeek con ciclo TDD (`implement-module`); los tests y contratos los escribió Claude. El orquestador `exp002.run` es código determinístico: no llama a ningún LLM al ejecutarse.
- Tests: `tests/test_macro_vintage.py`, `tests/growth_max/`.
- Evidencia de la corrida real: `runs/EXP-002-growth-max-global/20261113T202608Z/` (datos congelados reales, `n_boot=10000`, semilla 0).
- Datos congelados: Release `data-2026-11-12` (ver `data/manifest.json`).

## Flujo (metodología)
Pre-registro bloqueado → datos congelados con SHA-256 → cómputo con código fijo (sin LLM en la corrida) → etiqueta determinista (VALIDATED/REJECTED/INCONCLUSIVE, nunca decidida por un LLM). Un resultado negativo se documenta igual que uno positivo.

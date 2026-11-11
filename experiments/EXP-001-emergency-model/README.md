# EXP-001 · Modelo de emergencia multifactor — espacio del experimento

Índice único de todo lo que existe sobre este experimento. **Estado: INCONCLUSIVE** (etiqueta calculada por código con los criterios pre-registrados).
Reporte público: https://jgonzalez.app/pulso-mercado/research/exp-001-modelo-de-emergencia

## Documentos (en este directorio)
| Archivo | Qué es |
|---|---|
| `PREREGISTRATION.md` | Pre-registro (v1.1, LOCKED antes de ver datos reales): hipótesis, diseño, criterios, grilla de 162 variantes. |
| `IMPLEMENTATION_SPEC.md` | Contrato de implementación por módulo (lo que DeepSeek debe cumplir). |
| `spec.yaml` | Especificación ejecutable del experimento. |
| `appendix.py` / `appendix.json` | Análisis exploratorio post-hoc determinista (semilla 0): sensibilidad, bootstrap, placebo, DSR paso a paso, entradas y salidas. Reproduce las métricas publicadas con `assert`. |
| `results_published.json` | Métricas publicadas (referencia del assert de reproducción). |
| `LOG.md` | Bitácora cronológica: decisiones, errores, correcciones y pruebas pendientes. |
| `REFERENCES.md` | Literatura relacionada (cada cita con estado de verificación). |

## Código y pruebas
- Módulos: `src/prl/emergency/{features,state_machine,backtest,grid,inputs,evaluation,exp001,daily,robustness}.py`. Escritos por DeepSeek con ciclo TDD (`implement-module`); los tests y contratos los escribió Claude. Código generado corre sin secretos y se revisa por humano/Claude.
- Tests: `tests/emergency/`.
- Evidencia de cada corrida: `runs/` (`runs/EXP-001-emergency-model/<fecha>/` y `runs/implement/<módulo>/<fecha>/`).
- Datos congelados: Release `data-2026-11-11` (hash de manifiesto `4cdc4e18…`, ver `data/manifest.json`).

## Flujo (metodología)
Pre-registro → datos congelados con SHA-256 → cómputo con código fijo → LLM solo redacta texto → verificador automático de cifras → etiqueta determinista. Los análisis exploratorios se marcan "EXPLORATORIO · post-hoc" y **no cambian la etiqueta**.

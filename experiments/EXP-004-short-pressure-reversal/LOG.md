# LOG — EXP-004 Short Pressure Reversal

## 2026-11-20 — Pre-registro

El usuario propuso el experimento completo (13 secciones: factores de
short pressure/price exhaustion, búsqueda automática de buckets
candidatos, 6 baselines, validación walk-forward, robustez, criterios
de etiqueta). Antes de diseñar nada se investigó viabilidad real de
datos:

* **Short volume diario (FINRA Reg SHO)**: confirmado accesible por
  HTTP directo, sin auth, desde 2019-01-02 (403 antes de esa fecha).
* **Short interest bi-mensual (FINRA)**: confirmado accesible por HTTP
  directo, sin auth, con `days_to_cover` y `change_pct` ya calculados
  por FINRA (no hay que derivarlos). Limitación real encontrada: no
  hay float histórico gratis point-in-time — se sustituye "short
  interest/float" por las 3 métricas que FINRA sí da directo.
* Se verificó (no se asumió) que las tablas de S&P 400/600 de
  Wikipedia son accesibles y parseables (6,062 celdas `<td>` detectadas
  en la de S&P 400) para construir el universo S&P 1500 sin tener que
  pelear con la protección anti-bot de iShares (intento fallido,
  documentado: la descarga directa de holdings de IWB devolvió HTML,
  no CSV).

Con la viabilidad confirmada, se preguntó al usuario dos decisiones
reales de alcance antes de bloquear nada: amplitud del universo
(eligió S&P 1500/Russell 1000 sobre S&P 500 solo o todo FINRA) y si
arrancar ya con el pre-registro aceptando que esto toma varias
sesiones, como EXP-002 (eligió arrancar ya).

Se escribió y bloqueó `PREREGISTRATION.md` v1: universo S&P 1500
actual, 3 familias de features normalizadas por percentil
cross-sectional, grilla cerrada de 140 variantes (5 umbrales de short
pressure × 4 de price exhaustion × 7 configuraciones de confirmación),
split discovery 2019-2022/validation 2023-2024H1/locked test
2024H2-2026, 6 baselines, criterios VALIDATED/REJECTED/INCONCLUSIVE
fijados antes de correr nada.

**Siguiente paso**: fase de infraestructura de datos (precios de
~1,500 acciones + short volume/interest de FINRA) — no se ha corrido
nada todavía, no se ha tocado ningún dato real.

# EXP-003 · Validación estadística y robustez del motor de trading — espacio del experimento

Índice único de todo lo que existe sobre este experimento.
**Estado: no es una sola etiqueta** (ver abajo por qué) — los 3 buckets
de producción quedan sin evidencia validada de ventaja real en las 2
pruebas diseñadas para medirlo directamente (DSR, placebo); ninguno
muestra fragilidad extrema; `riesgo_alto` confirma además sesgo de
supervivencia material. Detalle completo en `RESULTADOS.md`.

**Nota de alcance:** a diferencia de EXP-001/EXP-002, este experimento
no valida nada del catálogo/pipeline de `pulso-research-lab` — valida
el motor de trading algorítmico de un repositorio distinto
(`jesusmariogonz/algo_trading_platform`). Ver `PREREGISTRATION.md`
para el detalle completo de por qué vive catalogado aquí sin usar la
infraestructura propia de este repo (DeepSeek-TDD, `data/manifest.json`).

## Por qué no hay una sola etiqueta VALIDATED/REJECTED/INCONCLUSIVE

El pre-registro (`PREREGISTRATION.md`) lo fijó explícitamente desde el
inicio: son 3 estrategias de producción × 7 capas de validación
independientes, cada una con su propio criterio. Forzar un semáforo
único sería promediar preguntas que no son comparables (¿depende de un
sector? ¿sobrevive ejecución realista? ¿hay ventaja real sobre el
azar?). La tabla completa, capa por capa y bucket por bucket, está en
`RESULTADOS.md`.

## Documentos (en este directorio)

| Archivo | Qué es |
|---|---|
| `PREREGISTRATION.md` | Pre-registro (LOCKED 2026-11-18 en el repo de origen antes de ver resultados): alcance, hipótesis, las 7 capas y su criterio, registro de cambios (incluida la corrección del 2026-11-19). |
| `RESULTADOS.md` | Resultado completo de las 7 capas, capa por capa y bucket por bucket, con los números reales de cada corrida y la síntesis final. |
| `LOG.md` | Bitácora cronológica: decisiones, el bug de harness encontrado y corregido, correcciones. |

## Código y pruebas

- Toda la ejecución real vive en `jesusmariogonz/algo_trading_platform`, directorio `research/exp-003-validacion-motor-produccion/` (código Python de cada capa + resultados JSON, versionados desde el día 1 — nunca gitignored, ver ADR 0041 de ese repo). Escrito directamente (no vía DeepSeek: ese repo no usa esa infraestructura), con el mismo estándar de autoverificación contra resultados ya publicados antes de confiar en cualquier cálculo nuevo que se usó en el appendix de EXP-002 de este laboratorio.
- Suite de ese repositorio: 254/254 tests, sin cambios de producción en ningún momento de las 7 capas ni de la corrección.
- Commits de referencia en `main` de ese repo: `8e147ba` (pre-registro) .. `c971560` (síntesis final).

## Flujo (metodología)

Pre-registro bloqueado (7 capas, criterio fijado antes de correr nada)
→ ejecución con código fijo, autoverificado contra resultados conocidos
antes de cada cómputo nuevo → corrección documentada de un bug de
implementación real (filtro de sizing faltante en el harness
compartido), sin borrar los números anteriores, solo marcándolos como
superados → síntesis final en prosa, nunca un promedio ni una
votación de las 7 capas. Un resultado negativo (y aquí, mixto) se
documenta con el mismo detalle que uno positivo.

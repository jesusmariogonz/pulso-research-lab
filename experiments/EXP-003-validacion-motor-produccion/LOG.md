# LOG — EXP-003 Validación estadística y robustez del motor de trading

## 2026-11-18 — Pre-registro

Se escribió y bloqueó `PREREGISTRATION.md` en el repositorio de
origen (`algo_trading_platform`): alcance (configuración exacta de
producción de los 3 buckets), 7 capas con criterio
VALIDATED/REJECTED/INCONCLUSIVE fijado antes de correr nada, orden de
ejecución (capas que reusan infraestructura ya existente primero).
Motivado por la preocupación explícita del usuario sobre si el motor
en vivo de IBKR opera una configuración buena, y por la decisión
previa (de una sesión anterior) de que la validación debe poder fallar
honestamente — no se diseñó para garantizar un resultado positivo.

## 2026-11-18/19 — Capas 1, 6, 7, 4, 5 (sin corrección todavía)

Corridas en orden: Capa 1 (walk-forward rolling, los 3 buckets
INCONCLUSIVE por pocas operaciones por ventana), Capa 7 (ejecución
realista, `largo_plazo` salió REJECTED — el bucket con mayor capital
asignado revertía su resultado histórico completo bajo un supuesto de
fill más realista), Capa 6 (perturbación de parámetros, los 3
VALIDATED, sin firma de sobreajuste), Capa 4 (placebo con potencia
verificada — diseñado explícitamente para no repetir el error de
EXP-002 de este laboratorio, donde un placebo de rotación circular
tuvo potencia estadística cero; aquí se verificó varianza no-trivial
entre réplicas antes de interpretar cualquier percentil — los 3
buckets salieron REJECTED, el Sharpe real no se distinguió de un
reordenamiento al azar de los mismos bloques mensuales), Capa 5
(leave-one-group-out, los 3 VALIDATED, sin dependencia de un sector
específico).

## 2026-11-19 — Capa 3 (DSR+PBO) y hallazgo crítico de harness

Al catalogar 47 configuraciones materialmente distintas ya probadas en
la historia documentada del proyecto (leyendo 43 ADR del repositorio
de origen) y calcular el Deflated Sharpe Ratio sobre esa cuenta, se
encontró que el harness compartido de las Capas 1/4/5/6/7 nunca
implementó un filtro de cross-sectional momentum que SÍ está activo en
producción real para `largo_plazo` desde un ADR anterior de ese mismo
repositorio (tanto en el motor simulado como en el motor en vivo de
IBKR) — confirmado leyendo el código fuente actual. Consecuencia: 5 de
las 7 capas habían estado probando una versión vieja de la estrategia
de `largo_plazo` (Sharpe 0.78), no la real de producción (Sharpe 2.25
según su propio walk-forward de aprobación). `mediano_plazo`/
`riesgo_alto` no se vieron afectados (el filtro es exclusivo de
`largo_plazo`). La Capa 3 reportó el DSR de `largo_plazo` con AMBOS
números en vez de elegir uno, dejando la contradicción explícita en
vez de ocultarla.

**Decisión:** corregir el harness y re-correr las 5 capas afectadas
SOLO para `largo_plazo`, antes de tocar la Capa 2 (la última
pendiente) — misma disciplina de no construir sobre un número que no
corresponde a la configuración real ya aplicada en este laboratorio.

## 2026-11-19 — Corrección: harness + re-corrida de largo_plazo

Harness corregido con el filtro real. Autoverificación: el full-period
con el filtro activo da Sharpe 0.92 (no reproduce exacto el 2.25 del
walk-forward OOS original de ese ADR — distinto esquema de ventanas,
documentado honestamente, no forzado). Re-corridas las 5 capas:

- Capa 1: sin cambio (INCONCLUSIVE, mismo problema de pocas
  operaciones, independiente del filtro).
- Capa 4: sin cambio real (REJECTED, percentil 27.67→48.33 — ambos muy
  por debajo del umbral de 80). Durante esta re-corrida se encontró y
  corrigió un bug propio: la primera fórmula del percentil
  (`np.mean([1 for s in sharpes if s < real])`) siempre daba 1.0, un
  error de cálculo, no de metodología — documentado con transparencia
  y vuelto a correr para no dejar un número sabidamente mal en el
  registro.
- Capa 5: sin cambio (VALIDATED).
- Capa 6: sin cambio (VALIDATED).
- **Capa 7: cambio real, REJECTED → VALIDATED** — con el filtro activo,
  el escenario pesimista de ejecución se queda positivo (+6.37% vs.
  −9.28% sin el filtro). El hallazgo original de fragilidad de
  `largo_plazo` era un artefacto de probar la configuración
  equivocada.

Los números "antes" de cada capa se dejaron visibles con una nota de
corrección, nunca borrados — mismo estándar de este laboratorio.

## 2026-11-19/20 — Capa 2 (última) y síntesis final

Capa 2 (sesgo de supervivencia): sin proveedor de datos point-in-time
disponible gratis/rápido, se construyó un universo neutral con una
muestra estratificada de 168 símbolos del S&P 500 actual — midiendo
sesgo de SELECCIÓN MANUAL con hindsight, no supervivencia completa
(limitación documentada explícitamente). `mediano_plazo` VALIDATED
(diferencia 0.9%); `riesgo_alto` **REJECTED** (diferencia 55.9% —
confirma cuantitativamente, por primera vez, una advertencia de
sesgo de supervivencia que el `roadmap.md` de ese repositorio dejó sin
resolver desde su fase inicial); `largo_plazo` INCONCLUSIVE por diseño
(universo de ETFs de clase de activo, el tipo de sesgo medido no
aplica igual).

Con las 7 capas visibles, se escribió la síntesis final
(`RESULTADOS.md` de este directorio, espejo de
`SINTESIS-FINAL.md` en el repositorio de origen): ningún bucket
demuestra, en las 2 pruebas diseñadas para medirlo directamente (DSR,
placebo), una ventaja distinguible del azar; ninguno muestra
fragilidad extrema; `riesgo_alto` se agrava con sesgo de supervivencia
confirmado. No se propuso ninguna configuración alternativa — fuera
del alcance del pre-registro, por diseño.

**Etiqueta:** no aplica una sola (ver `README.md` sobre por qué) —
resultado mixto documentado capa por capa y bucket por bucket en
`RESULTADOS.md`, calculado por código en cada capa, nunca decidido por
el LLM.

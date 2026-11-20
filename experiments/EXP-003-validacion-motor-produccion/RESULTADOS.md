# EXP-003 — Resultados completos

Las 7 capas pre-registradas en `PREREGISTRATION.md`, ejecutadas en
`jesusmariogonz/algo_trading_platform` (commits `3812be6`..`c971560`
en `main`, carpeta `research/exp-003-validacion-motor-produccion/` de
ese repositorio — código y JSON de cada corrida ahí, versionados). Esta
página resume con el mismo nivel de detalle que exige este laboratorio;
para la corrida exacta, el código fuente de cada capa y el catálogo
auditable de variantes, ver esa carpeta.

## Tabla completa

| Capa | largo_plazo | mediano_plazo | riesgo_alto |
|---|---|---|---|
| 1 — Walk-forward rolling | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE |
| 2 — Sesgo de supervivencia | INCONCLUSIVE (no aplica) | VALIDATED | **REJECTED** |
| 3 — DSR + PBO (47 intentos históricos) | AMBIGUO, sin resolver | **REJECTED** | **REJECTED** |
| 4 — Placebo (potencia verificada) | **REJECTED** | **REJECTED** | **REJECTED** |
| 5 — Leave-one-group-out | VALIDATED | VALIDATED | VALIDATED |
| 6 — Perturbación de parámetros | VALIDATED | VALIDATED | VALIDATED |
| 7 — Ejecución realista | VALIDATED | VALIDATED | VALIDATED |

`largo_plazo` en las Capas 1/4/6/7 usa la configuración corregida (con
el filtro de cross-sectional momentum real de producción) desde el
2026-11-19 — ver "Corrección" en cada capa abajo. La Capa 3 nunca se
re-corrió con el Sharpe corregido del período completo (0.92); su
ambigüedad en `largo_plazo` queda abierta tal cual.

## Capa 1 — Walk-forward rolling

Harness rolling (5 ventanas, 12m train/6m test, paso 4 meses), SIN
ningún filtro de sizing adicional, sobre la configuración de
producción. **Los 3 buckets: INCONCLUSIVE** — `largo_plazo` y
`riesgo_alto` por ventanas con <10 operaciones (criterio pre-fijado),
`mediano_plazo` por quedar exactamente en 3/5 ventanas positivas
(también INCONCLUSIVE por criterio, ni VALIDATED ni REJECTED).
`riesgo_alto` mostró una ventana de +56% seguida inmediatamente de
−24.65% — ejemplo directo de por qué una muestra tan chica no permite
distinguir una ventaja real de una racha.

Corrección (2026-11-19): con el filtro cross-sectional real de
`largo_plazo` (ADR 0034 del repo de origen) incluido en el harness, el
label de `largo_plazo` se mantiene **INCONCLUSIVE** (mismo problema de
pocas operaciones por ventana, independiente del filtro).

## Capa 2 — Sesgo de supervivencia

Comparación contra un universo neutral: muestra estratificada de 168
símbolos del S&P 500 actual (fuente pública), corrida con la MISMA
estrategia de producción.

| Bucket | Universo curado (retorno anual) | Universo neutral (retorno anual) | Diferencia | Label |
|---|---|---|---|---|
| mediano_plazo | 30.92% (74 símbolos) | 30.65% (165 símbolos) | 0.9% | **VALIDATED** |
| riesgo_alto | 26.21% (44 símbolos) | 11.57% (165 símbolos) | **55.9%** | **REJECTED** |
| largo_plazo | — | — | No aplica (universo de ETFs de clase de activo, no acciones elegidas a mano) | INCONCLUSIVE, por diseño |

`riesgo_alto` confirma cuantitativamente, por primera vez, una
advertencia que el `roadmap.md` de ese repositorio dejó abierta desde
su Fase 0: el universo curado (PLTR, SMCI, COIN, RIVN, SOFI...) incluye
nombres elegidos con el diario de que ya ganaron el rally de IA/growth
2023-2025. Nota metodológica honesta: el universo neutral (S&P 500
large-cap) es estructuralmente más estable que el universo real de
`riesgo_alto` (small/mid-cap de alta volatilidad) — la diferencia de
55.9% es, si algo, un **piso** del sesgo real, no un techo.

## Capa 3 — Deflated Sharpe Ratio + PBO sobre el espacio de búsqueda histórico

Catálogo auditable de **47 configuraciones materialmente distintas**
ya probadas en la historia documentada del proyecto (leídos los 43 ADR
del repositorio de origen, agrupadas en 12 grupos por ADR de origen,
sin contar la misma variante dos veces). De esas 47, **18 tienen un
Sharpe explícitamente reportado** — usado para estimar empíricamente
la dispersión de Sharpe entre intentos (σ_SR = 0.7101) con la fórmula
de Bailey & López de Prado (misma derivación del appendix de EXP-002:
constante de Euler-Mascheroni, teoría de valores extremos para el
máximo esperado de N trials).

Con N=47 y σ_SR=0.71, el techo de Sharpe esperable por puro azar es
≈1.60.

| Bucket | Sharpe usado | DSR | PBO (sobre 3 variantes re-simulables) | Label |
|---|---|---|---|---|
| largo_plazo (sin filtro ADR 0034) | 0.78 | 0.0000 | 0.00 | REJECTED |
| **largo_plazo (con filtro ADR 0034, Sharpe walk-forward OOS publicado en ese ADR)** | **2.25** | **1.0000** | 0.00 | **VALIDATED** |
| mediano_plazo | 1.39 | 0.0001 | 0.00 | **REJECTED** |
| riesgo_alto | 0.92 (recalculado con el Sharpe corregido) | 0.0000 | 0.15 | **REJECTED** |

**`mediano_plazo` y `riesgo_alto` quedan REJECTED sin ambigüedad bajo
cualquier lectura**: con 47 intentos ya documentados en la historia de
este proyecto, su Sharpe observado no se distingue de la mejor racha
que ese volumen de búsqueda produciría sin ninguna habilidad real.
`largo_plazo` queda en dos labels contradictorios según qué cifra de
Sharpe se use (0.78 del harness reconstruido vs. 2.25 del walk-forward
original publicado en el ADR que aprobó el filtro) — esto no se
resolvió: el harness corregido nunca se volvió a pasar por esta capa
con su propio Sharpe de período completo (0.92), que habría sido la
comparación correcta y consistente con el resto de EXP-003. Importante
no sobre-leer el PBO: solo cubre 3 de las 47 variantes del catálogo
(las únicas con datos ventana-por-ventana re-simulables disponibles),
no contradice el DSR sobre las 47.

## Capa 4 — Placebo con potencia verificada

Lección directa de EXP-002 incorporada al diseño: un placebo de
rotación circular sobre una estadística invariante al orden (como el
CAGR vía producto usado ahí) puede tener potencia estadística CERO sin
que sea obvio de entrada. Aquí se verificó la potencia ANTES de
interpretar cualquier percentil.

Método: moving block bootstrap conjunto, bloques de 21 sesiones
(~1 mes), la MISMA secuencia de bloques reordenados aplicada a todos
los símbolos del universo de un bucket y a SPY en una réplica dada
(preserva la estructura cross-seccional). Desde los retornos crudos se
reconstruye un panel OHLCV sintético, se recalculan TODOS los
indicadores con las funciones reales de producción, y se corre la
estrategia + motor de simulación reales sobre cada réplica — 300
réplicas por bucket (no 1,000; costo computacional documentado: hasta
8s/réplica en el universo más grande, >2h para 1,000 réplicas en ese
bucket).

| Bucket | Sharpe real | Media placebo (std) | Percentil | Label |
|---|---|---|---|---|
| largo_plazo (con filtro ADR 0034, corregido) | 0.92 | 0.921 (0.476) | **48.33** | **REJECTED** |
| mediano_plazo | 1.39 | — | **49.33** | **REJECTED** |
| riesgo_alto | 0.91 | — | **55.33** | **REJECTED** |

Potencia confirmada en los 3 (desviación estándar entre réplicas
~0.45-0.50, del mismo orden que el propio Sharpe — no el caso
degenerado de EXP-002). **Los 3 buckets caen prácticamente en la
mediana de la distribución placebo**: si los mismos movimientos reales
de ~1 mes hubieran ocurrido en otro orden, la estrategia de producción
no habría rendido distinto en promedio. Durante la corrección del
2026-11-19 se encontró y corrigió un bug propio en el primer cálculo
del percentil (`np.mean([1 for s in sharpes if s < real])`, que
siempre da 1.0 por error de fórmula — dio un percentil falso de 100.0
antes de corregirse), documentado con la misma transparencia que
cualquier otro hallazgo de este laboratorio.

Límite explícito de esta prueba (no es la última palabra): un bloque
de 21 días destruye deliberadamente la persistencia de tendencia de
varios meses que `time_series_momentum`/`trend_following` buscan
explotar — un tamaño de bloque distinto podría dar un resultado
distinto.

## Capa 5 — Cross-sectional leave-one-group-out

Agrupación por clase de activo (`largo_plazo`, ETFs) o sector GICS
aproximado a mano (`mediano_plazo`/`riesgo_alto`, acciones
individuales — documentado en el código fuente de esa capa). Caída
máxima de Sharpe al quitar cualquier grupo individual:

| Bucket | Grupo con mayor caída | Caída | Label |
|---|---|---|---|
| largo_plazo | Commodities | 1.3% | VALIDATED |
| mediano_plazo | Utilities | 30.2% | VALIDATED |
| riesgo_alto | Hardware_Semis | 17.6% | VALIDATED |

**Los 3 buckets: VALIDATED** — ninguna caída cruza el umbral de 40%;
varios grupos incluso mejoran el Sharpe al quitarse, indicando
dilución, no dependencia concentrada en un clúster correlacionado.

## Capa 6 — Superficie de perturbación de parámetros

Cada parámetro continuo real de cada estrategia perturbado ±10%/±20%,
uno a la vez, el resto fijo en su valor de producción.

| Bucket | Parámetro(s) | Caída máxima dentro de ±10% | Label |
|---|---|---|---|
| largo_plazo | `atr_stop_multiple` | 33.3% | VALIDATED |
| mediano_plazo | `atr_stop_multiple` | 28.1% | VALIDATED |
| riesgo_alto | 4 parámetros (`atr_stop_multiple`, `min_breakout_volume`, `min_relative_strength`, `max_atr_contraction`) | 29.7% | VALIDATED |

**Los 3 buckets: VALIDATED** — ninguna perturbación dentro de ±15%
(la banda que decide el label) produce una caída >50%, sin firma de
pico aislado (sobreajuste). Hallazgo adicional que NO cambia el label
pero es relevante: en `largo_plazo` y `riesgo_alto`, el valor de
parámetro de producción no está en el máximo local de la malla
(un stop más ajustado o filtros más estrictos mejoran el Sharpe
consistentemente en esta muestra) — documentado como observación, no
usado para proponer un cambio (fuera del alcance pre-registrado de
esta capa).

## Capa 7 — Robustez a supuestos de ejecución

Fill al open del día siguiente a la señal (no al close) + 2x la
fricción, combinados, sobre todo el período disponible.

| Bucket | Sharpe baseline → pesimista | Retorno baseline → pesimista | Label |
|---|---|---|---|
| largo_plazo (corregido, con filtro ADR 0034) | 0.92 → 0.18 | +59.52% → +6.37% | **VALIDATED** |
| mediano_plazo | 1.39 → 0.53 | +209.36% → +49.19% | VALIDATED |
| riesgo_alto | 0.91 → 0.33 | +165.28% → +25.65% | VALIDATED |

**Los 3 buckets: VALIDATED** — se degradan fuerte (Sharpe cae ~50-80%)
pero ninguno cruza a pérdida neta. `largo_plazo` tuvo originalmente
(sin el filtro real) un resultado REJECTED (Sharpe 0.78→−0.09, retorno
+45.96%→−9.28%) que se revirtió por completo al corregir el harness —
el REJECTED original era un artefacto de probar una versión de la
estrategia que ya no es la que opera en producción, no un hallazgo
real sobre la configuración vigente.

## Síntesis (no es un promedio ni una votación)

Las dos capas diseñadas específicamente para distinguir habilidad real
de azar (3 y 4) rechazan a los 3 buckets (con la ambigüedad sin
resolver de `largo_plazo` en la Capa 3). Las tres capas de robustez (5,
6, 7) las pasan los 3 — el resultado no depende de un sector, un
parámetro exacto, o un supuesto de ejecución optimista. La Capa 1
queda INCONCLUSIVE en los 3 por pocas operaciones — la pregunta de
consistencia temporal sigue abierta con los datos disponibles. La
Capa 2 agrega un hallazgo adicional y más severo específico de
`riesgo_alto`: sesgo de supervivencia material confirmado.

**Lectura de fondo**: no hay evidencia validada de que la
configuración actual de producción tenga una ventaja real sobre el
azar, en ninguno de los 3 buckets — y en `riesgo_alto` esto se agrava
con el sesgo de supervivencia. Esto no equivale a "está probado que no
vale nada" (Capa 1 INCONCLUSIVE deja esa pregunta abierta). EXP-003 no
busca ni propone una configuración alternativa — valida o rechaza
únicamente la de hoy, por diseño del pre-registro.

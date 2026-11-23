# LOG — EXP-005 Reverse Winners

## 2026-11-22 — Pre-registro

El usuario propuso "Reverse Winners": en vez de perseguir acciones que
ya están subiendo, identificar los mayores ganadores de 30 días hacia
atrás y "regresar al día 0" para extraer qué características tenían
antes de subir, con disciplina explícita de discovery→feature
extraction→rule formation→out-of-sample→evaluation (la misma que ya
rige este laboratorio).

Antes de pre-registrar se señaló un riesgo real: "los ganadores tenían
momentum antes" es casi tautológico — ya documentado por la literatura
de momentum cruzado (Jegadeesh & Titman 1993) y ya en producción
(`cross_sectional_momentum`, ADR 0034 de `algo_trading_platform`). Se
acordó agregar una condición de éxito explícita: el bucket descubierto
debe superar CLARAMENTE un baseline de momentum de un solo factor, no
solo igualarlo con más parámetros.

El usuario pidió formalizarlo como EXP-005, dejando a criterio la
ventana histórica a usar. Se verificó contra el manifiesto real de
EXP-004 (no se asumió) la cobertura del universo S&P 1500 por año de
inicio de cada símbolo: 74.6% ya cotizaba en 2010, 89% en 2018, 100%
en 2026. Se eligió 2010-01-01 como inicio del periodo completo
(~17 años) por balancear cobertura razonable del universo con muchas
ventanas de 30 días independientes — la debilidad de "pocos eventos"
que limitó a EXP-001/EXP-003 no debería repetirse aquí dado el volumen
de observaciones posible.

Se escribió y bloqueó `PREREGISTRATION.md` v1: reutiliza el universo y
los precios de EXP-004 (no hace falta nueva infraestructura de datos,
este experimento no usa FINRA), split discovery 2010-2018/validation
2019-2021 (incluye COVID)/locked test 2022-2026 (incluye el bear
market 2022 y el rally de IA), 15 features candidatas medidas en T0 con
discriminación estadística previa a construir cualquier bucket, grilla
cerrada de hasta 243 variantes, 4 baselines (momentum simple de un solo
factor es el que decide si el experimento aporta algo), criterios
VALIDATED/REJECTED/INCONCLUSIVE fijados antes de correr nada —
incluyendo el chequeo explícito de concentración/idiosincrasia (ningún
ticker puede aportar >20% de las señales).

**Pendiente, declarado en el pre-registro, no resuelto todavía**:
fuerza relativa vs. sector requiere una clasificación GICS de los
1,501 símbolos que no existe en este laboratorio — se decidirá si se
construye (mismo criterio que la Capa 5 de EXP-003 de
`algo_trading_platform`) o se declara fuera de alcance de v1.

**Siguiente paso**: construir `prl.reverse_winners.features` (módulo
de indicadores técnicos + discriminación estadística) — no se ha
corrido nada todavía, no se ha tocado ningún dato real.

## Módulo `prl.reverse_winners.features` implementado

Se escribió `IMPLEMENTATION_SPEC.md` con el contrato completo de
`prl.reverse_winners.features`: 15 funciones base (momentum,
distancia_sma, cruce_sma, atr, volatilidad_realizada, volumen_relativo,
volume_spike_zscore, rsi, drawdown_previo, gap, fuerza_relativa, beta,
sharpe_reciente, distancia_extremo, aceleracion) con fórmula y reglas
de borde exactas, el ensamblador `calcular_features_simbolo` (20
columnas con nombres y parámetros fijos), `universo_elegible`,
`features_cross_sectional`, `normalizar_percentil_cross_sectional`,
`discriminacion_features` y `features_discriminantes`, más 11 casos de
prueba obligatorios. ~40 tests escritos en
`tests/reverse_winners/test_reverse_winners_features.py` antes de
mandar nada a DeepSeek.

DeepSeek implementó el módulo vía `implement-module.yml` (2
iteraciones, veredicto `TESTS_PASAN`). El workflow no abrió el PR
automático (el `gh pr create` del workflow falló en silencio — ver
nota técnica abajo); se revisó la rama `implement/
reverse_winners_features-20261122T232029Z` directamente: lectura
completa de las 399 líneas contra el contrato (propagación de NaN,
manejo de booleanos nullable en `cruce_sma`, las tres ramas exactas de
`rsi` para gain/loss=0, el guard de `volume_spike_zscore` cuando la
desviación es cero, el orden determinístico de
`discriminacion_features`) y re-ejecución independiente de la suite en
un `git worktree` aislado (31 passed) antes de mergear a `main` por
fast-forward.

**Bug encontrado y corregido tras el merge** (no antes, porque no se
había corrido la suite completa con el módulo nuevo adentro):
`tests/reverse_winners/test_features.py` compartía basename con
`tests/emergency/test_features.py`; como ningún directorio de `tests/`
usa `__init__.py`, pytest exige basenames únicos en todo el árbol y la
colección completa se interrumpía con error. Se corrigió renombrando a
`test_reverse_winners_features.py` (mismo criterio que ya usa
`growth_max` para sus propios archivos de test) y actualizando la
entrada `MODULOS["reverse_winners_features"]` en `src/prl/implement.py`.
Re-verificado: suite completa 242 passed (211 previos + 31 nuevos).

Nota técnica sobre el PR automático: el workflow intentó `gh pr create
|| echo "No se pudo abrir el PR."`, que se tragó el error sin dejar
rastro visible más allá del log del run. Al no haber PR, la revisión
se hizo directamente sobre la rama (lectura de código + test
independiente) y el merge se hizo a mano — no se saltó la revisión
humana, solo el mecanismo de PR.

**Pendiente**: construir la grilla cerrada de buckets (hasta 243
variantes), los baselines (incluyendo el de momentum simple que decide
si el experimento aporta algo), el módulo de evaluación
(DSR/PBO/placebo/concentración) y el orquestador — todavía no se ha
tocado ningún dato real de precios, solo se construyó y verificó el
módulo de features.

## Módulos `grid`, `baselines`, `evaluation` y orquestador `exp005` implementados; corrida real completa

Se escribieron los contratos + tests de los 3 módulos restantes antes
del orquestador: `prl.reverse_winners.grid` (grilla cerrada de hasta
243 variantes, direccionada por el signo de `diferencia_medianas` de
cada feature discriminante), `prl.reverse_winners.baselines` (los 4
baselines, incluido el de momentum simple), `prl.reverse_winners.
evaluation` (bootstrap de bloques pareado, Deflated Sharpe Ratio
reimplementado igual que en EXP-001/002, PBO vía CSCV — Bailey et al.
2014, implementado desde cero porque no existía antes en este
laboratorio —, concentración, leave-one-ticker-out, placebo, y la
función de etiqueta final). Los 3 se mandaron a DeepSeek en paralelo,
se revisaron y verificaron de forma independiente (worktrees aislados)
antes de mergear — sin hallazgos de corrección.

Antes de escribir el contrato del orquestador se encontró y corrigió
un bug propio en el borrador del contrato: `ajustar_ohlc` especificaba
`factor = adj_close / close`, asumiendo que eso daría `NaN` cuando
`close=0` — en realidad `x/0.0` da `inf` en numpy/pandas, no `NaN`
(solo `0/0` da `NaN`). Se corrigió el contrato para exigir una máscara
explícita antes de mandarlo a DeepSeek, evitando que el bug quedara
bloqueado en el código generado.

El orquestador (`prl.reverse_winners.exp005`) se implementó vía
DeepSeek en 2 iteraciones, se revisó línea por línea contra el
contrato (sin hallazgos de corrección) y se verificó con un smoke test
sobre una muestra real de 40 símbolos antes de mergear a `main`. Suite
completa: 278/278 tras el merge.

**Corrida real** (2026-11-23, commit `025a906`, universo completo de
1,501 símbolos con datos, parámetros exactos del pre-registro,
`seed=0`): **`INCONCLUSIVE`**. El bucket descubierto (alta volatilidad
realizada 20d + bajo drawdown 60d + cerca de su máximo de 20d + beta
alto) supera a los 4 baselines en el locked test (2022-2026), incluido
el baseline de momentum simple (la condición que de verdad importaba),
con un bootstrap pareado de 87.9% de réplicas a favor — pero el
Deflated Sharpe Ratio (0.534, corregido por las 81 variantes
realmente probadas) queda muy por debajo del umbral de 0.95 exigido
para `VALIDATED`. PBO de 32.9% (CSCV, 10 particiones). Ningún chequeo
de concentración, leave-one-ticker-out o sensibilidad a vecinos de la
grilla disparó un rechazo. Detalle completo, con la tabla de los 6
criterios de éxito evaluados uno por uno, en `RESULTADOS.md`.

No se propone una fase de implementación operativa (reservada a un
resultado `VALIDATED` por el propio pre-registro). No se ajustó
ningún umbral después de ver el resultado.

## Forward validation: hipótesis congelada + mecanismo de recheck periódico

A petición del usuario, se construyó una validación forward estricta
del bucket ganador (el que dio `INCONCLUSIVE`), congelando
exactamente su configuración — universo, 4 features discriminantes,
umbrales, horizonte de 30d, método de retorno — sin volver a
descubrir ni reoptimizar nada con datos nuevos. Documento completo:
`FORWARD_VALIDATION.md`.

Se encontraron y resolvieron 2 ambigüedades propias al congelar: (1)
el bucket no tiene paso de ranking, es un filtro AND puro equal-weight
— se declara así en vez de inventar un criterio de orden; (2) el
pre-registro original exigía 0.05%+0.05% de costos de transacción pero
la implementación nunca los aplicó — se mantiene retorno bruto para
que la comparación forward sea consistente con lo ya reportado, y se
documenta la discrepancia en vez de corregirla en silencio.

Hallazgo crítico antes de tocar datos nuevos: **no existe ninguna
fecha de corte forward disponible hoy** (2026-11-23) con retorno de 30
días ya completo — la corrida original ya consumió hasta la última
fecha posible dados los precios actuales (SPY hasta 2026-11-12). Se
verificó con precisión (0 fechas nuevas con ventana completa) antes de
fabricar un resultado con muestra insuficiente, y se le preguntó
explícitamente al usuario cómo proceder dado ese hallazgo — eligió
congelar todo ahora y programar un recheck periódico.

Se construyeron 3 módulos nuevos vía DeepSeek-TDD:
`prl.reverse_winners.forward_validation` (Sharpe, max drawdown, hit
rate, turnover, concentración del efecto en pocas señales, desgloses
por periodo/régimen VIX/tercil de volatilidad — sector y tamaño de
empresa declarados no calculables por falta de datos),
`prl.reverse_winners.forward_runner` (aplica el bucket congelado y los
4 baselines + SPY sobre fechas dadas, reutilizando literalmente
`grid.aplicar_bucket`/`baselines.*`/`features.*`), y
`prl.reverse_winners.forward_check` (determina fechas nuevas, acumula
el log entre corridas de forma idempotente, calcula las métricas del
reporte).

**Dos bugs serios encontrados en la primera implementación de
`forward_runner` antes de mergear** (revisión manual, no solo
"TESTS_PASAN"): (1) nunca llamaba `grid.aplicar_bucket` con el orden
de argumentos real — el intento con el orden equivocado lanzaba
`KeyError`, capturado por un `except Exception` demasiado amplio que
caía en una reimplementación propia de la lógica de umbrales, la cual
NO reflejaba el umbral para dirección `"bajo"` (`valores <= umbral` en
vez de `valores <= 1-umbral`) — verificado con un caso manual: el real
selecciona 1 de 3 símbolos, el fallback seleccionaba 2; (2) la llamada
a `features.calcular_features_simbolo` se hacía sin el argumento
`benchmark` (obligatorio), también oculta por un `except` genérico —
esto dejaba **0 señales siempre**, para el bucket y los 4 baselines,
en cualquier fecha. Mis propios tests tampoco atraparon ninguno de los
dos (solo verificaban fechas o comportamiento vacío-compatible) — se
reescribieron el contrato (prohíbe explícitamente adivinar firmas y
usar `except` genéricos) y los tests (comparan contra las funciones
reales llamadas directamente, para direcciones "alto" y "bajo") antes
de re-despachar. De paso se encontró que el fixture sintético de
volumen constante (también presente, sin corregir, en
`test_reverse_winners_exp005.py` ya mergeado) deja `volume_spike_z`
siempre `NaN`, excluyendo a todos los símbolos de elegibilidad — no se
tocó `exp005.py` porque sus resultados ya están verificados contra
datos reales (smoke test de 40 símbolos + la corrida completa de
1,501).

El mecanismo de recheck (`scripts/exp005_forward_check.py`, sin
cómputo propio — puro *glue* que llama a los módulos de arriba) se
probó end-to-end contra una muestra real de 40 símbolos (con una
fecha de corte simulada anterior, ya que hoy no hay ninguna real) y
produjo el reporte exacto que pidió el usuario. Se conectó a
`.github/workflows/exp005-forward-check.yml`, cron semanal (domingos,
2h después de `data-build.yml`) + `workflow_dispatch`, mismo patrón
idempotente que `daily-indicator.yml` — commitea el log y el reporte
solo cuando de verdad hay fechas nuevas.

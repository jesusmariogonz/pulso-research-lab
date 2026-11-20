# EXP-004 — Short Pressure Reversal

**Estado:** `LOCKED`

Aprobado por el responsable del proyecto el 2026-11-20 y bloqueado con el
commit que añade esta línea. Desde este punto, cualquier cambio a las
reglas se registra en el *Registro de cambios* como nueva versión; todo
lo decidido después de ver resultados es **exploratorio** y no puede
mover la etiqueta final.

## Pregunta

¿Podemos identificar un bucket de activos que, después de una caída
extrema y bajo presión short elevada, tenga una probabilidad
significativamente mayor de experimentar una recuperación — y esa
ventaja sobrevive a la corrección por el número de configuraciones
exploradas, a la validación fuera de muestra, y a perturbaciones
razonables de los umbrales?

Este experimento es de **discovery**, no de confirmación: la hipótesis
no se asume cierta. El flujo es DATA → FEATURES → EXPLORATION →
CANDIDATE BUCKETS → TRAINING → VALIDATION → OOS → ROBUSTNESS → FINAL
BUCKET → CONCLUSION. Si la evidencia no existe, el resultado correcto
es `REJECTED`; si existe solo dentro de muestra, `INCONCLUSIVE`.

## Hipótesis

* **H1 (alternativa):** existe una combinación de SHORT PRESSURE +
  PRICE EXHAUSTION + REVERSAL CONFIRMATION, dentro de la grilla cerrada
  definida abajo, cuyo forward return en el *locked test* es superior
  al mejor de los 6 baselines, de forma distinguible del azar (bootstrap
  pareado) y consistente en al menos 2 de los 3 horizontes primarios
  (5d/10d/20d).
* **H0 (nula):** ninguna combinación de la grilla supera a los
  baselines de forma distinguible del azar fuera de muestra.
* **H2 (anti-sobreajuste, obligatoria para validar):** la ventaja, si
  existe, sobrevive la corrección por selección múltiple (Deflated
  Sharpe Ratio sobre las 140 variantes de la grilla) y es robusta a
  perturbar el umbral ganador a su vecino inmediato en la grilla (si
  una perturbación razonable revierte el signo o destruye más de la
  mitad del efecto, se trata como señal de sobreajuste, no de hallazgo
  real — ver "Robustez").

## Universo (fijo — ningún activo más, ninguno menos)

**S&P 1500 actual** (S&P 500 + S&P 400 MidCap + S&P 600 SmallCap), ≈1,500
símbolos — elegido explícitamente sobre un universo más angosto (ej.
S&P 500 solo) porque el fenómeno de "short squeeze"/reversión bajo
presión short es estructuralmente más relevante en mid/small-cap que en
large-cap establecido, y sobre un universo más amplio (todo lo que
reporta FINRA, varios miles de símbolos, incluyendo OTC/micro-caps) por
costo de descarga/cómputo y calidad de dato dudosa en esa cola.

Fuente: constituyentes **actuales** (no point-in-time históricos) de 3
tablas públicas ya verificadas accesibles desde este entorno — S&P 500
vía `github.com/datasets/s-and-p-500-companies` (misma fuente ya usada
y confirmada en la Capa 2 de EXP-003 de `algo_trading_platform`), S&P
400 y S&P 600 vía las tablas de Wikipedia "List of S&P 400/600
companies" (confirmadas accesibles y parseables — 6,062 celdas `<td>`
detectadas en la tabla de S&P 400 en la verificación previa a este
pre-registro).

**Limitación declarada, igual que en EXP-003 Capa 2**: usar
constituyentes de HOY para todo el periodo 2019-2026 elimina el sesgo
de *selección manual con hindsight* (no se eligen los 30-79 nombres que
ya se sabe que ganaron), pero NO elimina el sesgo de supervivencia
completo — una empresa que quebró, fue adquirida o salió de estos 3
índices durante 2019-2026 no aparece en ningún lado. Se declara
explícitamente, no se reconstruye un universo point-in-time histórico
(fuera de alcance por costo/tiempo).

## Datos y sus limitaciones conocidas

Todas las fuentes de abajo se verificaron con una petición HTTP real
(no de memoria ni documentación) antes de fijar este pre-registro.

| Fuente | Qué da | Ventana confirmada | Limitación conocida |
|---|---|---|---|
| FINRA Reg SHO, short volume diario (`cdn.finra.org/equity/regsho/daily/CNMSshvolYYYYMMDD.txt`, gratis, sin auth) | `ShortVolume`/`TotalVolume` por símbolo, por día | 2019-01-02 → hoy (403 antes de esa fecha) | Es actividad de trading en corto, no posición acumulada — se complementa con short interest. |
| FINRA short interest bi-mensual (`cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv`, gratis, sin auth) | `currentShortPositionQuantity`, `daysToCoverQuantity` (ya calculado), `changePercent`/`changePreviousNumber`, por símbolo, cada settlement date (15 y fin de mes) | 2020-01-15 confirmado; 2019 probable, pre-2019 da 403 | **No da float ni "% del float"** — ver abajo. Cadencia bi-mensual (step function, no diario). Publicación real: 7° día hábil después del settlement (point-in-time = usar el último valor PUBLICADO a cada fecha, nunca el settlement date directo). `revisionFlag` existe en el esquema: si una fecha histórica fue revisada, la descarga de hoy da el valor revisado, no el originalmente publicado (no hay historial de versiones) — limitación heredada del proveedor, se declara, no se oculta. |
| Precios/volumen diario (yfinance, ya usado por este laboratorio) | OHLCV | Según el símbolo, típicamente años | Ya documentado en `data/catalog.yaml` (revisiones de precio ajustado — ver ADR equivalente de `algo_trading_platform`, aplica igual aquí: una sola descarga congelada por corrida). |

**Sobre "short interest / float" (pedido originalmente)**: no hay fuente
gratuita de float histórico point-in-time. Se reemplaza por las 3
sub-features que FINRA sí da de forma directa y gratuita:
`days_to_cover`, `short_interest_change_pct`, y `short_volume_ratio`
(diario). Esto es una sustitución declarada, no una cifra inventada.

## Features

Todas se calculan por símbolo/día y se normalizan por **percentil
cross-sectional dentro del universo, el mismo día** (nunca un umbral
absoluto — pedido explícito del diseño original).

### Short Pressure

* `short_volume_ratio` = ShortVolume/TotalVolume (diario, Reg SHO).
* `short_volume_ratio_zscore_20d` = z-score de `short_volume_ratio` vs.
  su propia media/std de los 20 días previos (detecta un PICO de
  actividad corta, no solo un nivel persistentemente alto).
* `days_to_cover` (bi-mensual, último valor publicado, point-in-time).
* `short_interest_change_pct` (bi-mensual, ídem).
* `SHORT_PRESSURE_SCORE` = percentil cross-sectional promedio de las 4
  anteriores (pesos iguales — ver "Ranking" sobre por qué no se asumen
  pesos distintos sin evidencia primero).

### Price Exhaustion

`drawdown_5d/20d/60d`, `rsi_2`, `rsi_14`, `dist_sma20/50/200`,
`ret_1d/5d/20d`, `realized_vol_20d`, `rel_volume` (volumen/promedio
20d), `zscore_ret_5d` (vs. su propia distribución de 1 año). Todas ya
calculables con el pipeline de indicadores existente del laboratorio
(mismas fórmulas que `algo_trading_platform` usa para sus estrategias
de producción, reimplementadas aquí sobre el universo de acciones).
`PRICE_EXHAUSTION_SCORE` = percentil cross-sectional promedio (pesos
iguales, mismo razonamiento que arriba) — invertido para que "bajo
percentil" = más agotado/sobrevendido.

### Reversal Confirmation

Conjunto de reglas binarias, evaluadas el día de la señal (T, con el
OHLC ya cerrado de T):

* A — `close_T > close_{T-1}` (cierre positivo tras la caída)
* B — `(close_T - low_reciente) / (high_reciente - low_reciente) ≥ 0.25`
  (recuperó ≥25% del rango de la caída reciente — ventana de 10 días)
* C — `high_T > high_{T-1}` (ruptura del máximo del día anterior)
* D — `realized_vol_T(5d) < realized_vol_{T-1}(5d)` (contracción de
  volatilidad)
* E — `rel_volume_T > 1.0 AND close_T > close_{T-1}` (volumen por
  encima del promedio en un día de cierre positivo — proxy de volumen
  comprador, no hay datos de volumen por lado)

## Normalización

Percentil cross-sectional (`rank(pct=True)` sobre el universo completo
ese día, no solo entre candidatos), igual convención que
`cross_sectional_momentum.py` de `algo_trading_platform` (ADR 0034 de
ese repositorio) — precedente ya probado en producción, reutilizado
aquí, no reinventado.

## Periodo y split (discovery / validation / locked test)

Acotado por la ventana real confirmada de los datos de short interest
(2019-02 en adelante, con margen de seguridad sobre el límite duro de
2019-01):

* **Discovery**: 2019-02-01 → 2022-12-31 (≈4 años) — aquí se filtran
  las variantes por soporte mínimo (ver "Selección").
* **Validation**: 2023-01-01 → 2024-06-30 (≈1.5 años) — aquí se elige
  LA variante ganadora entre las que pasaron el filtro de discovery.
* **Locked test**: 2024-07-01 → 2026-11-01 (≈2.3 años) — **nunca se
  mira hasta la corrida final**, igual disciplina que EXP-002.

## Grilla completa de buckets candidatos (todas las variantes — ninguna más)

| Dimensión | Valores | n |
|---|---|---|
| Umbral SHORT_PRESSURE_SCORE | P75, P80, P85, P90, P95 | 5 |
| Umbral PRICE_EXHAUSTION_SCORE (percentil bajo = agotado) | P5, P10, P15, P20 | 4 |
| Configuración de Reversal Confirmation | ninguna, A, A+C, A+B, A+D, A+E, A+B+C+D+E (todas) | 7 |

**Total: 5 × 4 × 7 = 140 variantes.** Cerrada y enumerada aquí — no se
prueba ninguna combinación fuera de esta tabla. No se asume de
antemano cuál de las 7 configuraciones de confirmación "funciona
mejor" (pedido explícito del diseño original): las 7 se corren igual.

## Selección de la variante (dentro de discovery+validation, nunca locked test)

1. **Filtro de soporte mínimo (en discovery)**: la variante se descarta
   si genera <30 señales independientes en todo el universo×discovery,
   o si un solo ticker aporta >20% de las señales (concentración).
2. **Ranking (en validation, entre las que pasaron el filtro)**: se
   ordena por el forward return medio a 10 días (horizonte primario) de
   las señales generadas en el periodo de validation.
3. La variante con mejor ranking en el paso 2 es **la ganadora** — se
   congela antes de tocar el locked test.

## Targets

Por cada señal: forward return a 1/3/5/10/20/60 días; MFE; MAE; máximo
drawdown después de la entrada; tiempo hasta +2%/+5%/+10%; probabilidad
de terminar positivo (por horizonte); probabilidad de alcanzar un nuevo
mínimo antes de recuperarse (antes de +0% desde la entrada).

## Baselines (mismo universo, mismo periodo, mismos costos)

1. **Buy & Hold**: equal-weight de todo el universo.
2. **Caída simple**: comprar cuando `ret_5d ≤ -10%` (umbral fijo, sin
   búsqueda), mismos horizontes.
3. **Mean reversion solo con price exhaustion**: comprar cuando
   `PRICE_EXHAUSTION_SCORE ≤ P10`, sin short pressure ni confirmación.
4. **Solo Short Pressure**: comprar cuando `SHORT_PRESSURE_SCORE ≥ P90`,
   sin price exhaustion ni confirmación.
5. **Solo Price Exhaustion sin Short Pressure**: idéntico al baseline 3
   (se declara como el mismo baseline para no duplicar; el pedido
   original los separaba por simetría conceptual, aquí son la misma
   regla).
6. **Combo ingenuo, sin búsqueda de umbrales**: `SHORT_PRESSURE_SCORE ≥
   P90` AND `PRICE_EXHAUSTION_SCORE ≤ P10` AND confirmación = A (la
   más simple) — umbrales fijos de referencia, NUNCA elegidos por la
   grilla. Este baseline existe específicamente para aislar cuánto
   valor agrega el PROCESO DE BÚSQUEDA (los 140 intentos) sobre
   simplemente combinar las 3 ideas a ojo.

El objetivo explícito (pedido original): determinar si agregar
información de short selling aporta valor incremental sobre price
exhaustion solo (baseline 3 vs. bucket ganador) y sobre un combo
ingenuo sin búsqueda (baseline 6 vs. bucket ganador).

## Costos

0.05% comisión + 0.05% slippage por lado — mismo estándar que
`METHODOLOGY.md` de este laboratorio y que el sistema de trading de
producción.

## Validación

* **Sin look-ahead**: toda señal del día T usa solo datos conocidos al
  cierre de T (incluido el short interest: se usa el último valor
  PUBLICADO a esa fecha, respetando el lag real de 7 días hábiles tras
  el settlement — nunca el valor del settlement date directo).
* **Walk-forward**: la selección de la variante ganadora (arriba) usa
  discovery→validation como dos ventanas separadas, no optimización
  conjunta. El locked test es la única medición fuera de muestra real.
* **Point-in-time del short interest**: ver tabla de datos arriba — se
  implementa como serie escalonada (forward-fill desde la fecha de
  publicación, nunca desde el settlement date).

## Robustez

* **Sensibilidad a umbrales**: la grilla ya cubre los vecinos
  inmediatos de cualquier ganador (ej. si gana P90, P85 y P95 ya están
  corridos) — no hace falta una corrida extra. Si el vecino inmediato
  revierte el signo del efecto o lo reduce >50%, se marca como posible
  sobreajuste (pedido explícito del diseño original).
* **Deflated Sharpe Ratio**: corrigiendo por las 140 variantes de la
  grilla, misma derivación que el appendix de EXP-002 y la Capa 3 de
  EXP-003.
* **PBO (Combinatorially Symmetric Cross-Validation)**: sobre el
  subconjunto de variantes con suficientes señales por partición
  temporal para que sea informativo.
* **Placebo con potencia verificada**: mismo estándar que la Capa 4 de
  EXP-003 — señales en días aleatorios (mismo conteo que el bucket
  real), verificando varianza no-trivial entre réplicas ANTES de
  interpretar cualquier percentil.
* **Análisis por régimen (EXPLORATORIO, post-hoc, no cambia la
  etiqueta)**: bull/bear (SPY sobre/bajo su SMA200) y alta/baja
  volatilidad (VIX sobre/bajo su mediana histórica) — describe,
  no prueba.

## Ranking dentro del bucket final (Reversal Score)

Antes de asumir pesos, se estudia el poder predictivo individual de
cada sub-feature (correlación/IC con el forward return primario,
dentro de discovery+validation únicamente). Si hay evidencia suficiente
de que algunas pesan más, se usa una combinación ponderada; **si no hay
evidencia suficiente, el ranking es un promedio simple de percentiles,
y esa limitación se declara explícitamente** (pedido explícito del
diseño original — no se inventa un peso sin respaldo).

## Criterios de éxito (fijados antes de correr)

* **`VALIDATED`**: en el locked test, el bucket ganador supera al
  MEJOR de los 6 baselines en al menos 2 de los 3 horizontes primarios
  (5d/10d/20d), con el bootstrap pareado (bloques de 20 días, mismo
  estándar que `METHODOLOGY.md`) dando ≥80% de las réplicas a favor del
  bucket — **y** DSR > 0.95 sobre las 140 variantes — **y** ningún
  vecino inmediato en la grilla revierte el signo o destruye >50% del
  efecto — **y** ≥20 señales independientes en el locked test — **y**
  ningún ticker aporta >20% de esas señales.
* **`REJECTED`**: el bucket ganador no supera a NINGÚN baseline en el
  locked test, o DSR ≤ 0.5, o el placebo (con potencia confirmada) no
  lo distingue de un reordenamiento al azar.
* **`INCONCLUSIVE`**: cualquier otro caso — p. ej. supera algún
  baseline pero no el mejor, o DSR entre 0.5-0.95, o pocas señales en
  el locked test, o es sensible a los vecinos de la grilla sin llegar a
  revertir el signo.

## Fuera de alcance

No toca el motor de paper trading ni IBKR de `algo_trading_platform`,
ni ningún sistema de producción. Solo si resulta `VALIDATED` se
propondría una fase aparte (con su propio pre-registro) para evaluar
una implementación operativa — nunca una consecuencia automática de
este experimento.

## Registro de cambios

| Fecha | Cambio | Commit |
|---|---|---|
| 2026-11-20 | Pre-registro inicial (v1), tras verificar con peticiones HTTP reales la disponibilidad de short volume diario y short interest bi-mensual de FINRA, y la accesibilidad de las tablas de S&P 400/600 | (este commit) |

# EXP-005 — Forward Validation (hipótesis congelada)

**Estado:** `LOCKED` (bloqueado el 2026-11-23, antes de que exista una
sola fecha de evaluación forward con retorno de 30 días completo —
ver "Por qué no hay resultados todavía").

Este documento congela, palabra por palabra, la configuración exacta
que salió de `experiments/EXP-005-reverse-winners/RESULTADOS.md`
(corrida original, commit `209c90d`). **Nada de lo que está aquí se
reoptimiza, recalibra ni reselecciona** con datos nuevos. Si algún
parámetro necesario no está determinado por la corrida original, se
declara explícitamente como ambigüedad resuelta (con la decisión
tomada y por qué) — no se inventa en silencio.

## 1. Hipótesis congelada

### Universo

`data/universes/sp1500_short_pressure.txt` — exactamente el mismo
archivo, 1,502 símbolos listados (1,501 con datos; `CWEN-A` sin
archivo, igual que en la corrida original). Benchmark: `SPY`.

### Elegibilidad por fecha

Igual que `features.universo_elegible` + el filtro de `exp005.py`: un
símbolo participa en una fecha de corte si tiene ≥252 sesiones de
historia previa **y** su fila de features esa fecha no tiene ningún
`NaN` en las 20 columnas.

### Features discriminantes (congeladas, no se re-descubren)

| Feature | Dirección | Fórmula (ya implementada en `prl.reverse_winners.features`) |
|---|---|---|
| `vol_realizada_20d` | alto | volatilidad realizada anualizada, ventana 20d |
| `drawdown_60d` | bajo | `precio / máximo(60d) − 1` |
| `dist_max20` | bajo | `precio / máximo(20d) − 1` |
| `beta_60d` | alto | beta 60d vs. `SPY` |

Estas 4 son las que discriminaron en la corrida original — **no se
vuelve a correr `discriminacion_features` con datos nuevos**. Si una
quinta feature hubiera discriminado distinto incluyendo datos nuevos,
eso es información para un experimento *nuevo*, no para esta
validación forward.

### Bucket ganador (congelado, `variant_id` original)

```
vol_realizada_20d: alto, P90
drawdown_60d:      bajo, P90
dist_max20:        bajo, P90
beta_60d:          alto, P75
```

Condición de entrada: **AND** de las 4 — percentil cross-sectional de
cada feature, calculado dentro del universo elegible esa fecha (misma
convención `rank(pct=True)` de todo el laboratorio), comparado contra
el umbral fijo de cada feature. Se aplica literalmente con
`prl.reverse_winners.grid.aplicar_bucket` (la misma función ya
probada, sin tocar su código).

### Ranking — **no existe, no se inventa uno**

El bucket original es un filtro puro (AND de condiciones), no una
selección top-N rankeada. **Todos los símbolos que cumplen las 4
condiciones entran, con el mismo peso (equal-weight)** — no hay un
criterio de desempate ni de orden porque nunca hizo falta uno en la
corrida original (nunca se limitó el tamaño del bucket a un top-N).

### Horizonte y método de retorno

30 sesiones hábiles hacia adelante, **retorno simple sin componer**:
`retorno_30d = cierre_ajustado.shift(-30) / cierre_ajustado − 1`
(`prl.reverse_winners.exp005.retorno_forward`, ya implementada). Precio
ajustado por splits/dividendos (`ajustar_ohlc`, `adj_close`).

### Cadencia de fechas de corte

Una fecha de corte cada 10 sesiones hábiles (`paso_dias=10`), sobre el
calendario de `SPY` — misma función `fechas_t0` ya implementada.

### Costos de transacción — **ambigüedad resuelta: NO se aplican**

El pre-registro original (`PREREGISTRATION.md`, sección *Costos*)
declaraba un estándar de 0.05% comisión + 0.05% slippage por lado,
pero la implementación real (`exp005.py`) **nunca aplicó ese costo** —
todos los números de `RESULTADOS.md` son retornos brutos. Esto es una
discrepancia real entre el pre-registro y lo implementado, detectada
al congelar esta hipótesis. Decisión: el forward test usa el **mismo
método exacto** que la corrida original (bruto, sin costos) para que
la comparación sea de manzanas con manzanas — no se "corrige" el
método ahora, eso sería cambiar la hipótesis a mitad de la validación.
Se reporta este hallazgo explícitamente aquí para que quede trazable;
si se quisiera un número neto de costos, sería un análisis aparte, no
una modificación de esta validación forward.

### Baselines de comparación (los mismos 4 de la corrida original, más SPY)

1. **Momentum simple** — Top 20% por `mom_20d` (percentil). El que de
   verdad importa.
2. **Buy & Hold** — universo elegible completo, equal-weight.
3. **RSI simple** — Top 10% por RSI14 más bajo (mean-reversion).
4. **Combo ingenuo** — `mom_20d>0 AND dist_sma50>0 AND
   vol_relativo_20d>1.2` (umbrales crudos, fijos).
5. **`SPY`** (nuevo en el reporte forward, no estaba en los 4
   originales, agregado porque el usuario lo pidió explícitamente como
   referencia de benchmark — no modifica el bucket, solo agrega una
   línea de comparación) — retorno simple del propio índice a 30 días
   desde cada fecha de corte.

## 2. Periodo forward

**No existe todavía ninguna fecha de corte nueva con retorno de 30
días completo.** Verificado el 2026-11-23: la corrida original ya
usó, como última fecha de locked test, el **2026-09-30** — que es,
dado el precio disponible hoy (`SPY` hasta 2026-11-12), la **última
fecha para la que un retorno de 30 sesiones hábiles ya está
completo**. La siguiente fecha de corte posible (~2026-10-14)
necesitaría precio hasta ~2026-11-27, que no existe todavía.

Esto no es una limitación de cómputo — es que el tiempo de calendario
real necesario para una validación forward honesta **todavía no ha
pasado**. Correr esto hoy con los datos actuales daría exactamente
**0 señales nuevas**, no una muestra chica.

**Plan**: un mecanismo de recheck periódico (ver sección siguiente de
este experimento) revisa automáticamente si ya existe al menos 1 fecha
de corte nueva con retorno completo y, si existe, corre el bucket
congelado sobre ella y acumula el resultado en
`FORWARD_VALIDATION_RESULTADOS.md` / `forward_log.json`. El primer
dato nuevo debería estar disponible aproximadamente a mediados de
diciembre de 2026 (10 sesiones hábiles después del 2026-09-30, más el
buffer de 30 días para el retorno).

## 3. Comparación, desgloses y criterios — declarados antes de tener un solo dato nuevo

### Métricas por fecha/acumuladas (una vez haya señales)

Retorno promedio, mediana, volatilidad, Sharpe, máximo drawdown, hit
rate, retorno acumulado, exceso de retorno vs. cada benchmark, número
de posiciones, concentración (`frac_max_ticker`), turnover (cambio de
composición del bucket entre fechas de corte consecutivas).

### Desgloses — **2 de los 4 pedidos no son calculables hoy, declarado, no inventado**

* **Por periodo**: sí, calculable (se acumula fecha por fecha conforme
  pasa el tiempo).
* **Por régimen de mercado**: sí, calculable — terciles de nivel de
  `VIX` (`data/raw/VIX.parquet`, disponible desde 1990) en cada fecha
  de corte, como proxy de régimen (no hay una clasificación de
  régimen más rica en este laboratorio; se declara así).
* **Por sector**: **no calculable** — no existe clasificación GICS (ni
  aproximada) de los 1,501 símbolos en este laboratorio. Ya declarado
  como limitación en `PREREGISTRATION.md` original.
* **Por tamaño de empresa**: **no calculable** — no existe dato de
  capitalización de mercado para el universo en este laboratorio. No
  se aproxima con un proxy (ej. precio o volumen en dólares) porque
  eso introduciría una variable nueva no congelada ni declarada en el
  pre-registro original.
* **Por volatilidad**: sí, calculable — terciles de `vol_realizada_20d`
  cruda de cada símbolo seleccionado ese día (la misma feature ya
  usada en el bucket, reportada por tercil para ver si el efecto se
  concentra en el tercil más extremo).

### Criterio de éxito (fijado ahora, antes de cualquier dato forward)

* 🟢 **Evidencia favorable**: el bucket supera a los 5 benchmarks en
  retorno acumulado forward, con al menos 10 fechas de corte
  acumuladas (≈ 3-4 meses de forward real) y sin que el resultado
  dependa de una sola fecha o de <5 símbolos extraordinarios
  (verificado con el mismo tipo de leave-one-ticker-out ya
  implementado).
* 🟡 **Evidencia inconclusa**: menos de 10 fechas de corte acumuladas
  (muestra insuficiente para concluir nada, sin importar el signo del
  resultado), o resultado mixto entre benchmarks, o dependiente de
  pocos nombres.
* 🔴 **Evidencia negativa**: el bucket pierde claramente contra
  Buy & Hold y Momentum simple con ≥10 fechas acumuladas.

**Nunca se declara `VALIDATED`/`CANDIDATE FOR VALIDATION` solo porque
el retorno acumulado sea positivo** — se exige el mismo nivel de
evidencia (consistencia, significancia vs. número de observaciones,
no depender de pocos nombres) que ya aplicó el experimento original.

## Registro de cambios

| Fecha | Cambio |
|---|---|
| 2026-11-23 | Congelado v1. Se detectó y declaró la discrepancia costos-de-transacción (pre-registro original los exigía, la implementación nunca los aplicó) — se decide mantener retorno bruto para comparación consistente. Se declara la imposibilidad de desgloses por sector/tamaño de empresa por falta de datos. |

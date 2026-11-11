# EXP-001 — Contrato de implementación (lo que debe cumplir el código)

Este documento y los tests en `tests/emergency/` son el **contrato**. El
código de `src/prl/emergency/*.py` debe hacerlos pasar sin tocarlos.
Implementa el pre-registro `PREREGISTRATION.md`; si hay conflicto, manda el
pre-registro.

Reglas transversales:
* **Sin look-ahead:** el valor en la fecha *t* solo puede usar datos con
  fecha ≤ *t*. Hay tests que truncan y alteran el futuro para comprobarlo.
* Solo `pandas`, `numpy`, `math`, `typing`, `dataclasses`. Sin red, sin
  archivos, sin variables de entorno.
* Funciones puras, con tipos y docstring breve.

## `features.py` — dimensiones de estrés (z-scores expansivos)

Todas devuelven `pd.Series` con el mismo índice que la entrada. Una dimensión
alta = más estrés.

* `expanding_zscore(s, min_periods=252)`: `(s_t − media(s[:t])) / desv(s[:t], ddof=1)`
  usando todo el historial hasta *t* inclusive. NaN antes de `min_periods`
  observaciones válidas.
* `trend_stress(close)`: crudo = `−(close / SMA200 − 1)`; luego `expanding_zscore`.
* `vol_stress(vix)`: promedio de `expanding_zscore(log(vix))` y
  `expanding_zscore(log(vix / vix.shift(5)))` (nivel y cambio); si solo uno está
  disponible, usa ese.
* `credit_stress(spread)`: `expanding_zscore(spread)`.
* `drawdown_velocity_stress(close)`: crudo = `−(close / close.shift(10) − 1)`;
  luego `expanding_zscore`.
* `breadth_stress(rsp, spy)`: crudo = `−(log(rsp/spy) − log(rsp/spy).shift(60))`
  (la razón RSP/SPY cayendo = amplitud que se estrecha); luego `expanding_zscore`.
* `correlation_stress(returns, window=60)`: `returns` es un DataFrame de
  retornos diarios de sectores; crudo = correlación promedio por pares (sin la
  diagonal) en la ventana móvil de `window` días; luego `expanding_zscore`.
* `composite_score(dims, weights)`: `dims` es un DataFrame (una columna por
  dimensión), `weights` un dict `{columna: peso}`. Por fila, promedio ponderado
  **solo de las dimensiones disponibles** (no-NaN), con los pesos renormalizados
  entre ellas. Si ninguna está disponible → NaN. Columnas sin peso se ignoran.

## `state_machine.py` — niveles de emergencia

* `exposure_for_level(level)`: `{0: 1.0, 1: 0.75, 2: 0.5, 3: 0.25, 4: 0.0}`.
* `raw_levels(score, theta)`: nivel crudo = `clip(floor(score / theta), 0, 4)`;
  score negativo o NaN → 0. Devuelve enteros.
* `assign_levels(score, theta, k, m)`: aplica persistencia e histéresis sobre
  los niveles crudos. Empieza en nivel 0. En cada día *t*:
  1. **Subir:** `candidato_sube = min(crudo[t-k+1 .. t])`; si `> nivel_actual`,
     el nivel pasa a `candidato_sube`.
  2. **Bajar:** si no subió, `candidato_baja = max(crudo[t-m+1 .. t])`; si
     `< nivel_actual`, el nivel pasa a `candidato_baja`.
  Las ventanas necesitan *k* (o *m*) días completos; antes de eso no hay cambio.
  Nunca salta por una sola señal. Devuelve enteros con el índice de `score`.

## `backtest.py` — política de exposición con costos

* `run_backtest(prices, exposure, risk_asset, safe_weights, cost_per_side=0.001)`:
  * `prices`: DataFrame de precios ajustados diarios (columnas = activos).
  * `exposure`: Series con la exposición objetivo al riesgo (0–1) **decidida al
    cierre de cada día**; se aplica a partir del **día siguiente** (t+1).
  * `safe_weights`: dict `{activo: peso}` (suman 1) del refugio, rebalanceado
    diariamente.
  * Retorno del día *t* (fila *t*): `e_{t−1}·r_riesgo + (1−e_{t−1})·r_refugio − costo`,
    con `r` = retorno simple diario. La primera fila tiene retorno 0.
  * `costo = 2 · cost_per_side · |e_{t−1} − e_{t−2}|` (se vende un lado y se
    compra el otro). La exposición aplicada en la primera fila es `exposure.iloc[0]`
    y no genera costo.
  * **Validación estricta (nunca resultados en silencio con datos faltantes):** lanza
    `ValueError` si, tras alinear `exposure` al índice de `prices`, `exposure` contiene
    NaN o valores fuera de [0, 1]; o si las columnas de `prices` realmente usadas
    (`risk_asset` y las de `safe_weights`) contienen NaN; o si `safe_weights` no suma 1
    (tolerancia 1e-9) o referencia un activo ausente. Quien llama debe recortar la muestra
    al período común antes de llamar.
  * Devuelve DataFrame con columnas `ret`, `equity` (empieza en 1.0), `exposure_applied`, `cost`.
* `metrics(returns)`: dict con `cagr` (años = días calendario / 365.25),
  `max_drawdown` (negativo), `calmar` (`cagr / |max_drawdown|`), `sharpe`
  (`media/desv(ddof=1) · √252`, rf=0), `sortino` (desviación a la baja con
  objetivo 0, `√252`), `n_days`.

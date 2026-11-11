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

---

# Fase 2 — Evaluación y orquestación

Reglas transversales: las mismas de arriba. Los módulos nuevos pueden importar
`prl.emergency.*` y `scipy.stats`. Nunca dejar pasar NaN en silencio.

## `grid.py`

* `build_grid() -> list[dict]`: las **162** variantes del pre-registro, en el orden de
  `itertools.product(weights, theta, k, m, destination)` con
  `weights ∈ ["equal", "tvc2"]`, `theta ∈ [0.5, 1.0, 1.5]`, `k ∈ [2, 3, 5]`,
  `m ∈ [5, 10, 20]`, `destination ∈ ["TLT", "CASH", "MIX"]`. Cada dict trae
  `variant_id` (str único, p. ej. `"equal|0.5|2|5|TLT"`) y las cinco claves anteriores.
* `dimension_weights(name) -> dict`: dimensiones `trend`, `vol`, `correlation`, `credit`,
  `breadth`, `drawdown_velocity`. `"equal"`: todas 1.0. `"tvc2"`: `trend`, `vol` y `credit`
  = 2.0; el resto 1.0. Nombre desconocido → `ValueError`.
* `destination_weights(dest) -> dict`: `"TLT"→{"TLT":1.0}`, `"CASH"→{"CASH":1.0}`,
  `"MIX"→{"TLT":0.5,"CASH":0.5}`. Desconocido → `ValueError`.

## `inputs.py`

* `build_cash_index(dtb3, bil) -> pd.Series`: índice de nivel de efectivo (T-Bills).
  `dtb3` = tasa anual en % (Series diaria); `bil` = precio ajustado de BIL.
  Índice resultado = unión ordenada de ambos índices; `dtb3` se propaga hacia adelante.
  Empieza en 1.0 en la primera fecha. Antes de la primera fecha de BIL:
  `idx_t = idx_{t-1} · (1 + dtb3_{t-1}/100/252)` (usa la tasa del día ANTERIOR). Desde la
  primera fecha de BIL (`t0`): `idx_t = idx_{t0} · bil_t / bil_{t0}` para `t ≥ t0`, donde `idx_{t0}`
  sale de la fórmula sintética. Fechas de BIL ausentes se propagan hacia adelante.
* `sma200_exposure(close) -> pd.Series`: `1.0` si `close > SMA200`, si no `0.0`; mientras no
  haya 200 observaciones, `1.0`. Sin look-ahead.
* `common_start(series: dict[str, pd.Series]) -> pd.Timestamp`: la más tardía de las primeras
  fechas con valor válido (no NaN) entre las series.

## `evaluation.py`

* `walk_forward_select(variant_returns, first_test_year, criterion="calmar") -> (pd.Series, dict[int,str])`:
  `variant_returns` = `{variant_id: Series de retornos diarios}` (mismo índice). Para cada año `Y`
  desde `first_test_year` hasta el último año con datos: elige la variante con mayor
  `metrics(ret hasta el 31-dic de Y-1)["calmar"]` (NaN cuenta como −inf; empates → la primera
  en el orden del dict); los retornos fuera de muestra del año `Y` son los de esa variante en `Y`.
  Devuelve (retornos OOS concatenados en orden cronológico, `{Y: variant_id}`). Si el
  entrenamiento previo a `Y` tiene < 252 retornos → `ValueError`. **Nunca** usa datos del año `Y`
  para elegir.
* `block_bootstrap_ci(r_a, r_b, statistic, block=20, n_boot=500, alpha=0.05, seed=0) -> (float, float)`:
  *block bootstrap* pareado. Con `rng = np.random.default_rng(seed)`, en cada réplica concatena
  `ceil(n/block)` bloques de `block` filas consecutivas (inicio uniforme en `[0, n-block]`), se
  recorta a `n` filas y se aplica **la misma** selección de filas a `r_a` y `r_b`; evalúa
  `statistic(a, b)`. Devuelve los percentiles `alpha/2` y `1-alpha/2` (np.percentile). Si
  `n < block` → `ValueError`.
* `deflated_sharpe_ratio(returns, n_trials) -> float`: sea `n=len(returns)`, `sr` = media/desv(ddof=1)
  **diaria** (sin anualizar), `g3` = asimetría y `g4` = curtosis (NO exceso) de los retornos
  (pandas `skew()` y `kurt()+3`), `sr_std = sqrt((1 - g3·sr + (g4-1)/4·sr²)/(n-1))`. Si
  `n_trials ≤ 1`: `sr0 = 0`; si no: `γ = 0.5772156649015329` y
  `sr0 = sr_std · ((1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e)))` con `N = n_trials`. Resultado
  `Φ((sr - sr0)/sr_std)` (Φ = normal estándar, `scipy.stats.norm`).
* `episode_report(close, level, episodes) -> dict`: `episodes` = lista de dicts
  `{"name","peak","trough"}` (fechas `YYYY-MM-DD`). `close` = precios del riesgo; `level` = nivel
  de emergencia por fecha (enteros 0–4), mismo índice.
  * `cross20` de un episodio = primera fecha **posterior** a `peak` con `close/close[peak]-1 ≤ -0.20`
    (`None` si no existe).
  * Ventana de detección = fechas `d` con `peak - 90 días ≤ d ≤ cross20`; `detection_date` = primera
    con `level ≥ 2` (`None` si no hay). `lead_days = (cross20 - detection_date).days`;
    `detected = detection_date is not None`.
  * `"episodes"`: lista con `name, peak, trough, cross20, detection_date, lead_days, detected`
    (fechas como `YYYY-MM-DD`).
  * Alarmas = rachas máximas de fechas consecutivas con `level == 4`; sea `s` su primera fecha.
    Es falsa si, en las **60 filas siguientes** a `s`, `min(close/close[s]-1) > -0.10`. Si quedan
    < 60 filas posteriores → no evaluable. `"alarms"`: `{"n_alarms", "n_false", "n_unevaluable", "false_dates": [...]}`.
* `non_episode_shortfall(model_returns, bench_returns, episodes) -> float`: excluye las fechas
  `peak ≤ d ≤ trough` de cualquier episodio; devuelve
  `prod(1+bench) - prod(1+model)` sobre las fechas restantes (retorno acumulado del benchmark
  menos el del modelo; positivo = el modelo se perdió rally).
* `label_result(m: dict) -> str` con claves `maxdd_model`, `maxdd_bh`, `cagr_model`, `cagr_bh`,
  `calmar_model`, `calmar_sma`, `calmar_diff_ci_lo` (los drawdowns son negativos):
  1. **`"REJECTED"`** si `calmar_model <= calmar_sma` **o** `maxdd_model < maxdd_bh` es falso
     (es decir, el modelo no reduce el MaxDD: `abs(maxdd_model) >= abs(maxdd_bh)`).
  2. Si no, **`"VALIDATED"`** si `abs(maxdd_model) <= 0.70·abs(maxdd_bh)` **y**
     `cagr_model >= 0.90·cagr_bh` **y** `calmar_diff_ci_lo > 0`.
  3. En cualquier otro caso **`"INCONCLUSIVE"`**.
  Cualquier valor faltante o NaN → `"INCONCLUSIVE"`.

## `exp001.py`

`run(inputs_dir, run_dir, first_test_year=2003, n_boot=500, episodes=None) -> dict`. Escribe
`run_dir/results.json` (y lo devuelve). `episodes=None` usa los 4 del pre-registro
(`DEFAULT_EPISODES`: dot-com 2000-03-24→2002-10-09, crisis financiera 2007-10-09→2009-03-09,
COVID 2020-02-19→2020-03-23, 2022 2022-01-03→2022-10-12). Pasos:
1. Lee `inputs_dir/<ID>.parquet`: precios con `adj_close`; series FRED (`BAA10Y`, `DTB3`) con `value`.
   Series: SPY, VIX, BAA10Y, RSP, sectores XLK XLE XLF XLV XLP XLU XLY XLI XLB, TLT, BIL, DTB3.
2. Dimensiones: `trend=trend_stress(SPY)`, `vol=vol_stress(VIX)`, `credit=credit_stress(BAA10Y)`,
   `breadth=breadth_stress(RSP,SPY)`, `drawdown_velocity=drawdown_velocity_stress(SPY)`,
   `correlation=correlation_stress(retornos diarios de los 9 sectores)`. Todo alineado al índice
   de SPY (los FRED con propagación hacia adelante).
3. `CASH = build_cash_index(DTB3, BIL)` alineado a SPY (propagación hacia adelante). Precios
   del backtest: columnas `SPY`, `TLT`, `CASH`, recortados a `common_start` de las tres.
4. Para cada variante de `build_grid()`: `score = composite_score(dims, dimension_weights(w))`,
   `level = assign_levels(score, theta, k, m)`, `exposure = level.map(exposure_for_level)`,
   `run_backtest(prices, exposure, "SPY", destination_weights(dest), 0.001)`. Guarda `ret`, `level`,
   `exposure_applied` y `cost` por variante.
5. `walk_forward_select` sobre los `ret` de todas las variantes → retornos OOS del modelo y
   `chosen_by_year`. El nivel, `exposure_applied` y `cost` OOS se arman uniendo los de la variante
   elegida en cada año.
6. Benchmarks sobre las mismas fechas OOS (mismo `run_backtest`, costo 0.001): buy-and-hold
   (exposición 1.0), regla SMA200 (`sma200_exposure(SPY)`, refugio `{"CASH":1.0}`) y 60/40
   (exposición 0.6 constante, refugio `{"TLT":1.0}`).
7. `metrics` de los cuatro (modelo y 3 benchmarks) sobre el período OOS. IC bootstrap de
   `calmar(modelo) - calmar(SMA200)` con `block_bootstrap_ci(..., block=20, n_boot=n_boot, seed=0)`.
8. `episode_report(SPY, nivel_OOS, episodes)`, `non_episode_shortfall(modelo, buy-and-hold, episodes)`,
   `deflated_sharpe_ratio(retornos OOS del modelo, n_trials=162)`.
9. `label = label_result({...})` con los valores calculados (`calmar_diff_ci_lo` = límite inferior).
10. `results.json` (NaN → `null`) con claves: `experiment` ("EXP-001"), `first_test_year`, `oos_start`,
    `oos_end` (fechas), `n_variants`, `n_oos_days`, `metrics` (`model`, `buy_hold`, `sma200`,
    `sixty_forty`: cada uno el dict de `metrics`), `calmar_diff_vs_sma200` (`value`, `ci_lo`, `ci_hi`,
    `n_boot`, `block`), `episodes` (salida de `episode_report`), `non_episode_shortfall`,
    `deflated_sharpe`, `chosen_by_year` (claves str), `level_fractions` (fracción de días OOS en
    cada nivel 0–4), `turnover` (suma de |Δ exposición aplicada|), `costs_paid` (suma de costos),
    `label`, `notes` (lista de limitaciones: rebalanceo diario sin costo, crédito solo con BAA10Y
    —sin HYG/LQD en v0—, amplitud solo con proxies, pocos eventos independientes).
Debe ser **determinista** (mismas entradas → mismo `results.json`).

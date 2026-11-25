# EXP-004 — Contrato de implementación (lo que debe cumplir el código)

Convención general (igual que EXP-005): `rolling(..., min_periods=ventana)`
en todo lo que requiera ventana completa — antes de eso, `NaN`, nunca un
valor calculado con menos datos de los que pide el parámetro. Percentil
cross-sectional siempre `rank(pct=True)` (método `"average"` de pandas
ante empates), calculado dentro del universo elegible, el mismo día —
nunca un umbral absoluto. Cada módulo es autocontenido (no importa de
`prl.reverse_winners` ni de ningún otro paquete de experimento, aunque
varias fórmulas coincidan — mismo criterio ya usado entre EXP-001/002/005).

## `prl.short_pressure.features`

Implementa la sección *Features* de `PREREGISTRATION.md`. Tests en
`tests/short_pressure/test_short_pressure_features.py`. Solo `pandas`,
`numpy`, `typing`. Funciones puras (sin red, sin archivos).

### Bloques base de precio (mismas fórmulas que `prl.reverse_winners.features`, reimplementadas aquí)

* `momentum(precio: pd.Series, dias: int) -> pd.Series`: `precio / precio.shift(dias) - 1`.
* `distancia_sma(precio: pd.Series, ventana: int) -> pd.Series`: `sma = precio.rolling(ventana, min_periods=ventana).mean()`; `precio / sma - 1`.
* `rsi(precio: pd.Series, ventana: int) -> pd.Series`: RSI simple (no Wilder). `diff = precio.diff()`, `ganancia = diff.clip(lower=0)`, `perdida = (-diff).clip(lower=0)`, medias móviles de cada una con `min_periods=ventana`. Si `media_perdida > 0`: `100 - 100/(1 + media_ganancia/media_perdida)`; si `media_perdida == 0` y `media_ganancia > 0`: `100.0`; si ambas `0`: `50.0`. `NaN` antes de completar la ventana.
* `drawdown_previo(precio: pd.Series, ventana: int) -> pd.Series`: `maximo = precio.rolling(ventana, min_periods=ventana).max()`; `precio / maximo - 1`.
* `volatilidad_realizada(precio: pd.Series, ventana: int) -> pd.Series`: `retornos = precio.pct_change()`; `std = retornos.rolling(ventana, min_periods=ventana).std(ddof=1)`; resultado `= std * sqrt(252)`.
* `volumen_relativo(volumen: pd.Series, ventana: int) -> pd.Series`: `volumen / volumen.rolling(ventana, min_periods=ventana).mean()`. `NaN` si el promedio es `0` o antes de completar la ventana.
* `zscore_retorno(precio: pd.Series, dias_retorno: int, ventana: int) -> pd.Series`: `r = momentum(precio, dias_retorno)`; `media = r.rolling(ventana, min_periods=ventana).mean()`; `sd = r.rolling(ventana, min_periods=ventana).std(ddof=1)`; resultado `= (r - media) / sd`. `NaN` si `sd` es `0`/`NaN` o antes de completar la ventana. (Usada para `zscore_ret_5d` con `dias_retorno=5, ventana=252` — z-score del retorno de 5 días contra su propia distribución de 1 año, pedido explícito del pre-registro.)
* `zscore_nivel(serie: pd.Series, ventana: int) -> pd.Series`: igual que `zscore_retorno` pero sobre el NIVEL de `serie` directamente (sin `momentum` previo) — `media`/`sd` rolling de `serie` misma. Usada para `short_volume_ratio_zscore_20d` (detecta un PICO de actividad corta, no solo un nivel alto sostenido).

### Short Pressure (consume las fuentes ya descargadas por `prl.data.finra`, no vuelve a parsear FINRA)

* `short_volume_ratio_serie(short_volume_simbolo: pd.DataFrame, calendario: pd.DatetimeIndex) -> pd.Series`: `short_volume_simbolo` son las filas de `short_volume_consolidado.parquet` de UN símbolo (columnas `date`, `short_volume_ratio`, puede tener huecos — FINRA no publica todos los días hábiles para todos los símbolos). Reindexa a `calendario` (sin relleno: fechas sin dato quedan `NaN`) y devuelve la Serie de `short_volume_ratio` en ese índice.
* `days_to_cover_serie(short_interest_simbolo: pd.DataFrame, calendario: pd.DatetimeIndex) -> pd.Series` y `short_interest_change_pct_serie(short_interest_simbolo: pd.DataFrame, calendario: pd.DatetimeIndex) -> pd.Series`: `short_interest_simbolo` son las filas de `short_interest_consolidado.parquet` de un símbolo (columnas `settlement_date`, `days_to_cover`, `short_interest_change_pct`). Para cada fecha de `calendario`, usa el snapshot VIGENTE a esa fecha según el point-in-time de FINRA: construye `snapshots = {settlement_date: fila}` y, para cada fecha de `calendario`, el snapshot vigente es el de mayor `settlement_date` tal que `settlement_date + 7 días hábiles (pd.tseries.offsets.BDay(7)) <= fecha` (igual regla que `prl.data.finra.fecha_publicacion`/`ultimo_short_interest_vigente`, reimplementada aquí sin importar ese módulo — mismo criterio de autocontención). `NaN` si no hay ningún snapshot ya publicado a esa fecha.
* `SHORT_PRESSURE_SCORE(tabla_percentil: pd.DataFrame) -> pd.Series`: `tabla_percentil` ya trae las columnas `short_volume_ratio`, `short_volume_ratio_zscore_20d`, `days_to_cover`, `short_interest_change_pct` **ya normalizadas a percentil cross-sectional** (esta función NO normaliza, solo promedia — la normalización es responsabilidad del ensamblador, igual que en EXP-005). Resultado = promedio simple (pesos iguales) de las 4 columnas, fila por fila. `NaN` si alguna de las 4 es `NaN` para esa fila (sin promedio parcial — pedido implícito de "pesos iguales" sobre las 4, no sobre las que estén disponibles).

### Price Exhaustion

14 sub-features: `ret_1d/5d/20d` (`momentum`), `drawdown_5d/20d/60d` (`drawdown_previo`), `dist_sma20/50/200` (`distancia_sma`), `rsi_2/14` (`rsi`), `realized_vol_20d` (`volatilidad_realizada`), `rel_volume` (`volumen_relativo`, ventana 20), `zscore_ret_5d` (`zscore_retorno`, dias_retorno=5, ventana=252).

**Ambigüedad resuelta** (el pre-registro dice "percentil cross-sectional promedio, invertido para que bajo percentil = más agotado" sin especificar la orientación de cada sub-feature — se declara aquí en vez de inventarla en silencio): 12 de las 14 sub-features tienen un valor crudo MÁS BAJO cuando hay más agotamiento (retornos muy negativos, drawdown profundo, muy por debajo de sus medias móviles, RSI bajo/sobrevendido, z-score de retorno muy negativo) — para esas, el rank orientado hacia agotamiento es `1 - rank_normal`. Las otras 2 (`realized_vol_20d`, `rel_volume`) indican agotamiento cuando son ALTAS (pico de volatilidad/volumen típico de una capitulación) — para esas, el rank orientado es el `rank_normal` directo, sin invertir. `PRICE_EXHAUSTION_SCORE` final = `1 - promedio(los 14 ranks ya orientados hacia agotamiento)` — esta inversión final es la que hace que, tal como pide el pre-registro, un percentil BAJO del score final signifique más agotamiento (un símbolo muy agotado tiene un promedio orientado alto → `1 - alto` = bajo).

* `PRICE_EXHAUSTION_SCORE(tabla_percentil: pd.DataFrame) -> pd.Series`: `tabla_percentil` ya trae las 14 columnas (listadas arriba, nombradas exactamente `ret_1d, ret_5d, ret_20d, drawdown_5d, drawdown_20d, drawdown_60d, dist_sma20, dist_sma50, dist_sma200, rsi_2, rsi_14, realized_vol_20d, rel_volume, zscore_ret_5d`) **ya normalizadas a percentil cross-sectional, sin orientar** (`rank_normal`, tal cual salen de `rank(pct=True)`) — esta función hace la orientación y el promedio. `NaN` si alguna de las 14 es `NaN` para esa fila.

### Reversal Confirmation (reglas binarias, día T con el OHLC ya cerrado)

Ventana de "caída reciente" para la regla B: 10 sesiones (`ventana_caida=10`, parámetro con ese default, no fijo dentro de la función).

* `confirmacion_a(cierre: pd.Series) -> pd.Series`: `bool`. `cierre > cierre.shift(1)`. `NaN` (dtype `"boolean"` nullable) en la primera fila.
* `confirmacion_b(cierre: pd.Series, alto: pd.Series, bajo: pd.Series, ventana_caida: int = 10) -> pd.Series`: `bool`. `high_reciente = alto.rolling(ventana_caida, min_periods=ventana_caida).max()`, `low_reciente = bajo.rolling(ventana_caida, min_periods=ventana_caida).min()`, `rango = high_reciente - low_reciente`. Resultado: `(cierre - low_reciente) / rango >= 0.25` donde `rango > 0`; si `rango == 0` (precio plano toda la ventana), `False` (no `NaN`: no hay caída que recuperar, la confirmación no aplica, se declara `False` en vez de indefinido). `NaN` antes de completar `ventana_caida`.
* `confirmacion_c(alto: pd.Series) -> pd.Series`: `bool`. `alto > alto.shift(1)`. `NaN` en la primera fila.
* `confirmacion_d(vol_5d: pd.Series) -> pd.Series`: `bool`. Recibe la serie YA calculada de `volatilidad_realizada(precio, 5)` (no la recalcula). `vol_5d < vol_5d.shift(1)`. `NaN` si cualquiera de los dos valores es `NaN`.
* `confirmacion_e(rel_volume: pd.Series, cierre: pd.Series) -> pd.Series`: `bool`. Recibe `rel_volume` ya calculado (`volumen_relativo(volumen, 20)`). `(rel_volume > 1.0) & (cierre > cierre.shift(1))`. `NaN` si `rel_volume` es `NaN`; si `rel_volume` no es `NaN` pero es la primera fila de `cierre` (sin `cierre.shift(1)`), también `NaN`.

### Ensamblador

* `calcular_features_simbolo(df: pd.DataFrame, short_volume_simbolo: pd.DataFrame, short_interest_simbolo: pd.DataFrame) -> pd.DataFrame`: `df` columnas `["open", "high", "low", "close", "volume"]`, índice de fechas ya ordenado ascendente (ya ajustado por splits/dividendos por el llamador, igual convención que EXP-005 — esta función no ajusta OHLC). Calcula las 18 columnas crudas con los bloques de arriba (4 de short pressure sin `SHORT_PRESSURE_SCORE` todavía — ese se agrega normalizado, ver abajo — más 14 de price exhaustion) más las 5 columnas booleanas de confirmación (`confirmacion_a` .. `confirmacion_e`), usando `df.index` como `calendario` para las series de FINRA. Devuelve un único `DataFrame` con esas 23 columnas, mismo índice que `df`.

### Casos de prueba obligatorios

1. Cada bloque base de precio: un caso con ventana completa (valor conocido calculado a mano) y un caso antes de completar la ventana (`NaN`).
2. `short_volume_ratio_serie`/`days_to_cover_serie`/`short_interest_change_pct_serie`: fixture sintético con huecos reales (fechas de `calendario` sin fila en `short_volume_simbolo`) → `NaN` en esas fechas; para el point-in-time, un caso explícito donde una fecha de `calendario` cae ANTES de que el snapshot más reciente se publique (7 días hábiles tras su `settlement_date`) → usa el snapshot ANTERIOR, no el que todavía no se publicó; otro caso donde cae justo el día de publicación → ya usa el nuevo.
3. `SHORT_PRESSURE_SCORE`/`PRICE_EXHAUSTION_SCORE`: tabla percentil sintética de 5-10 símbolos con valores conocidos; verificar el promedio a mano para un símbolo, y verificar explícitamente la orientación de `PRICE_EXHAUSTION_SCORE` (un símbolo con las 12 sub-features "orientables" en su extremo más agotado y las 2 de volumen/volatilidad también altas debe terminar con el percentil MÁS BAJO del grupo).
4. Cada regla de confirmación: casos sintéticos que cubren `True`/`False`/el caso límite (`rango == 0` en B; igualdad exacta en A/C/D/E).
5. `calcular_features_simbolo`: fixture con `df` + `short_volume_simbolo` + `short_interest_simbolo` sintéticos, verifica que las 23 columnas existen con los nombres exactos y que una fila intermedia conocida coincide con el cálculo manual.

Todos los datos de prueba son sintéticos, construidos a mano (sin red).

## `prl.short_pressure.grid`

Implementa la sección *Grilla completa de buckets candidatos* de
`PREREGISTRATION.md`. Tests en
`tests/short_pressure/test_short_pressure_grid.py`. Solo `itertools`,
`typing` (y `pandas` solo en `aplicar_bucket`, que recibe un
`DataFrame`). A diferencia de `prl.reverse_winners.grid` (que
generaliza sobre features DESCUBIERTAS), aquí la grilla es **fija y
enumerada en el pre-registro** — no hay paso de descubrimiento.

* `UMBRALES_SHORT_PRESSURE: list[float] = [0.75, 0.80, 0.85, 0.90, 0.95]`
* `UMBRALES_PRICE_EXHAUSTION: list[float] = [0.05, 0.10, 0.15, 0.20]`
* `CONFIRMACIONES: list[tuple[str, ...]] = [(), ("a",), ("a", "c"), ("a", "b"), ("a", "d"), ("a", "e"), ("a", "b", "c", "d", "e")]` — 7 configuraciones, en ese orden exacto (coincide con el orden del pre-registro: "ninguna, A, A+C, A+B, A+D, A+E, A+B+C+D+E").
* `build_grid() -> list[dict]`: sin argumentos (la grilla es fija). `itertools.product(UMBRALES_SHORT_PRESSURE, UMBRALES_PRICE_EXHAUSTION, CONFIRMACIONES)`, en ese orden de anidamiento (short pressure más significativo, confirmación menos significativo — semántica estándar de `itertools.product`). Devuelve exactamente 140 elementos, cada uno `{"variant_id": str, "umbral_short_pressure": float, "umbral_price_exhaustion": float, "confirmaciones": tuple[str, ...]}`. `variant_id = f"sp{int(sp*100)}_pe{int(pe*100)}_conf{''.join(c) if c else 'ninguna'}"` (ej. `"sp90_pe10_confa"`, `"sp75_pe5_confninguna"`).
* `aplicar_bucket(variant: dict, tabla_percentil: pd.DataFrame) -> pd.Series`: `tabla_percentil` tiene columnas `SHORT_PRESSURE_SCORE`, `PRICE_EXHAUSTION_SCORE` (ya normalizadas/orientadas por `features`) y, si `variant["confirmaciones"]` no está vacío, las columnas booleanas `confirmacion_a`..`confirmacion_e` necesarias. `bool`, índice = `tabla_percentil.index`. Condición: `SHORT_PRESSURE_SCORE >= variant["umbral_short_pressure"]` **y** `PRICE_EXHAUSTION_SCORE <= variant["umbral_price_exhaustion"]` **y**, para cada letra en `variant["confirmaciones"]`, `tabla_percentil[f"confirmacion_{letra}"] == True` (un `NaN`/`pd.NA` en cualquiera de las columnas usadas da `False` para esa fila, nunca excepción — comparación estándar de pandas/NA).

### Casos de prueba obligatorios

1. `build_grid()`: exactamente 140 elementos; todos los `variant_id` únicos; el primero es `{umbral_short_pressure: 0.75, umbral_price_exhaustion: 0.05, confirmaciones: ()}`, el último es `{0.95, 0.20, ("a","b","c","d","e")}`.
2. `aplicar_bucket`: tabla sintética de 6-8 símbolos con `SHORT_PRESSURE_SCORE`/`PRICE_EXHAUSTION_SCORE`/columnas de confirmación conocidas; verificar a mano la selección para una variante sin confirmaciones, una con una sola letra, y una con las 5; un símbolo con `NaN` en `SHORT_PRESSURE_SCORE` → `False`, nunca excepción.

Todos los datos de prueba son sintéticos.

## `prl.short_pressure.baselines`

Implementa la sección *Baselines* de `PREREGISTRATION.md`. Tests en
`tests/short_pressure/test_short_pressure_baselines.py`. Solo
`pandas`/`typing`. Funciones puras, todas devuelven `pd.Series`
booleana, mismo índice que su entrada principal. El pre-registro
declara el baseline 5 idéntico al 3 (mismo motivo: no se implementa
dos veces, el orquestador reusa el resultado de `baseline_price_exhaustion`
para ambos).

* `baseline_buy_hold(simbolos_elegibles: list[str]) -> pd.Series`: `True` para todos, indexado por `simbolos_elegibles` en ese orden.
* `baseline_caida_simple(features_crudas: pd.DataFrame) -> pd.Series`: `features_crudas["ret_5d"] <= -0.10` (umbral fijo, valores crudos — no percentil). `NaN` en `ret_5d` → `False`.
* `baseline_price_exhaustion(tabla_percentil: pd.DataFrame) -> pd.Series`: `tabla_percentil["PRICE_EXHAUSTION_SCORE"] <= 0.10` (percentil ya normalizado/orientado, umbral fijo de referencia — nunca el de la grilla). `NaN` → `False`.
* `baseline_short_pressure(tabla_percentil: pd.DataFrame) -> pd.Series`: `tabla_percentil["SHORT_PRESSURE_SCORE"] >= 0.90`. `NaN` → `False`.
* `baseline_combo_ingenuo(tabla_percentil: pd.DataFrame) -> pd.Series`: `(tabla_percentil["SHORT_PRESSURE_SCORE"] >= 0.90) & (tabla_percentil["PRICE_EXHAUSTION_SCORE"] <= 0.10) & (tabla_percentil["confirmacion_a"] == True)`. Umbrales fijos de referencia, nunca elegidos por la grilla — existe para aislar cuánto valor agrega el proceso de búsqueda. `NaN` en cualquiera de las tres → `False`.

### Casos de prueba obligatorios

1. `baseline_buy_hold`: lista de 3 símbolos → 3 `True`, mismo orden.
2. `baseline_caida_simple`: tabla sintética con `ret_5d` en `[-0.15, -0.10, -0.05, NaN]` → selecciona exactamente las dos primeras (`<=-0.10` incluye el límite exacto); `NaN` → `False`.
3. `baseline_price_exhaustion`/`baseline_short_pressure`: tablas percentil sintéticas, verificar el límite exacto (`<= 0.10` y `>= 0.90` respectivamente, inclusive) y `NaN` → `False`.
4. `baseline_combo_ingenuo`: tabla de 5 símbolos cubriendo: cumple los 3 (`True`); falla exactamente uno (`False`); `NaN` en uno de los tres (`False`).

Todos los datos de prueba son sintéticos.

## `prl.short_pressure.evaluation`

Implementa la sección *Validación y robustez* y *Criterios de éxito* de
`PREREGISTRATION.md`. Tests en
`tests/short_pressure/test_short_pressure_evaluation.py`. Solo
`pandas`/`numpy`/`scipy.stats`/`typing`/`itertools`/`math`. Sin red,
sin archivos. Funciones puras. **Mismas fórmulas estadísticas que
`prl.reverse_winners.evaluation`** (reimplementadas aquí, no
importadas — mismo criterio de autocontención del proyecto), con la
misma aclaración de granularidad: las "series de retornos" están
indexadas por fecha de corte (una observación cada fecha de corte de
la grilla, no diaria), y `tamano_bloque` cuenta observaciones de fecha
de corte consecutivas.

* `bootstrap_bloques(retornos: pd.DataFrame, tamano_bloque: int, n_replicas: int, seed: int) -> np.ndarray` — idéntica a `prl.reverse_winners.evaluation.bootstrap_bloques`.
* `comparacion_bootstrap(ret_bucket: pd.Series, ret_baseline: pd.Series, tamano_bloque: int = 2, n_replicas: int = 10000, seed: int = 0, alpha: float = 0.05) -> dict` — idéntica.
* `deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float` — idéntica.
* `probabilidad_backtest_overfitting(matriz_desempeno: pd.DataFrame, n_particiones: int = 10) -> float` — idéntica (CSCV, Bailey et al. 2014).
* `concentracion_maxima(senales: pd.DataFrame) -> dict` — idéntica.
* `leave_one_ticker_out_signo(senales: pd.DataFrame, columna_retorno: str = "retorno_10d") -> dict` — idéntica, salvo que el nombre de columna por defecto es `"retorno_10d"` (horizonte primario de EXP-004, no `"retorno_30d"`).
* `placebo_aleatorio(pool_retornos: pd.Series, n_senales: int, n_placebos: int = 1000, seed: int = 0) -> np.ndarray` — idéntica.
* `percentil_real_vs_placebo(valor_real: float, placebos: np.ndarray) -> float` — idéntica.

### `etiqueta` — distinta de EXP-005: multi-horizonte y 5 baselines, no 4

`etiqueta(n_horizontes_superados: int, mejor_frac_bootstrap: float, dsr:
float, n_senales_locked: int, frac_max_ticker: float,
vecino_revierte_signo: bool, vecino_destruye_mas_50pct: bool,
placebo_distingue: bool | None) -> str`:

`n_horizontes_superados` = cuántos de los 3 horizontes primarios (5d,
10d, 20d) tienen al ganador superando al MEJOR de los 5 baselines
distintos en ese horizonte (lo calcula el orquestador, esta función
solo recibe el conteo ya hecho — 0 a 3). `mejor_frac_bootstrap` = la
`frac_supera_baseline` del bootstrap pareado contra el MEJOR baseline
en el horizonte primario principal (10d), calculado por el
orquestador.

1. `REJECTED` si `n_horizontes_superados == 0` **o** `dsr <= 0.5` **o**
   `frac_max_ticker > 0.20` **o** `placebo_distingue is False`
   (`placebo_distingue is None` no cuenta como rechazo por sí solo).
2. `VALIDATED` si, no habiendo caído en 1: `n_horizontes_superados >=
   2` **y** `mejor_frac_bootstrap >= 0.80` **y** `dsr > 0.95` **y**
   `not vecino_revierte_signo` **y** `not vecino_destruye_mas_50pct`
   **y** `frac_max_ticker <= 0.20` **y** `n_senales_locked >= 20`.
3. `INCONCLUSIVE` en cualquier otro caso. Nunca lanza excepción por
   `NaN` numérico (cuenta como "no cumple" esa comparación).

### Casos de prueba obligatorios

Los mismos 8 casos de `prl.reverse_winners.evaluation` para las
funciones compartidas (ver ese módulo como referencia de qué cubrir:
forma/determinismo de `bootstrap_bloques`, extremos de
`comparacion_bootstrap`, monotonía de `deflated_sharpe_ratio` en
`n_trials`, extremos de `probabilidad_backtest_overfitting` con
matrices "genuina"/"adversarial" sintéticas, empates en
`concentracion_maxima`, reversión en `leave_one_ticker_out_signo`,
determinismo de `placebo_aleatorio`, `percentil_real_vs_placebo` con
`[1,2,3,4,5]` y `valor_real=3` → `0.6`), más para `etiqueta`: los 3
niveles probados por separado, incluido `n_horizontes_superados=1`
con todo lo demás en regla de `VALIDATED` → `INCONCLUSIVE` (no
`VALIDATED`, porque exige `>=2`); `dsr=NaN` con el resto en regla →
`INCONCLUSIVE`; `placebo_distingue=None` con el resto en regla de
`VALIDATED` no cae en `REJECTED` por esa sola razón.

Todos los datos de prueba son sintéticos. `n_replicas`/`n_placebos` de
prueba chicos (decenas).

## `prl.short_pressure.exp004` (orquestador)

Importa `prl.short_pressure.{features, grid, baselines, evaluation}`.
Lee `.parquet` de precios (`inputs_dir`), los dos `.parquet`
consolidados de FINRA, un archivo de texto de universo, escribe
`run_dir/results.json`. Determinista: mismas entradas → mismo
`results.json` byte a byte. Tests en
`tests/short_pressure/test_short_pressure_exp004.py`.

### Funciones puras auxiliares

* `ajustar_ohlc(df: pd.DataFrame) -> pd.DataFrame` — idéntica a `prl.reverse_winners.exp005.ajustar_ohlc` (factor `adj_close/close`, `NaN` forzado donde `close` es `0`/`NaN`).
* `retorno_forward(precio_cierre: pd.Series, dias: int) -> pd.Series` — idéntica: `precio_cierre.shift(-dias) / precio_cierre - 1`.

### `run(inputs_dir, short_volume_path, short_interest_path, universo_path, run_dir, discovery_start="2019-02-01", discovery_end="2022-12-31", validation_end="2024-06-30", locked_end="2026-11-01", paso_dias=10, min_historia=252, horizontes=(5, 10, 20), horizonte_principal=10, min_senales_discovery=30, max_frac_ticker=0.20, n_particiones_pbo=10, n_boot=10000, n_placebos=1000, seed=0) -> dict`

Pasos:

1. **Universo y precios**: lee `universo_path` (una línea por símbolo,
   orden tal cual). Lee `inputs_dir/<símbolo>.parquet` por símbolo; si
   no existe, se omite y se registra en `notes` (`f"{símbolo}: sin
   archivo de datos, omitido"`), no lanza excepción. Aplica
   `ajustar_ohlc`. El calendario maestro es la UNIÓN de índices de
   todos los símbolos con datos, ordenada (a diferencia de EXP-005, no
   hay un único benchmark que defina el calendario — short pressure no
   usa SPY como referencia de features, solo como universo de precios
   de cada acción).
2. **Datos FINRA**: lee `short_volume_path`/`short_interest_path`
   (los `.parquet` consolidados), agrupa por símbolo
   (`groupby("symbol")`) una sola vez.
3. **Features por símbolo, historia completa**: para cada símbolo,
   `features.calcular_features_simbolo(df_ajustado,
   short_volume_del_simbolo, short_interest_del_simbolo)` una sola vez
   sobre toda su historia (misma equivalencia rolling/shift que
   EXP-005 — verificada por el caso de prueba 1). También
   `retorno_forward(close_ajustado, h)` para cada `h` en `horizontes`.
4. **Fechas de corte**: una de cada `paso_dias` sesiones del
   calendario maestro, desde `discovery_start`, recortadas a las que
   tienen al menos `max(horizontes)` filas de calendario después (para
   que el retorno forward más largo sea calculable). Divide en
   `discovery` (`< discovery_end`), `validation` (`discovery_end <=
   fecha <= validation_end`), `locked` (`validation_end < fecha <=
   locked_end`) — límites inclusivos en el extremo superior de cada
   tramo.
5. **Tabla cross-sectional por fecha de corte**: un símbolo es
   elegible esa fecha si tiene `>= min_historia` filas de precio
   original con índice `<= fecha` **y** su fila de features esa fecha
   (o la más reciente `<= fecha` si `short_volume_ratio`/`days_to_cover`
   / `short_interest_change_pct` tienen huecos de publicación —
   **excepción explícita**: SOLO esas 3 columnas de FINRA usan
   forward-fill desde la última fila no nula hasta `fecha`, el resto
   de las 23 columnas exige la fila exacta de `fecha` sin `NaN`) no
   tiene `NaN` en ninguna columna tras ese forward-fill acotado a
   FINRA. Arma `features_crudas` y, con
   `rank(pct=True)` por columna sobre los símbolos elegibles esa
   fecha, `features_percentil_sin_orientar` (18 columnas numéricas:
   las 4 de short pressure crudas y las 14 de price exhaustion, sin
   incluir las 5 booleanas de confirmación, que no se normalizan).
   Agrega `SHORT_PRESSURE_SCORE`/`PRICE_EXHAUSTION_SCORE` llamando a
   las funciones de `features` sobre ese percentil, y copia las 5
   columnas booleanas de confirmación (no se normalizan). Junta el
   `retorno_{h}d` de cada símbolo elegible esa fecha, para cada `h` en
   `horizontes`.
6. **Grilla**: `grid.build_grid()` (140 variantes, fijas — sin paso de
   discriminación, a diferencia de EXP-005).
7. **Filtro de soporte (discovery) y selección (validation, horizonte
   principal)**: para cada una de las 140 variantes, en cada fecha de
   `discovery`, `grid.aplicar_bucket(variante, tabla_de_esa_fecha)` →
   señales `(fecha, símbolo, retorno_{horizonte_principal}d)`. Sobrevive
   si `len(señales_discovery) >= min_senales_discovery` **y**
   `evaluation.concentracion_maxima(...)["frac_max_ticker"] <=
   max_frac_ticker`. Para las sobrevivientes, recolecta señales en
   `validation` (mismo horizonte principal) y calcula su media. La
   ganadora es la de mayor media en validation (empate → primera en
   orden alfabético de `variant_id`). Si ninguna variante sobrevive:
   `results.json` con `"label": "INCONCLUSIVE"`, `"motivo":
   "ninguna_variante_pasa_el_filtro_de_soporte"`, resto en `null` — el
   locked test nunca se toca.
8. **Señales del ganador y los 5 baselines, SOLO en locked test, para
   cada horizonte**: para cada fecha de `locked`, aplica el bucket
   ganador y `baseline_buy_hold` (sobre elegibles esa fecha),
   `baseline_caida_simple`/`baseline_price_exhaustion`/
   `baseline_short_pressure`/`baseline_combo_ingenuo` (sobre la tabla
   de esa fecha, según su contrato). El baseline "5" (price exhaustion
   sin short pressure) del pre-registro es el MISMO resultado que
   `baseline_price_exhaustion` — se reporta una sola vez en
   `metricas_locked`, con una nota aclarando la duplicación declarada
   en el pre-registro. Para cada uno de los 5 (ganador + 4 baselines
   distintos) y cada horizonte, serie indexada por fecha de corte =
   media de `retorno_{h}d` de sus señales esa fecha.
9. **Métricas descriptivas**: para el ganador y cada baseline, por
   cada horizonte: media, mediana, fracción positiva. MFE/MAE/drawdown
   post-señal/tiempo-a-objetivo (sección *Targets*) quedan fuera de
   alcance v1, igual declaración que EXP-005, documentado en `notes`.
10. **`n_horizontes_superados` y mejor baseline por horizonte**: para
    cada horizonte, `mejor_baseline_valor = max(media del ganador... )`
    — no, correcto: para cada horizonte, compara la media del ganador
    contra la media de CADA uno de los 4 baselines distintos en ese
    horizonte; `supera_este_horizonte = True` si la media del ganador
    es mayor que la de TODOS los baselines en ese horizonte (mismo
    criterio "mejor de los baselines" que el pre-registro). `n_horizontes_superados
    = suma de `supera_este_horizonte` sobre los 3 horizontes
    primarios. Identifica, para el horizonte principal (10d), cuál de
    los 4 baselines tuvo la media MÁS ALTA (`mejor_baseline_10d`) —
    ese es el que se usa para el bootstrap pareado del paso siguiente.
11. **Bootstrap vs. mejor baseline (horizonte principal)**: alinea la
    serie del ganador y la del `mejor_baseline_10d` a su índice común
    (fechas con señal en ambos); si vacío,
    `mejor_frac_bootstrap = NaN`. Si no,
    `evaluation.comparacion_bootstrap(serie_ganador, serie_mejor_baseline,
    tamano_bloque=2, n_replicas=n_boot, seed=seed)`.
12. **DSR**: `evaluation.deflated_sharpe_ratio(serie_ganador_validation
    (horizonte principal, paso 7), n_trials=140)`.
13. **PBO**: sobre fechas de `discovery+validation`, mismo
    procedimiento que EXP-005 (bloques contiguos truncados,
    `matriz_desempeno` solo con variantes que sobrevivieron el paso 7 y
    con al menos 1 señal en cada bloque; si quedan <2 así, `pbo =
    null` con nota).
14. **Concentración y leave-one-ticker-out** (señales del ganador en
    locked, horizonte principal): igual que EXP-005.
15. **Sensibilidad a vecinos**: para `umbral_short_pressure`, vecinos
    = valores adyacentes en `UMBRALES_SHORT_PRESSURE` (ej. ganador
    `0.90` → vecinos `0.85` y `0.95`; `0.75`/`0.95` solo tienen un
    vecino); igual para `umbral_price_exhaustion` en
    `UMBRALES_PRICE_EXHAUSTION`; la `confirmaciones` del ganador queda
    fija en ambos casos (el pre-registro no define una noción de
    "vecino" para la configuración de confirmación — son categóricas,
    no ordenadas — se declara así, no se improvisa un orden). Para
    cada vecino, señales en locked test (horizonte principal) y su
    media. `vecino_revierte_signo`/`vecino_destruye_mas_50pct`, misma
    definición que EXP-005.
16. **Placebo**: pool = `retorno_{horizonte_principal}d` de todas las
    señales elegibles en locked (sin estructura de bucket).
    `n_senales_locked` = señales del ganador en locked, horizonte
    principal. Resto idéntico a EXP-005.
17. **Etiqueta**: `evaluation.etiqueta(n_horizontes_superados,
    mejor_frac_bootstrap o 0.0 si NaN, dsr, n_senales_locked,
    frac_max_ticker, vecino_revierte_signo, vecino_destruye_mas_50pct,
    placebo_distingue)`. Igual anulación que EXP-005:
    `revierte_con_algun_ticker` (paso 14) `True` fuerza `"REJECTED"`
    sin importar el resultado de `evaluation.etiqueta`.
18. **`results.json`**: `experiment` (`"EXP-004"`),
    `n_simbolos_universo`, `n_simbolos_con_datos`, `fechas_t0` (conteo
    por split), `n_variantes_grid_total` (140),
    `n_variantes_sobreviven_filtro_soporte`, `variant_id_ganador` (o
    `null`), `motivo`, `metricas_locked` (ganador + 4 baselines
    distintos, cada uno con media/mediana/frac_positivo por cada
    horizonte), `n_horizontes_superados`, `mejor_baseline_10d`,
    `comparacion_bootstrap_vs_mejor_baseline`, `dsr`, `n_trials_dsr`
    (140), `pbo` (o `null`), `n_variantes_pbo`, `concentracion`,
    `leave_one_ticker_out`, `sensibilidad_vecinos` (ambas dimensiones,
    detalle por vecino), `placebo`, `label`, `notes` (símbolos sin
    datos, MFE/MAE/tiempo-a-objetivo fuera de alcance v1, análisis por
    sector fuera de alcance — sin clasificación GICS, análisis por
    régimen bull/bear y vol alta/baja declarado como exploratorio-no-
    incluido-en-v1 si no se alcanza a implementar, baseline 5 idéntico
    al 3 por diseño del pre-registro).

### Casos de prueba obligatorios (integración, datos sintéticos)

Mismo patrón que `test_reverse_winners_exp005.py`: fixture con 8-12
símbolos sintéticos (trayectorias con reversión clara tras caída +
pico de short volume para algunos, planos para otros), series
sintéticas de `short_volume_consolidado`/`short_interest_consolidado`
(con huecos reales de publicación), `discovery_start/discovery_end/
validation_end/locked_end` de prueba más chicos que los del
pre-registro.

1. Equivalencia histórica (igual razonamiento que EXP-005: una
   feature calculada sobre la historia completa vs. truncada a una
   fecha intermedia da el mismo valor en esa fecha).
2. `run` escribe `results.json` con todas las claves de la sección 18;
   `label` ∈ `{VALIDATED, REJECTED, INCONCLUSIVE}`.
3. `run` es determinista (dos corridas, mismo resultado byte a byte).
4. Si `variant_id_ganador` no es `null`, `metricas_locked` tiene
   exactamente 5 claves (`ganador` + 4 baselines distintos), cada una
   con media/mediana/frac_positivo por cada uno de los 3 horizontes.
5. Caso "ninguna variante pasa el filtro de soporte" (datos
   sintéticos donde ninguna combinación genera >=30 señales) →
   `label == "INCONCLUSIVE"`, motivo correcto, locked test nunca
   tocado (verificable porque ninguna señal con fecha de locked
   aparece en ningún lado del resultado).
6. Un símbolo sin archivo `.parquet` no lanza excepción, queda en
   `notes`.
7. El baseline "5" no se calcula dos veces (mismo valor que el "3" en
   `metricas_locked`, una sola entrada).

Todos los datos de prueba son sintéticos (sin red). `n_boot`/
`n_placebos` de prueba chicos.

## Registro de cambios

| Fecha | Cambio |
|---|---|
| 2026-11-25 | Contrato inicial (v1) de los 5 módulos de cómputo, tras retomar el experimento (infraestructura de datos ya cerrada el 2026-11-21). Se resuelve explícitamente la ambigüedad de orientación de `PRICE_EXHAUSTION_SCORE` (no estaba especificada feature por feature en `PREREGISTRATION.md`). |

# EXP-005 — Contrato de implementación (lo que debe cumplir el código)

## `prl.reverse_winners.features`

Implementa la sección "Metodología — ventanas rolling" de
`PREREGISTRATION.md` (pasos 2 y 3: features en T0 y discriminación
estadística). Tests en
`tests/reverse_winners/test_reverse_winners_features.py` (nombre
distinto de "test_features.py" a propósito: ningún directorio de
`tests/` usa `__init__.py`, así que los nombres de archivo deben ser
únicos en todo el árbol — `tests/emergency/test_features.py` ya existe
desde EXP-001; mismo motivo por el que `growth_max` prefija sus tests
con "growth_").

Reglas transversales (igual estándar que `prl.growth_max.signals` de
EXP-002):

* **Sin look-ahead:** el valor en la fecha *t* usa solo datos con
  fecha ≤ *t*. `rolling(..., min_periods=ventana)` en todos lados —
  antes de completar la ventana, `NaN`, nunca un valor calculado con
  menos datos de los que pide el parámetro.
* Solo `pandas`, `numpy`, `typing`, `dataclasses`. Sin red, sin
  archivos, sin variables de entorno.
* Funciones puras, con tipos y docstring breve.
* **Nunca rellenar en silencio:** `NaN` antes de tener ventana
  completa o ante división entre cero, nunca `0`, `inf` ni el valor
  más reciente disponible.
* Todas las funciones de una sola serie devuelven `pd.Series` con el
  mismo índice que la entrada principal.

### Bloques base (parametrizados — se llaman con los parámetros exactos del pre-registro, no se fijan dentro de la función)

* `momentum(precio: pd.Series, dias: int) -> pd.Series`: `precio /
  precio.shift(dias) - 1`. `NaN` si `precio.shift(dias)` es `NaN`
  (historia insuficiente).
* `distancia_sma(precio: pd.Series, ventana: int) -> pd.Series`:
  `sma = precio.rolling(ventana, min_periods=ventana).mean()`;
  resultado = `precio / sma - 1`. `NaN` antes de completar la ventana.
* `cruce_sma(precio: pd.Series, ventana_corta: int, ventana_larga: int)
  -> pd.Series`: `bool`. `True` si
  `sma(ventana_corta) > sma(ventana_larga)` (estado "golden cross", no
  el momento exacto del cruce), `False` si es menor o igual. `NaN`
  (como `pd.NA`, la Serie queda `dtype="boolean"` nullable) si
  cualquiera de las dos SMA no está completa.
* `atr(alto: pd.Series, bajo: pd.Series, cierre: pd.Series, ventana:
  int) -> pd.Series`: rango verdadero `TR = max(alto-bajo,
  |alto-cierre.shift(1)|, |bajo-cierre.shift(1)|)` fila por fila;
  `ATR = TR.rolling(ventana, min_periods=ventana).mean()`. La primera
  fila de `TR` (sin `cierre.shift(1)`) usa solo `alto-bajo` — `NaN` en
  `ATR` hasta completar la ventana de todas formas.
* `volatilidad_realizada(precio: pd.Series, ventana: int) ->
  pd.Series`: igual fórmula que `prl.growth_max.signals` de EXP-002 —
  retornos diarios `precio.pct_change()`,
  `std = retornos.rolling(ventana, min_periods=ventana).std(ddof=1)`,
  resultado `= std * sqrt(252)`. `NaN` antes de completar la ventana.
* `volumen_relativo(volumen: pd.Series, ventana: int) -> pd.Series`:
  `volumen / volumen.rolling(ventana, min_periods=ventana).mean()`.
  `NaN` antes de completar la ventana, o si el promedio es `0`.
* `volume_spike_zscore(volumen: pd.Series, ventana_corta: int,
  ventana_larga: int) -> pd.Series`:
  `media_corta = volumen.rolling(ventana_corta, min_periods=ventana_corta).mean()`,
  `media_larga = volumen.rolling(ventana_larga, min_periods=ventana_larga).mean()`,
  `sd_larga = volumen.rolling(ventana_larga, min_periods=ventana_larga).std(ddof=1)`.
  Resultado `= (media_corta - media_larga) / sd_larga`. `NaN` si
  `sd_larga` es `0` o `NaN`, o antes de completar `ventana_larga`
  (la ventana larga manda: si no está completa, `NaN` aunque la corta
  sí lo esté).
* `rsi(precio: pd.Series, ventana: int) -> pd.Series`: RSI simple (NO
  el suavizado de Wilder — se declara explícitamente para que el test
  sea reproducible a mano). `diff = precio.diff()`,
  `ganancia = diff.clip(lower=0)`, `perdida = (-diff).clip(lower=0)`,
  `media_ganancia = ganancia.rolling(ventana, min_periods=ventana).mean()`,
  `media_perdida = perdida.rolling(ventana, min_periods=ventana).mean()`.
  Casos: si `media_perdida > 0` → `100 - 100/(1 + media_ganancia/media_perdida)`;
  si `media_perdida == 0` y `media_ganancia > 0` → `100.0` (solo subidas
  en la ventana); si `media_perdida == 0` y `media_ganancia == 0` →
  `50.0` (precio plano, sin cambio — señal neutral declarada, no
  indefinida). `NaN` antes de completar la ventana.
* `drawdown_previo(precio: pd.Series, ventana: int) -> pd.Series`:
  `maximo = precio.rolling(ventana, min_periods=ventana).max()`;
  resultado `= precio / maximo - 1` (≤ 0 siempre que no sea `NaN`).
  `NaN` antes de completar la ventana.
* `gap(apertura: pd.Series, cierre: pd.Series) -> pd.Series`:
  `apertura / cierre.shift(1) - 1`. `NaN` en la primera fila.
* `fuerza_relativa(precio: pd.Series, precio_benchmark: pd.Series,
  dias: int) -> pd.Series`: `momentum(precio, dias) -
  momentum(precio_benchmark, dias)`, ambas series ya alineadas al
  mismo índice antes de llamar la función (no reindexa internamente).
  `NaN` si cualquiera de los dos momentums es `NaN`.
* `beta(precio: pd.Series, precio_benchmark: pd.Series, ventana: int)
  -> pd.Series`: `r = precio.pct_change()`, `r_b =
  precio_benchmark.pct_change()` (ambas ya alineadas). `cov =
  r.rolling(ventana, min_periods=ventana).cov(r_b)`, `var =
  r_b.rolling(ventana, min_periods=ventana).var(ddof=1)`. Resultado
  `= cov / var`. `NaN` si `var` es `0` o `NaN`, o antes de completar la
  ventana.
* `sharpe_reciente(precio: pd.Series, ventana: int) -> pd.Series`:
  `r = precio.pct_change()`, `media = r.rolling(ventana,
  min_periods=ventana).mean()`, `sd = r.rolling(ventana,
  min_periods=ventana).std(ddof=1)`. Resultado `= media / sd *
  sqrt(252)`. `NaN` si `sd` es `0` o `NaN`.
* `distancia_extremo(precio: pd.Series, ventana: int, tipo:
  Literal["max", "min"]) -> pd.Series`: si `tipo="max"`, `extremo =
  precio.rolling(ventana, min_periods=ventana).max()`; si `tipo="min"`,
  `.min()` en vez de `.max()`. Resultado `= precio / extremo - 1`.
  `NaN` antes de completar la ventana. `ValueError` si `tipo` no es
  `"max"` ni `"min"` (único caso donde esta familia de funciones lanza
  una excepción en vez de devolver `NaN`, porque es un error de
  programación del llamador, no un dato insuficiente).
* `aceleracion(precio: pd.Series, dias_corto: int, dias_largo: int) ->
  pd.Series`: `momentum(precio, dias_corto) - momentum(precio,
  dias_largo)`.

### Ensamblador — features nombradas con los parámetros exactos del pre-registro

* `calcular_features_simbolo(df: pd.DataFrame, df_benchmark: pd.DataFrame)
  -> pd.DataFrame`. `df` tiene columnas `["open", "high", "low",
  "close", "volume"]`, índice de fechas ya ordenado ascendente; `df_benchmark`
  mismas columnas, **ya alineado al índice de `df`** (el llamador
  reindexa antes de invocar esta función — aquí no se reindexa, un
  índice distinto es un error de uso, no se intenta corregir en
  silencio). Devuelve un `DataFrame` con el mismo índice que `df` y
  EXACTAMENTE estas 20 columnas, calculadas con los bloques de arriba y
  los parámetros ya fijados en `PREREGISTRATION.md` (nunca
  configurables desde fuera de esta función — si el pre-registro
  cambiara el parámetro, este es el único lugar que se edita):

  | Columna | Construida con |
  |---|---|
  | `mom_5d` | `momentum(close, 5)` |
  | `mom_10d` | `momentum(close, 10)` |
  | `mom_20d` | `momentum(close, 20)` |
  | `dist_sma20` | `distancia_sma(close, 20)` |
  | `dist_sma50` | `distancia_sma(close, 50)` |
  | `dist_sma200` | `distancia_sma(close, 200)` |
  | `golden_cross` | `cruce_sma(close, 50, 200)` |
  | `atr14` | `atr(high, low, close, 14)` |
  | `vol_realizada_20d` | `volatilidad_realizada(close, 20)` |
  | `vol_relativo_20d` | `volumen_relativo(volume, 20)` |
  | `volume_spike_z` | `volume_spike_zscore(volume, 5, 60)` |
  | `rsi14` | `rsi(close, 14)` |
  | `drawdown_60d` | `drawdown_previo(close, 60)` |
  | `gap` | `gap(open, close)` |
  | `fuerza_relativa_20d` | `fuerza_relativa(close, df_benchmark["close"], 20)` |
  | `beta_60d` | `beta(close, df_benchmark["close"], 60)` |
  | `sharpe_20d` | `sharpe_reciente(close, 20)` |
  | `dist_max20` | `distancia_extremo(close, 20, "max")` |
  | `dist_min20` | `distancia_extremo(close, 20, "min")` |
  | `aceleracion` | `aceleracion(close, 5, 20)` |

### Elegibilidad y corte cross-sectional

* `universo_elegible(universo: dict[str, pd.DataFrame], fecha:
  pd.Timestamp, min_historia: int = 252) -> list[str]`: un símbolo es
  elegible en `fecha` si tiene al menos `min_historia` filas con índice
  `<= fecha` (cuenta la propia fecha si existe ese día). Devuelve la
  lista de símbolos elegibles, **ordenada alfabéticamente** (orden
  determinista, no el orden de inserción del diccionario de entrada).
* `features_cross_sectional(universo: dict[str, pd.DataFrame],
  benchmark: pd.DataFrame, fecha: pd.Timestamp, min_historia: int =
  252) -> pd.DataFrame`: para cada símbolo de `universo_elegible(...)`,
  recorta su historia a `<= fecha`, reindexa `benchmark` a ese mismo
  índice recortado (`benchmark.reindex(df.index)` — sin relleno hacia
  adelante, si el benchmark no tiene un dato en una fecha del símbolo
  queda `NaN` ese día, se declara así), llama
  `calcular_features_simbolo`, y toma la ÚLTIMA fila (la de `fecha` o
  la fecha disponible más cercana `<= fecha`). Devuelve un
  `DataFrame` indexado por símbolo (índice = los símbolos elegibles,
  mismo orden alfabético), columnas = las 20 de arriba, valores =
  crudos (sin normalizar todavía).

### Normalización y discriminación

* `normalizar_percentil_cross_sectional(features_crudas: pd.DataFrame)
  -> pd.DataFrame`: por columna, `columna.rank(pct=True)` — igual
  convención que `cross_sectional_momentum.py` de
  `algo_trading_platform` (ADR 0034): `rank(pct=True)` ignora `NaN`
  automáticamente (un símbolo con `NaN` en una columna queda `NaN` en
  esa columna normalizada, no se excluye de las demás columnas).
* `discriminacion_features(features_crudas: pd.DataFrame, es_ganador:
  pd.Series) -> pd.DataFrame`: `es_ganador` es `bool`, mismo índice
  (símbolos) que `features_crudas`. Para cada columna: descarta pares
  con `NaN` en esa columna antes de comparar (no afecta a las demás
  columnas); `diferencia_medianas = mediana(columna donde
  es_ganador=True) - mediana(columna donde es_ganador=False)`;
  `correlacion_punto_biserial = correlación de Pearson entre
  es_ganador.astype(float) y la columna` (sobre los pares no-`NaN`).
  Si después de descartar `NaN` quedan menos de 2 valores en cualquiera
  de los dos grupos (ganadores o no-ganadores), esa columna da `NaN` en
  ambas métricas — nunca una correlación calculada sobre un solo punto.
  Devuelve un `DataFrame` indexado por nombre de columna (= nombre de
  feature), con columnas `["diferencia_medianas",
  "correlacion_punto_biserial", "n_ganadores", "n_no_ganadores"]`,
  **ordenado por `|correlacion_punto_biserial|` descendente** (los
  `NaN` al final), con empates exactos desempatados alfabéticamente por
  nombre de feature (orden determinista).
* `features_discriminantes(discriminacion: pd.DataFrame, umbral: float
  = 0.05, max_features: int = 5) -> list[str]`: filtra las filas con
  `|correlacion_punto_biserial| >= umbral` (excluye `NaN`), toma como
  máximo las primeras `max_features` de ese subconjunto YA ordenado por
  `discriminacion_features` (no reordena), devuelve la lista de
  nombres de columna en ese mismo orden.

### Casos de prueba obligatorios

1. **Historia insuficiente** en cada bloque con ventana (`momentum`,
   `distancia_sma`, `atr`, `volatilidad_realizada`, `volumen_relativo`,
   `volume_spike_zscore`, `rsi`, `drawdown_previo`, `beta`,
   `sharpe_reciente`, `distancia_extremo`): `NaN` en todas las filas
   antes de completar la ventana más larga que usa, valor no-`NaN` en
   la primera fila donde se completa.
2. **`cruce_sma`**: una serie con SMA50 claramente por encima de SMA200
   da `True`; el caso inverso da `False`; antes de completar SMA200 da
   `NaN`/`pd.NA`.
3. **`rsi`**: una serie estrictamente creciente en la ventana da
   `100.0` (solo ganancias); una estrictamente decreciente da `0.0`
   (perdida media > 0, ganancia media = 0 → `100 - 100/(1+0) = 0`);
   una serie perfectamente plana da `50.0` exacto (no `NaN`, no
   excepción de división entre cero).
4. **`volume_spike_zscore`**: una serie de volumen constante (sd=0) da
   `NaN`, no `inf` ni excepción.
5. **`distancia_extremo`** con `tipo` inválido (ej. `"maximo"`) lanza
   `ValueError`.
6. **`calcular_features_simbolo`** con una serie sintética de ≥260
   filas (para que las 20 columnas tengan al menos una fila no-`NaN`)
   devuelve exactamente esas 20 columnas, en ese orden, sin columnas de
   más ni de menos.
7. **`universo_elegible`**: con 3 símbolos sintéticos (uno con 300
   filas, uno con 100, uno con exactamente 252) antes de una fecha de
   corte dada, devuelve solo los que cumplen `>= 252`, ordenados
   alfabéticamente.
8. **`features_cross_sectional`**: con 3 símbolos sintéticos de
   historia suficiente, devuelve un DataFrame con esos 3 símbolos como
   índice (orden alfabético) y las 20 columnas; un símbolo sin dato
   exacto en `fecha` (pero con una fecha anterior cercana) usa esa
   fecha anterior, no lanza excepción ni inventa un valor.
9. **`normalizar_percentil_cross_sectional`**: con una columna `[10,
   20, NaN, 30]` da percentiles `[0.333, 0.667, NaN, 1.0]`
   (aproximado, `rank(pct=True)` estándar de pandas) — el `NaN` se
   queda `NaN`, no cuenta en el denominador del percentil de las demás
   filas.
10. **`discriminacion_features`**: con una columna sintética donde los
    "ganadores" (`es_ganador=True`) tienen valores claramente más altos
    que los "no-ganadores", la `diferencia_medianas` sale positiva y
    `correlacion_punto_biserial` sale positiva y alta (> 0.5); con una
    columna de puro ruido sin relación con `es_ganador`, la correlación
    sale cerca de `0`; con menos de 2 valores no-`NaN` en el grupo de
    ganadores, esa fila da `NaN` en ambas métricas, no lanza excepción.
11. **`features_discriminantes`**: con una tabla de discriminación
    sintética de 8 features donde 3 superan el umbral de `0.05` y el
    resto no, devuelve exactamente esas 3 (o menos si `max_features`
    es menor), en el mismo orden que llegaron ya ordenadas, nunca más
    de `max_features` aunque más columnas superen el umbral.

Todas las series de prueba son sintéticas, construidas a mano (sin red,
sin datos reales) — mismo criterio que el resto del contrato.

## `prl.reverse_winners.grid`

Implementa el paso 4 ("Grilla de buckets candidatos") de la sección
*Metodología* de `PREREGISTRATION.md`. Tests en
`tests/reverse_winners/test_reverse_winners_grid.py`. Solo `itertools`,
`typing`, `dataclasses` (no necesita `pandas`/`numpy` salvo
`aplicar_bucket`, que sí recibe un `DataFrame`). Funciones puras.

* `direccion_features(discriminacion: "pd.DataFrame", features: list[str])
  -> dict[str, str]`: `discriminacion` es el `DataFrame` que devuelve
  `prl.reverse_winners.features.discriminacion_features` (indexado por
  nombre de feature, columna `diferencia_medianas`). Para cada nombre en
  `features`, `"alto"` si `discriminacion.loc[nombre,
  "diferencia_medianas"] > 0` (los ganadores tienen el valor MÁS alto en
  esa feature), `"bajo"` en caso contrario (`<= 0`, incluido el caso
  exacto `0.0` — no hay un tercer caso).
* `UMBRALES: list[float] = [0.60, 0.75, 0.90]` (percentiles cross-sectional,
  de menos a más exigente, fijos — no se exploran otros valores).
* `build_grid(features_ordenadas: list[str], direcciones: dict[str, str])
  -> list[dict]`: `features_ordenadas` tiene como máximo 5 elementos,
  todos presentes como llaves de `direcciones` (valores `"alto"` o
  `"bajo"`). Si `features_ordenadas` está vacía, devuelve `[]` (grilla
  vacía — no hay feature discriminante, no hay bucket que construir).
  En caso contrario, usa `itertools.product(*([UMBRALES] *
  len(features_ordenadas)))` para enumerar las combinaciones — el
  **último** elemento de `features_ordenadas` avanza más rápido
  (semántica estándar de `itertools.product`, el primer argumento es el
  "dígito" más significativo). Cada combinación produce un `dict`:
  `{"variant_id": str, "umbrales": {feature: {"direccion": "alto"|"bajo",
  "percentil": float}}}`, con `umbrales` conteniendo una entrada por
  cada feature de `features_ordenadas`, en ese mismo orden de inserción.
  `variant_id = "|".join(f"{feat}:{direcciones[feat]}:{p:.2f}" for feat, p
  in zip(features_ordenadas, combinacion))`. Tamaño total:
  `3 ** len(features_ordenadas)` (máximo 243 si hay 5 features).
* `aplicar_bucket(variant: dict, features_percentil: "pd.DataFrame") ->
  "pd.Series"`: `features_percentil` ya viene normalizada por percentil
  cross-sectional (salida de
  `normalizar_percentil_cross_sectional`), indexada por símbolo. Para
  cada `feature, info` en `variant["umbrales"].items()`: si
  `info["direccion"] == "alto"`, condición = `features_percentil[feature]
  >= info["percentil"]`; si `"bajo"`, condición = `features_percentil[
  feature] <= (1 - info["percentil"])`. El resultado es el **AND** de
  todas las condiciones (si `variant["umbrales"]` está vacío, el AND
  vacío es `True` para todos los símbolos — caso que en la práctica
  `build_grid` nunca produce, pero la función no lo rechaza). Un `NaN`
  en `features_percentil[feature]` para un símbolo hace que esa
  condición sea `False` para ese símbolo (comparación estándar de
  pandas con `NaN`, sin manejo especial adicional) — un símbolo con una
  feature faltante queda excluido del bucket, no incluido "por si
  acaso". Devuelve una `Series` booleana con el mismo índice que
  `features_percentil`.

### Casos de prueba obligatorios

1. **`direccion_features`**: tabla sintética con feature `"A"`
   (`diferencia_medianas=0.1`) y `"B"` (`diferencia_medianas=-0.2`) →
   `{"A": "alto", "B": "bajo"}`; una feature con `diferencia_medianas`
   exactamente `0.0` da `"bajo"`.
2. **`build_grid([], {})`** da `[]`.
3. **`build_grid` con 2 features** (`["A", "B"]`,
   `{"A": "alto", "B": "bajo"}`) da exactamente 9 variantes, todas con
   `variant_id` únicos; el primer elemento es
   `{"variant_id": "A:alto:0.60|B:bajo:0.60", "umbrales": {"A":
   {"direccion": "alto", "percentil": 0.60}, "B": {"direccion": "bajo",
   "percentil": 0.60}}}`; el segundo elemento tiene `B` en `0.75` y `A`
   sigue en `0.60` (confirma que `B`, el último de la lista, avanza más
   rápido); el último elemento tiene ambos en `0.90`.
4. **`build_grid` con 5 features** da exactamente 243 variantes, todas
   con `variant_id` únicos (`len(set(...)) == 243`).
5. **`aplicar_bucket`**: tabla de percentiles sintética de 5 símbolos
   con 2 columnas (`"A"`, `"B"`); variante que exige `A: alto, 0.75` Y
   `B: bajo, 0.60` → selecciona exactamente los símbolos donde
   `A >= 0.75` y `B <= 0.40`, verificado símbolo por símbolo; un
   símbolo con `NaN` en `A` queda excluido aunque cumpla `B`; con
   `variant["umbrales"] == {}`, selecciona a todos los símbolos
   (`True` en toda la Serie).

Todas las tablas de prueba son sintéticas, construidas a mano.

## `prl.reverse_winners.baselines`

Implementa la sección *Baselines* de `PREREGISTRATION.md`. Tests en
`tests/reverse_winners/test_reverse_winners_baselines.py`. Solo
`pandas`/`numpy`/`typing`. Funciones puras, todas devuelven `pd.Series`
booleana (símbolo seleccionado o no), mismo índice que su entrada
principal — mismo tipo de salida que `aplicar_bucket`, para que el
orquestador las trate de forma uniforme.

* `baseline_momentum_simple(features_percentil: pd.DataFrame, pct:
  float = 0.20) -> pd.Series`: Top `pct` por `features_percentil[
  "mom_20d"]` — selecciona donde `mom_20d >= (1 - pct)` (percentil ya
  normalizado, igual convención que `aplicar_bucket`). **Este es el
  baseline que de verdad importa** (ver pre-registro): un solo factor,
  sin combinar nada más.
* `baseline_buy_hold(simbolos_elegibles: list[str]) -> pd.Series`:
  `True` para todos los símbolos de `simbolos_elegibles`, indexado por
  esa misma lista (en ese orden).
* `baseline_rsi_simple(features_percentil: pd.DataFrame, pct: float =
  0.10) -> pd.Series`: Top `pct` por RSI **más bajo** — selecciona
  donde `features_percentil["rsi14"] <= pct`. Mean-reversion puro,
  dirección opuesta al experimento — referencia de contraste, no se
  espera que gane.
* `baseline_combo_ingenuo(features_crudas: pd.DataFrame) -> pd.Series`:
  umbrales fijos sobre valores **crudos** (no percentiles — a
  diferencia de los tres anteriores, a propósito, ver pre-registro):
  `(features_crudas["mom_20d"] > 0) & (features_crudas["dist_sma50"] >
  0) & (features_crudas["vol_relativo_20d"] > 1.2)`. Comparación
  estricta (`>`, no `>=`) en los tres casos. Un `NaN` en cualquiera de
  las tres columnas para un símbolo da `False` para ese símbolo (sin
  manejo especial — comparación estándar de pandas con `NaN`).

### Casos de prueba obligatorios

1. **`baseline_momentum_simple`**: columna `mom_20d` sintética de 10
   símbolos con percentiles conocidos (`0.05, 0.15, ..., 0.95`),
   `pct=0.20` → selecciona exactamente los 2 símbolos con percentil
   `>= 0.80` (`0.85` y `0.95`), verificado por nombre.
2. **`baseline_buy_hold`**: con `simbolos_elegibles = ["AAA", "BBB",
   "CCC"]`, devuelve una Serie de 3 `True`, índice exactamente esos 3
   símbolos en ese orden.
3. **`baseline_rsi_simple`**: columna `rsi14` percentil sintética,
   `pct=0.10` → selecciona exactamente el/los símbolos con percentil
   `<= 0.10`.
4. **`baseline_combo_ingenuo`**: tabla cruda sintética de 5 símbolos
   que cubre los 4 casos: cumple los 3 umbrales (`True`); falla
   exactamente uno de los 3 (`False`); los 3 valores exactamente en el
   límite (`mom_20d=0.0`, `dist_sma50=0.0`, `vol_relativo_20d=1.2`) →
   `False` en los tres (comparación estricta); un `NaN` en una de las
   tres columnas → `False` sin excepción.

Todas las tablas de prueba son sintéticas, construidas a mano.

## `prl.reverse_winners.evaluation`

Implementa la sección *Validación y robustez* y *Criterios de éxito*
de `PREREGISTRATION.md`. Tests en
`tests/reverse_winners/test_reverse_winners_evaluation.py`. Solo
`pandas`/`numpy`/`scipy.stats`/`typing`/`itertools`/`math`. Sin red,
sin archivos, sin variables de entorno. Funciones puras. **No importa
`prl.growth_max` ni `prl.emergency`** — las fórmulas compartidas
(bootstrap de bloques, Deflated Sharpe, placebo) se reimplementan aquí,
mismo criterio que `composite_score` en EXP-002.

Aclaración importante de granularidad (distinta a EXP-001/EXP-002):
aquí las "series de retornos" que entran a estas funciones **no son
retornos diarios de una curva de equity continua** — son series
indexadas por fecha de corte T0 (una observación cada 10 sesiones
hábiles, ver pre-registro), donde cada valor es el retorno forward 30d
promedio (equal-weight) de los símbolos seleccionados ese T0 por un
bucket/baseline dado. `tamano_bloque` en estas funciones cuenta
**observaciones T0 consecutivas**, no días de calendario — se declara
así explícitamente para que no se confunda con la convención de
EXP-002.

* `bootstrap_bloques(retornos: pd.DataFrame, tamano_bloque: int,
  n_replicas: int, seed: int) -> np.ndarray`: idéntica lógica que
  `prl.growth_max.evaluation.bootstrap_bloques_retornos` (bootstrap de
  bloques pareado entre columnas: con `rng =
  np.random.default_rng(seed)`, cada réplica concatena
  `ceil(n/tamano_bloque)` bloques de `tamano_bloque` filas consecutivas
  —inicio uniforme en `[0, n - tamano_bloque]`—, recortado a `n` filas;
  la misma selección de bloques aplica a todas las columnas de una
  réplica). Devuelve `(n_replicas, n, n_columnas)`. `ValueError` si
  `n < tamano_bloque`.
* `comparacion_bootstrap(ret_bucket: pd.Series, ret_baseline: pd.Series,
  tamano_bloque: int = 2, n_replicas: int = 10000, seed: int = 0, alpha:
  float = 0.05) -> dict`: ambas series comparten el mismo índice
  (`ValueError` si no). Usa `bootstrap_bloques` con ambas como columnas
  (pareado). Para cada réplica, la métrica es la **media simple** de
  cada columna remuestreada (no CAGR compuesto — no aplica aquí, estas
  no son observaciones diarias que se compongan geométricamente).
  Devuelve `{"ci_media_bucket": (percentil alpha/2, percentil
  1-alpha/2), "frac_supera_baseline": fracción de réplicas donde
  media_bucket_replica > media_baseline_replica}` (`>` estricto).
* `deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float`:
  **fórmula idéntica** a
  `prl.growth_max.evaluation.deflated_sharpe_ratio` (= la de
  `prl.emergency.evaluation` de EXP-001): `n = len(returns)`, `sr` =
  media/desviación (`ddof=1`) de `returns` sin anualizar, `g3 =
  returns.skew()`, `g4 = returns.kurt() + 3`, `sr_std =
  sqrt((1 - g3·sr + (g4-1)/4·sr²) / (n-1))`. Si `n_trials <= 1`:
  `sr0 = 0`; si no, `γ = 0.5772156649015329`, `N = n_trials`, `sr0 =
  sr_std · ((1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e)))`
  (`Φ⁻¹ = scipy.stats.norm.ppf`). Resultado: `Φ((sr - sr0)/sr_std)`
  (`scipy.stats.norm.cdf`).
* `probabilidad_backtest_overfitting(matriz_desempeno: pd.DataFrame,
  n_particiones: int = 10) -> float`: CSCV (Combinatorially Symmetric
  Cross-Validation, Bailey et al. 2014). `matriz_desempeno`: filas =
  períodos (sin huecos, orden temporal ya dado por el índice), columnas
  = `variant_id`, valores = desempeño medio de esa variante en ese
  período (sin `NaN` — el orquestador ya agregó antes de llamar esta
  función). `ValueError` si `n_particiones` es impar o `< 2`, o si
  `len(matriz_desempeno) < n_particiones`. Pasos, **deterministas, sin
  aleatoriedad** (CSCV enumera, no muestrea):
  1. Divide las filas en `n_particiones` bloques contiguos de tamaño
     igual `tam = len(matriz_desempeno) // n_particiones` (si no es
     divisible exacto, las últimas `len(matriz_desempeno) % tam` filas
     sobrantes se descartan, no entran a ningún bloque — se declara así
     para que el comportamiento sea exacto y testeable).
  2. Para cada combinación `C` en
     `itertools.combinations(range(n_particiones), n_particiones // 2)`
     (entrenamiento = unión de los bloques en `C`, prueba = unión del
     resto): `desempeno_is = matriz_desempeno.iloc[filas de
     entrenamiento].mean()` (por columna); `variante_elegida` = la
     columna con mayor `desempeno_is` (empate exacto → la primera en
     orden alfabético de `variant_id`); `desempeno_oos =
     matriz_desempeno.iloc[filas de prueba].mean()` (por columna);
     `rho = desempeno_oos.rank(pct=True)[variante_elegida]` (misma
     convención `rank(pct=True)` que el resto del proyecto, método
     `"average"` por defecto de pandas ante empates); recorta `rho` a
     `[epsilon, 1-epsilon]` con `epsilon = 1 / (2 · n_variantes)` (evita
     `logit` infinito); `logit_C = ln(rho / (1 - rho))`.
  3. `PBO = fracción de combinaciones C donde logit_C <= 0` (empate en
     `0` cuenta como sobreajuste — regla conservadora, declarada).
  Devuelve el `float` de `PBO` (en `[0, 1]`).
* `concentracion_maxima(senales: pd.DataFrame) -> dict`: `senales`
  tiene una fila por señal (una combinación fecha×símbolo seleccionada
  por un bucket/baseline en un split dado), columna `"ticker"`.
  Devuelve `{"frac_max_ticker": float, "ticker_max": str}` — la
  fracción de filas que corresponde al ticker más frecuente (empate
  exacto en el conteo → el ticker que sea alfabéticamente primero).
  Si `senales` está vacío, `{"frac_max_ticker": 0.0, "ticker_max":
  None}`.
* `leave_one_ticker_out_signo(senales: pd.DataFrame, columna_retorno:
  str = "retorno_30d") -> dict`: `senales` tiene columnas `"ticker"` y
  `columna_retorno`. `signo_original = sign(media(columna_retorno))`
  (`1`/`-1`/`0`). Para cada ticker único, recalcula la media excluyendo
  **todas** sus filas y su signo; `reversiones` = conteo de tickers
  donde ese signo recalculado es opuesto al `signo_original` (el caso
  `0` nunca se considera opuesto a nada, ni él mismo). Devuelve
  `{"signo_original": int, "n_tickers": int, "reversiones": int,
  "revierte_con_algun_ticker": bool}` (`True` si `reversiones > 0`).
* `placebo_aleatorio(pool_retornos: pd.Series, n_senales: int,
  n_placebos: int = 1000, seed: int = 0) -> np.ndarray`: `pool_retornos`
  es la serie plana de retornos forward 30d de **todas** las señales
  elegibles (fecha×símbolo) del split, sin estructura de bucket.
  `rng = np.random.default_rng(seed)`; en cada placebo, muestrea
  `n_senales` valores de `pool_retornos` **sin reemplazo**
  (`rng.choice(pool_retornos.to_numpy(), size=n_senales,
  replace=False)`) y calcula su media. Devuelve `(n_placebos,)`.
  `ValueError` si `n_senales > len(pool_retornos)` o `n_senales <= 0`.
* `percentil_real_vs_placebo(valor_real: float, placebos: np.ndarray)
  -> float`: idéntica a `prl.growth_max.evaluation` — fracción de
  `placebos` que son `<= valor_real` (incluye empates); `0.0` si
  `placebos` está vacío.
* `etiqueta(supera_los_4_baselines: bool, frac_bootstrap_vs_baseline1:
  float, dsr: float, n_senales_locked: int, frac_max_ticker: float,
  vecino_revierte_signo: bool, vecino_destruye_mas_50pct: bool,
  placebo_distingue: bool | None) -> str`: aplica el orden de prioridad
  de los *Criterios de éxito* del pre-registro, nunca lanza excepción
  por un `NaN` numérico (cuenta como "no cumple" esa comparación
  específica):
  1. `REJECTED` si `frac_bootstrap_vs_baseline1 <= 0.5` **o** `dsr <=
     0.5` **o** `frac_max_ticker > 0.20` **o** `placebo_distingue is
     False` (si `placebo_distingue is None` —potencia no confirmada—
     esta sub-condición NO aplica, no cuenta como rechazo por sí sola).
  2. `VALIDATED` si, no habiendo caído en 1: `supera_los_4_baselines`
     **y** `frac_bootstrap_vs_baseline1 >= 0.80` **y** `dsr > 0.95`
     **y** `not vecino_revierte_signo` **y** `not
     vecino_destruye_mas_50pct` **y** `frac_max_ticker <= 0.20` **y**
     `n_senales_locked >= 20`.
  3. `INCONCLUSIVE` en cualquier otro caso.

### Casos de prueba obligatorios

1. **`bootstrap_bloques`**: forma `(n_replicas, n, n_columnas)`; mismo
   `seed` → resultados idénticos; `n < tamano_bloque` → `ValueError`;
   pareado (una fila remuestreada de la réplica *r* corresponde a la
   misma posición original en ambas columnas).
2. **`comparacion_bootstrap`**: `ret_bucket` idéntico a `ret_baseline`
   → `frac_supera_baseline == 0.0`; `ret_bucket` uniformemente mayor
   cada período → `frac_supera_baseline == 1.0`; índices distintos →
   `ValueError`.
3. **`deflated_sharpe_ratio`**: con `n_trials=1`, coincide con
   `Φ(sr/sr_std)` calculado a mano sobre una serie sintética simple;
   aumentar `n_trials` nunca aumenta el resultado.
4. **`probabilidad_backtest_overfitting`**: `n_particiones` impar →
   `ValueError`; matriz sintética de "habilidad genuina" (una columna
   domina en TODOS los períodos, sin excepción, sobre las demás) con
   `n_particiones=4` → `PBO == 0.0`; matriz sintética adversarial
   (construida a mano para que la columna ganadora in-sample en cada
   combinación sea sistemáticamente la peor out-of-sample) con
   `n_particiones=4` → `PBO == 1.0`; misma entrada dos veces → mismo
   resultado exacto (sin aleatoriedad).
5. **`concentracion_maxima`**: 100 filas sintéticas donde un ticker
   aparece 25 veces → `frac_max_ticker == 0.25`, `ticker_max` correcto;
   `senales` vacío → `{"frac_max_ticker": 0.0, "ticker_max": None}`;
   empate exacto entre dos tickers → gana el alfabéticamente primero.
6. **`leave_one_ticker_out_signo`**: datos sintéticos donde quitar un
   ticker específico revierte el signo → `revierte_con_algun_ticker ==
   True`, `reversiones` correcto; datos robustos a quitar cualquier
   ticker → `False`, `reversiones == 0`.
7. **`placebo_aleatorio`**: forma `(n_placebos,)`; mismo `seed` →
   idéntico; `n_senales > len(pool_retornos)` → `ValueError`.
8. **`percentil_real_vs_placebo`**: con `placebos=[1,2,3,4,5]` y
   `valor_real=3` → `0.6`.
9. **`etiqueta`**: los tres niveles de prioridad probados por
   separado, incluido que `dsr=NaN` con todo lo demás cumpliendo
   `VALIDATED` da `INCONCLUSIVE` (no excepción); `placebo_distingue=
   None` con el resto en regla de `VALIDATED` NO cae en `REJECTED` por
   esa sola razón.

Todas las series/tablas de prueba son sintéticas, construidas a mano.
Los tests de bootstrap/placebo usan `n_replicas`/`n_placebos` chicos
(decenas) para que la suite corra rápido.

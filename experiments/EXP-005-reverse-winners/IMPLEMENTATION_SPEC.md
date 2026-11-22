# EXP-005 — Contrato de implementación (lo que debe cumplir el código)

## `prl.reverse_winners.features`

Implementa la sección "Metodología — ventanas rolling" de
`PREREGISTRATION.md` (pasos 2 y 3: features en T0 y discriminación
estadística). Tests en `tests/reverse_winners/test_features.py`.

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

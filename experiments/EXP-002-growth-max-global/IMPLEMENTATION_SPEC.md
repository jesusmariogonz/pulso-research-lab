# EXP-002 — Contrato de implementación (lo que debe cumplir el código)

Este documento y los tests correspondientes en `tests/` son el
**contrato**. El código de cada módulo debe hacerlos pasar sin tocarlos.
Implementa `PREREGISTRATION.md` (con las aclaraciones de implementación
de su *Registro de cambios*); si hay conflicto, manda el pre-registro.

## `prl.data.macro_vintage`

Ver `DATA_INFRA_MACRO_VINTAGE.md` para el porqué. Tests en
`tests/test_macro_vintage.py`.

Reglas transversales (iguales a EXP-001):
* **Sin look-ahead:** ninguna función puede devolver, para una fecha de
  corte *D*, información cuyo `realtime_start` sea posterior a *D*.
* Solo `pandas`, `numpy`, `typing`, `dataclasses`. **Sin red, sin
  archivos, sin variables de entorno** — la descarga real (con
  `FRED_API_KEY`) vive en `prl.data.build`, fuera de este contrato, y no
  se prueba aquí.
* Funciones puras, con tipos y docstring breve.
* **Nunca rellenar en silencio.** Un dato no publicado aún en la fecha de
  corte es `NaN` explícito, nunca el valor más reciente disponible ni 0.

## Forma de los datos de entrada

Un DataFrame de "vintages" (lo que devuelve, ya parseado, una llamada a
ALFRED con `output_type=1` y ventana de tiempo real completa) con
columnas:

* `obs_date` (`datetime64`): período que describe el dato.
* `value` (`float`): valor publicado para ese período, en esa versión.
* `realtime_start` (`datetime64`): desde cuándo esa versión fue la
  vigente.
* `realtime_end` (`datetime64`): hasta cuándo fue vigente (inclusive).
  Un valor todavía vigente usa `pd.Timestamp("9999-12-31")` (no `NaT`).

No está ordenado por ninguna columna en particular al entrar a las
funciones del módulo — las funciones no deben asumir orden.

## `parse_vintage_observations(raw: list[dict]) -> pd.DataFrame`

Convierte la respuesta cruda de la API (lista de dicts con claves de
texto `"date"`, `"value"`, `"realtime_start"`, `"realtime_end"`, como
las que entrega el JSON de ALFRED) al DataFrame de arriba.

* Parsea las tres fechas a `datetime64` y `value` a `float`.
* `value == "."` (código de FRED para "sin dato") → fila **excluida**
  del resultado (no `NaN`: una versión que no tenía valor publicado para
  ese período no es información, no entra).
* Filas con `realtime_start > realtime_end` → `ValueError`.
* Filas con `realtime_start` **anterior** a `obs_date` → `ValueError` (un
  valor no puede conocerse antes del período que describe; ver
  `validar_vintages` para el chequeo reutilizable). **No** hay límite
  superior en cuánto más tarde puede ser `realtime_start`: series macro
  como M2 o producción industrial se re-benchmarkean décadas después
  (cambios de metodología de la agencia que las publica) — una revisión
  real de un dato de 1960 publicada en 2020 es válida, no corrupta.
* Si `raw` está vacío → DataFrame vacío con las columnas correctas (no
  `KeyError`, no excepción).

## `validar_vintages(df: pd.DataFrame) -> list[str]`

Dado un DataFrame ya parseado (forma de arriba), devuelve la lista de
problemas encontrados (vacía = todo bien). No lanza excepciones, no
corrige nada — solo reporta, igual que `prl.data.validate.validar_serie`.
Revisa, por cada `obs_date`:

* `REALTIME_START_ANTES_DE_OBS_DATE`: alguna fila tiene
  `realtime_start < obs_date`.
* `VENTANAS_INCONSISTENTES`: para un mismo `obs_date`, al ordenar sus
  filas por `realtime_start` ascendente, dos ventanas consecutivas
  `[realtime_start_i, realtime_end_i]` y `[realtime_start_{i+1},
  realtime_end_{i+1}]` deben cubrir el tiempo sin superposición y sin
  hueco: `realtime_start_{i+1} == realtime_end_i + pd.Timedelta(days=1)`.
  Cualquier desviación (se superponen, o queda un día sin versión
  vigente entre una revisión y la siguiente) cuenta como un problema.
  Con una sola fila para ese `obs_date` no hay nada que comparar → no
  aplica.
* `OBS_DATE_SIN_VERSION_VIGENTE`: algún `obs_date` no tiene ninguna fila
  con `realtime_end == pd.Timestamp("9999-12-31")` (toda observación real
  debe tener una versión "actual" vigente).

Cada entrada de la lista es un string legible, p. ej.
`"CPI 2015-06-01: ventanas superpuestas"`. El formato exacto del mensaje
no se testea con igualdad estricta; los tests comprueban que el código
correcto aparezca como *substring* de al menos un elemento de la lista
(usar un prefijo en mayúsculas como los ejemplos de arriba, que sí se
testea).

## `ultimo_valor_conocido(df: pd.DataFrame, fecha_corte) -> dict`

`fecha_corte` es un `pd.Timestamp` o algo convertible con
`pd.Timestamp(...)`. Entre todas las filas con
`realtime_start <= fecha_corte <= realtime_end`, toma la de `obs_date`
más reciente (si hay empate en `obs_date`, la de `realtime_start` más
reciente). Devuelve:

```python
{"obs_date": pd.Timestamp | None, "value": float | None, "antiguedad_dias": int | None}
```

`antiguedad_dias = (fecha_corte - obs_date).days` (≥ 0 siempre, porque
`realtime_start >= obs_date`). Si ninguna fila cumple la condición
(nada publicado todavía en `fecha_corte`) → `{"obs_date": None, "value": None, "antiguedad_dias": None}`,
nunca `NaN` de punta a punta ni una excepción.

## `serie_conocida_en(df: pd.DataFrame, fechas_corte) -> pd.DataFrame`

Versión vectorizada de `ultimo_valor_conocido` sobre una secuencia de
fechas de corte (p. ej. todos los días de trading de un backtest).
`fechas_corte`: cualquier iterable convertible a `pd.DatetimeIndex`.

Devuelve un DataFrame indexado por `fechas_corte` (mismo orden que la
entrada, sin reordenar) con columnas `value`, `obs_date_origen`,
`antiguedad_dias` — `NaN`/`NaT` cuando `ultimo_valor_conocido` no
encontró nada. Debe dar exactamente los mismos valores que llamar
`ultimo_valor_conocido` fecha por fecha (los tests lo comprueban
cruzado); la vectorización es solo por rendimiento, no cambia la
semántica.

## Casos de prueba obligatorios (lo que `tests/test_macro_vintage.py` cubre)

1. **Reconstrucción básica de una revisión:** una serie con un
   `obs_date`, publicada primero con un valor y luego revisada a otro
   valor en una fecha posterior. Antes de la primera publicación → nada
   conocido. Entre la primera publicación y la revisión → el valor
   inicial. En o después de la revisión → el valor revisado.
2. **Frontera de look-ahead:** una fila con `realtime_start` **futuro**
   respecto a la fecha de corte consultada nunca debe aparecer en el
   resultado, aunque sea la fila de `obs_date` más reciente del
   DataFrame.
3. **Varios `obs_date`:** con varios períodos observados y sus propias
   revisiones, en una fecha de corte dada se debe elegir el `obs_date`
   más reciente *entre los ya conocidos*, no el más reciente del
   DataFrame completo.
4. **Nada conocido todavía:** fecha de corte anterior a cualquier
   `realtime_start` del DataFrame → resultado vacío/None, no excepción,
   no 0.
5. **Bordes inclusivos:** fecha de corte exactamente igual a
   `realtime_start` de una fila, y exactamente igual a su
   `realtime_end` → ambas cuentan como conocidas.
6. **`parse_vintage_observations`** con `value == "."` filtra esas filas;
   con filas corruptas (`realtime_start < obs_date`,
   `realtime_start > realtime_end`) lanza `ValueError`; con lista vacía
   devuelve DataFrame vacío con columnas correctas.
7. **`validar_vintages`** detecta cada uno de los cuatro problemas por
   separado (un DataFrame sintético por problema) y devuelve lista vacía
   para un DataFrame limpio de dos `obs_date` con una revisión cada uno.
8. **Consistencia vectorizada:** `serie_conocida_en` sobre 20 fechas de
   corte sintéticas da fila por fila lo mismo que `ultimo_valor_conocido`
   llamada individualmente.

Todos los DataFrames de prueba son **sintéticos**, construidos a mano en
el test (sin red, sin fixtures externas) — igual que los tests de
EXP-001 no descargan datos reales.

## `prl.growth_max.signals`

Implementa la sección *Señales* de `PREREGISTRATION.md` (incluida la
aclaración de implementación v1.1 sobre "régimen de rango"). Tests en
`tests/growth_max/test_signals.py`.

Reglas transversales (iguales a EXP-001):
* **Sin look-ahead:** el valor en la fecha *t* usa solo datos con fecha
  ≤ *t*. `rolling(..., min_periods=ventana)` en vez de `min_periods=1`
  en todos lados — antes de completar la ventana, `NaN`, nunca un valor
  calculado con menos datos de los que pide el parámetro.
* Solo `pandas`, `numpy`, `typing`, `dataclasses`. Sin red, sin archivos,
  sin variables de entorno.
* Funciones puras, con tipos y docstring breve. Todas devuelven
  `pd.Series`/`pd.DataFrame` con el mismo índice que la entrada principal.
* **Nunca rellenar en silencio:** `NaN` antes de tener ventana completa,
  nunca `0` ni el valor más reciente disponible.

### Señales direccionales (familias 1-3 del pre-registro)

* `ts_momentum_signal(precio: pd.Series, meses: int) -> pd.Series`:
  `ventana = meses * 21` (aproximación estándar de días hábiles por mes).
  `retorno = precio / precio.shift(ventana) − 1`. Señal: `1.0` si
  `retorno > 0`, `−1.0` si `retorno < 0`, `0.0` si `retorno == 0`
  exactamente. `NaN` si `precio.shift(ventana)` es `NaN` (historia
  insuficiente).
* `trend_signal(precio: pd.Series, ventana: int) -> pd.Series`:
  `sma = precio.rolling(ventana, min_periods=ventana).mean()`. Señal =
  signo de `precio / sma − 1` (misma convención `1.0/−1.0/0.0` de
  arriba). `NaN` antes de completar la ventana.
* `breakout_signal(precio: pd.Series, ventana: int) -> pd.Series`:
  `maximo = precio.rolling(ventana, min_periods=ventana).max()`,
  `minimo` análogo. `1.0` si `precio >= maximo` (este caso tiene
  prioridad si además `precio <= minimo`, es decir ventana con precio
  plano); si no, `−1.0` si `precio <= minimo`; si no, `0.0`. `NaN` antes
  de completar la ventana.

### Reversión y volatilidad (familias 4 y 6)

* `reversion_zscore(precio: pd.Series, ventana: int) -> pd.Series`:
  `media = precio.rolling(ventana, min_periods=ventana).mean()`,
  `sd = precio.rolling(ventana, min_periods=ventana).std(ddof=1)`.
  `z = (precio − media) / sd`. Si `sd` es `0` o `NaN` → `NaN` (nunca
  `inf`). `NaN` antes de completar la ventana.
* `senal_reversion(precio: pd.Series, ventana: int) -> pd.Series`: signo
  de `−reversion_zscore(precio, ventana)` (z alto = precio "caro" frente
  a su media reciente → la reversión apuesta a baja = señal `−1.0`; z
  bajo → `1.0`), misma convención `1.0/−1.0/0.0`/`NaN` que las señales
  direccionales. `0.0` solo si el z-score es exactamente `0`.
* `volatilidad_realizada(precio: pd.Series, ventana: int) -> pd.Series`:
  retornos simples diarios `precio.pct_change()`; `vol =
  retornos.rolling(ventana, min_periods=ventana).std(ddof=1) *
  sqrt(252)`. `NaN` antes de completar la ventana (incluye el primer
  `NaN` de `pct_change`).

### Combinación (igual patrón que `composite_score` de EXP-001)

* `composite_score(dims: pd.DataFrame, weights: dict[str, float]) ->
  pd.Series`: por fila, promedio ponderado **solo de las columnas
  disponibles** (no-`NaN`) de `dims`, con los pesos de `weights`
  renormalizados entre ellas. Si ninguna columna de esa fila está
  disponible → `NaN`. Columnas de `dims` sin peso en `weights` se
  ignoran. (Idéntica a `prl.emergency.features.composite_score`, pero
  este módulo no puede importar `prl.emergency` — se reimplementa aquí
  para no crear una dependencia cruzada entre experimentos.)

### Régimen macro (familia 5) — point-in-time, ya resuelto aguas arriba

Estas funciones reciben series **ya** point-in-time-correctas (el
resultado de `prl.data.macro_vintage.serie_conocida_en` alineado a días
de trading) — no vuelven a razonar sobre `realtime_start`/`realtime_end`.

* `signo_cambio_trailing(serie_conocida: pd.Series, dias: int) ->
  pd.Series`: `cambio = serie_conocida − serie_conocida.shift(dias)`.
  Señal `1.0`/`−1.0`/`0.0` (exacto) igual convención de arriba. `NaN` si
  `serie_conocida[t]` o `serie_conocida[t − dias]` es `NaN` (incluye el
  caso de que el dato todavía no existiera en esa fecha).
* `regimen_macro(liquidez_signo: pd.Series, crecimiento_signo: pd.Series)
  -> pd.Series`: ambos ya alineados al mismo índice. Por fila: `NaN` si
  cualquiera de los dos es `NaN` **o** si cualquiera es exactamente `0.0`
  (cambio trailing nulo — se trata como señal insuficiente, no como un
  tercer valor). Si no, régimen entero (`float`, para poder llevar `NaN`):
  `1.0` si `(liquidez=1, crecimiento=1)`; `2.0` si `(liquidez=1,
  crecimiento=−1)`; `3.0` si `(liquidez=−1, crecimiento=1)`; `4.0` si
  `(liquidez=−1, crecimiento=−1)`.
* `es_regimen_de_rango(regimen: pd.Series) -> pd.Series`: `bool`. `True`
  si `regimen ∈ {2.0, 3.0}`; `False` si `regimen ∈ {1.0, 4.0}` **o** si
  `regimen` es `NaN` (aclaración v1.1: sin régimen claro, el overlay
  quedas apagado, no se asume rango por defecto).

### Orquestación final

* `senal_compuesta_con_overlay(direccional: pd.Series, reversion: pd.Series,
  regimen_de_rango: pd.Series) -> pd.Series`: por fila, si
  `regimen_de_rango` es `True` → usa el valor de `reversion`; si no, usa
  el valor de `direccional`. Todas las series ya alineadas al mismo
  índice. Si el valor elegido para esa fila es `NaN`, el resultado es
  `NaN` (no se cae de vuelta al otro valor).

### Casos de prueba obligatorios

1. **Historia insuficiente:** cada señal (`ts_momentum_signal`,
   `trend_signal`, `breakout_signal`, `reversion_zscore`,
   `volatilidad_realizada`) da `NaN` en todas las filas antes de
   completar su ventana, y un valor no-`NaN` en la primera fila donde la
   ventana se completa.
2. **Signo correcto:** una serie de precios estrictamente creciente da
   `1.0` en momentum/trend/breakout (una vez hay ventana); una
   estrictamente decreciente da `−1.0`.
3. **Empate de breakout:** una ventana de precio perfectamente plano
   (todos los valores iguales) da `1.0`, no `−1.0` ni `0.0`.
4. **Reversión con desviación cero:** una ventana de precio plano no
   lanza excepción ni da `inf`; da `NaN`.
5. **`composite_score`** con una fila donde falta una de tres columnas
   promedia solo las otras dos con pesos renormalizados; con las tres
   disponibles promedia las tres; con ninguna disponible da `NaN`.
6. **`signo_cambio_trailing`** antes de `dias` observaciones da `NaN`;
   con una serie con un hueco de `NaN` en medio (p. ej. antes de la
   primera publicación de una serie macro), la fila que necesita ese
   hueco da `NaN`, no se salta ni se interpola.
7. **`regimen_macro`** da cada uno de los 4 regímenes con los signos de
   entrada correspondientes, `NaN` si cualquier entrada es `NaN`, y
   `NaN` si cualquier entrada es `0.0` exacto.
8. **`es_regimen_de_rango`** da `True` solo para régimen 2 o 3, `False`
   para 1, 4 y `NaN`.
9. **`senal_compuesta_con_overlay`** con `regimen_de_rango` mezclando
   `True`/`False` fila por fila elige la serie correcta en cada una, y
   propaga `NaN` cuando el valor elegido es `NaN` (incluso si el otro
   valor no lo es).

Todas las series de prueba son sintéticas, construidas a mano (sin red,
sin datos reales) — mismo criterio que el resto del contrato.

## `prl.growth_max.portfolio`

Implementa la sección *Construcción de portafolio y apalancamiento* de
`PREREGISTRATION.md`, con las aclaraciones v1.2. Tests en
`tests/growth_max/test_portfolio.py`.

Reglas transversales (iguales a los módulos anteriores de EXP-002): sin
look-ahead, solo `pandas`/`numpy`/`typing`/`dataclasses`, sin red/archivos/
variables de entorno, funciones puras, `NaN` explícito nunca relleno en
silencio. Todas las funciones de pesos reciben y devuelven `pd.DataFrame`
con índice = fechas, columnas = activos (mismo universo en todos los
argumentos de una llamada — quien orquesta ya los alineó).

### Métodos de construcción (gross ≤ 1.0 antes de apalancamiento, por fila)

* `pesos_equal(senales: pd.DataFrame) -> pd.DataFrame`: por fila, entre
  las columnas con `senales` no `NaN` y `!= 0` (cuenta `N`), peso =
  `signo(senal) / N`. Columnas sin señal válida esa fila → `0.0` (no es
  un dato faltante, es "sin posición"). Si `N == 0` esa fila, todos los
  pesos son `0.0`.
* `pesos_inv_vol(senales: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame`:
  válidas = `senales` no `NaN` y `!=0`, **y** `vol` no `NaN` y `> 0`.
  `crudo = signo(senal) / vol` en las válidas, `0.0` en el resto. Si
  `Σ|crudo| > 0` esa fila, `peso = crudo / Σ|crudo|` (gross = 1.0); si
  `Σ|crudo| == 0`, todos los pesos son `0.0`.
* `pesos_vol_target(senales, vol, objetivo: float) -> pd.DataFrame`: parte
  de `pesos_inv_vol(senales, vol)` (llamarla internamente, no duplicar la
  lógica). Por fila, `vol_portafolio_aprox = sqrt(Σ(peso_i² · vol_i²))`
  (ignora correlaciones a propósito — ver aclaración v1.2). `factor =
  objetivo / vol_portafolio_aprox` si `vol_portafolio_aprox > 0`, si no
  `factor = 0.0` (esa fila ya tiene todos los pesos en `0.0`). Peso final
  = `peso_inv_vol · factor`.
* `retorno_esperado_trailing(retornos: pd.DataFrame, ventana: int) ->
  pd.DataFrame`: `retornos.rolling(ventana, min_periods=ventana).mean()`
  por columna. `NaN` antes de completar la ventana.
* `varianza_trailing(retornos: pd.DataFrame, ventana: int) ->
  pd.DataFrame`: `retornos.rolling(ventana, min_periods=ventana).var(ddof=1)`
  por columna. `NaN` antes de completar la ventana.
* `pesos_kelly_frac(senales: pd.DataFrame, mu: pd.DataFrame, varianza:
  pd.DataFrame, fraccion: float, tope_posicion: float = 0.20) ->
  pd.DataFrame`: válidas = `senales` no `NaN` y `!=0`, **y** `varianza` no
  `NaN` y `> 0` (si `mu` es `NaN` en una celda válida de `varianza`,
  trátese como `mu = 0.0` para el cálculo de Kelly — una señal activa sin
  suficiente historia de retorno trailing no debe excluirse solo por eso,
  simplemente no aporta *edge* estimado). `kelly = mu / varianza`.
  `crudo = signo(senal) · fraccion · |kelly|`, recortado (clip) a
  `±tope_posicion`. `0.0` en las no válidas. Luego, por fila, si
  `Σ|crudo| > 1.0`, reescalar toda la fila por `1.0 / Σ|crudo|`
  (mantiene proporciones relativas, gross final ≤ 1.0); si
  `Σ|crudo| ≤ 1.0`, no se toca.

### Apalancamiento y cash

* `cash_pct_dinamico(regimen: pd.Series) -> pd.Series`: `0.02` si
  `regimen ∈ {1.0, 2.0}` (liquidez en expansión), `0.10` si
  `regimen ∈ {3.0, 4.0}` (contracción). Si `regimen` es `NaN` → `0.10`
  (aclaración v1.2: ante macro incierta, el valor conservador, no el
  favorable).
* `aplicar_leverage_y_cash(pesos_base: pd.DataFrame, L: float, cash_pct:
  pd.Series) -> pd.DataFrame`: `pesos_base.mul(L * (1 - cash_pct), axis=0)`
  — multiplica cada fila por el escalar `L · (1 − cash_pct)` de esa fecha.
  Lanza `ValueError` si algún valor de `cash_pct` está fuera de `[0, 1]`.
* `costo_apalancamiento_diario(L: float, tasa_cash_anual: pd.Series,
  spread_anual: float) -> pd.Series`: `(L - 1) * (tasa_cash_anual / 252 +
  spread_anual / 252)`. `tasa_cash_anual` en fracción (no porcentaje,
  p. ej. `0.05` para 5%). Si `L == 1.0`, el resultado es `0.0` en todas
  las fechas (sin apalancamiento, sin costo), incluso donde
  `tasa_cash_anual` sea `NaN` (no hay nada que costear).

### Casos de prueba obligatorios

1. **`pesos_equal`**: con señales `[1, -1, 0, NaN]` en una fila da pesos
   `[0.5, -0.5, 0.0, 0.0]`; una fila sin ninguna señal válida da todos
   `0.0`, no `NaN`.
2. **`pesos_inv_vol`**: con dos activos de vol distinta y misma señal
   `+1`, el de menor vol recibe mayor peso, y `Σ|peso| == 1.0`; un activo
   con vol `NaN` o `0` se excluye (peso `0.0`) sin romper la normalización
   de los demás.
3. **`pesos_vol_target`**: con un objetivo del doble de la vol aproximada
   del portafolio de `pesos_inv_vol`, los pesos resultantes son
   exactamente el doble (mismo signo, misma proporción relativa). Una
   fila con `Σ|crudo| == 0` en `inv_vol` da `factor` sin lanzar
   `ZeroDivisionError` ni `NaN` contagioso (pesos quedan en `0.0`).
4. **`retorno_esperado_trailing` / `varianza_trailing`**: `NaN` antes de
   completar `ventana`; con retornos constantes, `varianza_trailing` da
   `0.0` (no `NaN`) una vez completa la ventana.
5. **`pesos_kelly_frac`**: (a) un activo con `varianza` muy chica y señal
   fuerte queda recortado exactamente en `±tope_posicion`, no más; (b)
   una fila donde la suma de `|crudo|` excede `1.0` se reescala
   proporcionalmente a gross `1.0` (verificar que la *proporción* entre
   dos posiciones de esa fila no cambia, solo la escala); (c) una fila
   con `varianza > 0` pero `mu` = `NaN` no excluye esa posición (usa
   `mu = 0.0`, dando `kelly = 0.0`, peso `0.0` por esa celda — no `NaN`
   contagiado al resto de la fila).
6. **`cash_pct_dinamico`**: da `0.02`/`0.10` para cada par de regímenes, y
   `0.10` (no `0.02` ni `NaN`) cuando el régimen es `NaN`.
7. **`aplicar_leverage_y_cash`**: con `L=2.0` y `cash_pct=0.10` constante,
   el resultado es exactamente `pesos_base * 1.8`; `cash_pct` fuera de
   `[0,1]` (p. ej. `1.5` o `-0.1`) lanza `ValueError`.
8. **`costo_apalancamiento_diario`**: con `L=1.0` da `0.0` en todas las
   fechas aunque `tasa_cash_anual` tenga `NaN`; con `L=2.0` y
   `tasa_cash_anual` constante, el valor coincide con el cálculo manual
   `(L-1)*(tasa/252 + spread/252)`.

Todos los DataFrames/Series de prueba son sintéticos, construidos a mano
(sin red, sin datos reales).

## `prl.growth_max.grid`

Implementa la sección *Grilla completa* de `PREREGISTRATION.md`: las
**17 280 variantes exactas**, ninguna más. Tests en
`tests/growth_max/test_growth_grid.py`. Solo `itertools`, `typing`,
`dataclasses` (no necesita `pandas`/`numpy`). Funciones puras.

* `construccion_parametros() -> list[tuple[str, float | None]]`: las
  **8** combinaciones fijas (método, parámetro), en este orden exacto
  (mismo orden de la tabla del pre-registro):
  `[("equal", None), ("inv_vol", None), ("vol_target", 0.10),
  ("vol_target", 0.15), ("vol_target", 0.20), ("kelly_frac", 0.25),
  ("kelly_frac", 0.50), ("kelly_frac", 1.00)]`.
* `cash_politicas() -> list[str]`: `["cash_0", "cash_5", "cash_10",
  "cash_20", "cash_dinamico"]`, en ese orden.
* `build_grid() -> list[dict]`: `itertools.product` en este orden exacto
  — `L_meses ∈ [3, 6, 12]`, `W_dias ∈ [50, 100, 200]`, `B_dias ∈ [55, 252]`,
  `V_dias ∈ [20, 60]`, `(construccion, construccion_param) ∈
  construccion_parametros()`, `cash_politica ∈ cash_politicas()`,
  `leverage ∈ [1.0, 1.5, 2.0]`, `spread ∈ [0.01, 0.02]`, `k ∈ [0.5, 0.75]`.
  Total: `3·3·2·2·8·5·3·2·2 = 17280`. Cada elemento es un `dict` con las
  claves `variant_id`, `L_meses`, `W_dias`, `B_dias`, `V_dias`,
  `construccion`, `construccion_param`, `cash_politica`, `leverage`,
  `spread`, `k` (`Z_dias` queda fijo en `10` fuera de la grilla, por
  pre-registro — no es una clave de este dict).
  `variant_id` = `"|".join([str(L_meses), str(W_dias), str(B_dias),
  str(V_dias), f"{construccion}:{construccion_param}", cash_politica,
  str(leverage), str(spread), str(k)])` — único por construcción (el
  producto cartesiano nunca repite una combinación).

### Casos de prueba obligatorios

1. **`construccion_parametros()`** devuelve exactamente las 8 tuplas en
   el orden de arriba (comparación de igualdad de lista completa, no solo
   el conteo).
2. **`cash_politicas()`** devuelve exactamente las 5 en el orden de
   arriba.
3. **`build_grid()`** tiene exactamente `17280` elementos.
4. **Todos los `variant_id` son únicos** (`len(set(...)) ==
   len(build_grid())`).
5. **Cada combinación de parámetros aparece exactamente una vez**: tomar
   una tupla de parámetros arbitraria (p. ej. `L_meses=6, W_dias=100,
   B_dias=252, V_dias=20, construccion="kelly_frac",
   construccion_param=0.5, cash_politica="cash_dinamico", leverage=1.5,
   spread=0.02, k=0.75`) y verificar que exactamente un elemento de
   `build_grid()` tiene esos 10 valores.
6. **El primer y el último elemento** de `build_grid()` son exactamente
   los que predice el orden de `itertools.product` documentado arriba
   (primer elemento: `L_meses=3, W_dias=50, B_dias=55, V_dias=20,
   construccion="equal", construccion_param=None, cash_politica="cash_0",
   leverage=1.0, spread=0.01, k=0.5`; último elemento: los últimos
   valores de cada lista, `k=0.75` al final).

## `prl.growth_max.evaluation`

Implementa la sección *Validación* y el *Criterio de selección* de
`PREREGISTRATION.md`, con la aclaración v1.4. Tests en
`tests/growth_max/test_growth_evaluation.py`.

Reglas transversales: solo `pandas`/`numpy`/`scipy.stats`/`typing`/
`dataclasses` (igual que `evaluation.py` de EXP-001 — aquí sí hace falta
`scipy.stats.norm` para el Deflated Sharpe). Sin red/archivos/variables de
entorno. Funciones puras. **No importa `prl.emergency` ni otros módulos de
`prl.growth_max`** — fórmulas compartidas se reimplementan (mismo criterio
que `composite_score`).

* `tasa_crecimiento_geometrica(retornos: pd.Series) -> float`: idéntica
  fórmula que el `cagr` de `prl.growth_max.backtest.metricas`
  (`equity_final ** (365.25 / días_calendario) − 1`; `NaN` si
  `días_calendario == 0`).

* `bootstrap_bloques_retornos(retornos: pd.DataFrame, tamano_bloque: int,
  n_replicas: int, seed: int) -> np.ndarray`: *block bootstrap* — con
  `rng = np.random.default_rng(seed)`, en cada réplica concatena
  `ceil(n/tamano_bloque)` bloques de `tamano_bloque` filas consecutivas
  (inicio de cada bloque uniforme en `[0, n − tamano_bloque]`), recorta a
  `n` filas. **La misma selección de bloques se aplica a todas las
  columnas de `retornos` en una réplica dada** (bootstrap pareado — ver
  aclaración v1.4). Devuelve un arreglo de forma
  `(n_replicas, n, n_columnas)` (orden de columnas = `retornos.columns`).
  Si `n < tamano_bloque` → `ValueError`.

* `probabilidad_perdida(retornos: pd.Series, umbral: float,
  tamano_bloque: int = 20, n_replicas: int = 10000, seed: int = 0) ->
  float`: usa `bootstrap_bloques_retornos` (una sola columna). Para cada
  réplica, calcula la curva de equity (`(1+r).cumprod()`) y su máximo
  drawdown (`(equity/equity.cummax() − 1).min()`); cuenta la fracción de
  réplicas donde `abs(max_drawdown) >= umbral`. `umbral` en fracción
  (`0.5` = 50%).

* `comparacion_bootstrap(ret_modelo: pd.Series, ret_benchmark: pd.Series,
  tamano_bloque: int = 20, n_replicas: int = 10000, seed: int = 0,
  alpha: float = 0.05) -> dict`: usa `bootstrap_bloques_retornos` con
  ambas series como columnas (pareado). Para cada réplica calcula
  `tasa_crecimiento_geometrica` de ambas columnas remuestreadas. Devuelve
  `{"ci_cagr_modelo": (percentil alpha/2, percentil 1-alpha/2),
  "frac_supera_benchmark": fracción de réplicas donde
  cagr_modelo_replica > cagr_benchmark_replica}`.

* `deflated_sharpe_ratio(returns: pd.Series, n_trials: int) -> float`:
  **misma fórmula exacta** que `prl.emergency.evaluation.deflated_sharpe_ratio`
  de EXP-001 (ver aclaración v1.4): `n = len(returns)`, `sr` = media/desv
  (`ddof=1`) **diaria sin anualizar**, `g3` = asimetría (`skew()`), `g4` =
  curtosis no-exceso (`kurt() + 3`), `sr_std =
  sqrt((1 − g3·sr + (g4−1)/4·sr²) / (n−1))`. Si `n_trials <= 1`: `sr0 = 0`;
  si no, `γ = 0.5772156649015329`,
  `sr0 = sr_std · ((1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e)))` con `N = n_trials`
  (`Φ⁻¹` = `scipy.stats.norm.ppf`). Resultado: `Φ((sr − sr0)/sr_std)`
  (`scipy.stats.norm.cdf`).

* `elegir_variante(log_wealth_validation: dict[str, float],
  prob_perdida_50: dict[str, float], prob_perdida_75: dict[str, float]) ->
  tuple[str | None, str]`: las tres claves comparten las mismas llaves
  (`variant_id`). Candidatos = `{v : prob_perdida_50[v] < 0.20}`. Si no
  está vacío, devuelve `(variant_id con mayor log_wealth_validation entre
  los candidatos, "filtro_50")` (empate → el primero según el orden de
  iteración del dict). Si está vacío, candidatos релajados =
  `{v : prob_perdida_75[v] < 0.20}`; si no está vacío, devuelve
  `(ganador, "filtro_75_relajado")`. Si también está vacío, devuelve
  `(None, "ninguna_variante_pasa_el_filtro_de_ruina")`.

* `placebo_circular(retornos: pd.Series, n_placebos: int = 1000, seed:
  int = 0) -> np.ndarray`: con `rng = np.random.default_rng(seed)`, para
  cada placebo elige un desplazamiento entero uniforme en
  `[1, len(retornos) − 1]` (nunca `0`, eso sería la serie original) y
  calcula `tasa_crecimiento_geometrica` de `np.roll(retornos.to_numpy(),
  desplazamiento)` (envuelto en una `pd.Series` con el índice original de
  `retornos`, para que la fórmula de días calendario siga funcionando).
  Devuelve un arreglo de `n_placebos` tasas. Si `len(retornos) < 2` →
  `ValueError`.

* `percentil_real_vs_placebo(valor_real: float, placebos: np.ndarray) ->
  float`: fracción de `placebos` que son `<= valor_real` (incluye
  empates). `0.0` si `placebos` está vacío.

* `etiqueta(ci_cagr_modelo: tuple[float, float], frac_supera_benchmark:
  float, prob_ruina_75: float, n_dias_locked_test: int) -> str`: aplica
  el orden de prioridad de la aclaración v1.4 (1. `INCONCLUSIVE` si
  `n_dias_locked_test < 756`; 2. `REJECTED` si
  `frac_supera_benchmark <= 0.50` o `prob_ruina_75 > 0.20`; 3.
  `VALIDATED` si `ci_cagr_modelo[0] > 0.0` y `frac_supera_benchmark >=
  0.80`; 4. `INCONCLUSIVE` en cualquier otro caso). Nunca lanza excepción
  por un valor `NaN` de entrada — un `NaN` en cualquier argumento numérico
  cuenta como "no cumple" esa comparación (ni `REJECTED` ni `VALIDATED`
  por esa condición específica), cayendo hacia `INCONCLUSIVE` si ninguna
  otra condición aplica.

### Casos de prueba obligatorios

1. **`tasa_crecimiento_geometrica`**: con un retorno diario constante
   conocido, coincide con el cálculo manual de la fórmula.
2. **`bootstrap_bloques_retornos`**: forma de salida correcta
   `(n_replicas, n, n_columnas)`; con `seed` igual, dos llamadas dan
   resultados idénticos (reproducibilidad); `n < tamano_bloque` lanza
   `ValueError`; con 2 columnas, una fila remuestreada de la réplica *r*
   siempre corresponde a la **misma fecha original** en ambas columnas
   (pareado: verificar reconstruyendo qué posición original se usó).
3. **`probabilidad_perdida`**: una serie de retornos diarios todos
   `-0.05` da probabilidad `1.0` para cualquier `umbral <= casi 100%`;
   una serie de retornos diarios todos `+0.001` (sin drawdown posible)
   da probabilidad `0.0` para `umbral > 0`.
4. **`comparacion_bootstrap`**: con `ret_modelo` idéntico a
   `ret_benchmark`, `frac_supera_benchmark` es `0.0` (nunca "supera" a
   una serie idéntica, con `>` estricto); con `ret_modelo` uniformemente
   mejor cada día, `frac_supera_benchmark == 1.0`.
5. **`deflated_sharpe_ratio`**: con `n_trials=1`, el resultado coincide
   con `Φ(sr/sr_std)` calculado a mano para una serie sintética simple;
   aumentar `n_trials` (con los mismos retornos) nunca aumenta el DSR.
6. **`elegir_variante`**: con dos variantes, una pasa el filtro de 50% y
   la otra no → gana la que pasa, motivo `"filtro_50"`, sin importar cuál
   tiene mayor `log_wealth_validation`; si ninguna pasa 50% pero una pasa
   75% → esa gana, motivo `"filtro_75_relajado"`; si ninguna pasa ninguno
   → `(None, "ninguna_variante_pasa_el_filtro_de_ruina")`.
7. **`placebo_circular`**: forma de salida `(n_placebos,)`; con `seed`
   igual, resultados idénticos; `len(retornos) < 2` lanza `ValueError`.
8. **`percentil_real_vs_placebo`**: con `placebos = [1,2,3,4,5]` (como
   array) y `valor_real = 3`, resultado `0.6` (3 de 5 son `<= 3`).
9. **`etiqueta`**: los cuatro casos de la aclaración v1.4, probados por
   separado (incluido que `n_dias_locked_test < 756` gana aunque el resto
   de condiciones serían `VALIDATED`); un `NaN` en `ci_cagr_modelo[0]`
   con el resto de condiciones de `VALIDATED` cumplidas da
   `INCONCLUSIVE`, no excepción.

Todas las series/arreglos de prueba son sintéticos, construidos a mano
(sin red, sin datos reales). Los tests de bootstrap/placebo usan
`n_replicas`/`n_placebos` chicos (decenas, no miles) para que la suite
corra rápido — el valor por defecto de la función (miles) es para uso
real, no para los tests.

## `prl.growth_max.backtest`

Implementa la sección *Costos* de `METHODOLOGY.md` y la aclaración de
implementación v1.3 de `PREREGISTRATION.md`. Tests en
`tests/growth_max/test_growth_backtest.py`.

Reglas transversales (iguales a los módulos anteriores de EXP-002): sin
look-ahead, solo `pandas`/`numpy`/`typing`/`dataclasses`, sin red/archivos/
variables de entorno, funciones puras. **Validación estricta: nunca
resultados en silencio con datos faltantes** (ver más abajo).

* `costo_transaccion_diario(pesos_aplicados: pd.DataFrame, costo_por_lado:
  float = 0.001) -> pd.Series`: `turnover_t = Σ_i |pesos_aplicados[t,i] −
  pesos_aplicados[t−1,i]|` para `t ≥ 1`; `turnover_0 = 0.0` (no hay fila
  anterior). `costo_t = turnover_t · costo_por_lado`. `pesos_aplicados`
  ya viene con el rezago aplicado (ver `ejecutar_backtest`) — esta función
  no vuelve a desplazar nada, solo calcula el turnover entre filas
  consecutivas tal cual las recibe.

* `ejecutar_backtest(pesos: pd.DataFrame, retornos: pd.DataFrame,
  costo_apalancamiento: pd.Series, costo_por_lado: float = 0.001) ->
  pd.DataFrame`:
  * `pesos` y `retornos` comparten el mismo índice de fechas y las mismas
    columnas (activos); `costo_apalancamiento` comparte el índice de
    fechas. Si no comparten índice/columnas exactamente → `ValueError`.
  * **Validación estricta:** si `pesos` tiene algún `NaN` → `ValueError`.
    Si, en algún día *t* y activo *i*, `pesos.shift(1)` (los pesos ya
    rezagados, los que de verdad generan el retorno de *t*) es distinto de
    `0.0` **y** `retornos[t, i]` es `NaN` → `ValueError` (se sostiene una
    posición en un activo sin dato de precio ese día).
  * `pesos_aplicados = pesos.shift(1).fillna(0.0)` (rezago interno: el
    primer día no tiene posición previa, por eso `0.0`, no se descarta la
    fila).
  * `turnover`/`costo_transaccion` = `costo_transaccion_diario(pesos_aplicados,
    costo_por_lado)` (primer día `0.0`, ver función de arriba).
  * `bruto_t = Σ_i (pesos_aplicados[t,i] · retornos[t,i])` (suma ignorando
    `NaN` de activos con peso `0.0` ese día — ya cubiertos por la
    validación de arriba cuando el peso NO es `0.0`).
  * `ret_t = bruto_t − costo_transaccion_t − costo_apalancamiento_t`.
    Primer día: `pesos_aplicados` es `0.0` en todas las columnas y
    `costo_transaccion` es `0.0`, así que `ret_0 = −costo_apalancamiento_0`
    (normalmente `0.0` si `L = 1.0`, ver `costo_apalancamiento_diario`).
  * `equity_t = Π_{s≤t} (1 + ret_s)` (empieza efectivamente en `1.0`
    antes de la primera fila, igual convención que `prl.emergency.backtest`
    de EXP-001).
  * Devuelve un `pd.DataFrame` con columnas `ret`, `equity`, `turnover`,
    `costo_transaccion`, `costo_apalancamiento` (todas con el mismo índice
    de fechas que `retornos`).

* `metricas(returns: pd.Series) -> dict`: igual definición que
  `prl.emergency.backtest.metrics` de EXP-001 (reimplementada aquí, sin
  importar `prl.emergency` — misma razón que `composite_score` en
  `signals.py`): `cagr` (`equity_final ** (365.25 / días_calendario) − 1`,
  días_calendario = `(índice[-1] − índice[0]).days`), `max_drawdown`
  (`(equity / equity.cummax() − 1).min()`, negativo), `calmar` (`cagr /
  |max_drawdown|`; si `max_drawdown == 0.0` → `NaN`, no `inf`), `sharpe`
  (`media(ret) / desv(ret, ddof=1) · √252`, rf=0; si `desv == 0` → `NaN`),
  `sortino` (`media(ret) / desv(ret[ret<0], ddof=1) · √252`; si no hay
  retornos negativos o la desviación a la baja es `0` → `NaN`), `n_days`
  (`len(returns)`).

### Casos de prueba obligatorios

1. **Rezago correcto (sin look-ahead):** una señal/peso que cambia
   bruscamente en la fecha *t* no debe afectar el retorno de *t*, solo el
   de *t+1* en adelante. Construir `pesos` con un salto de `0.0` a `1.0`
   en una fecha específica y verificar que `ret` en esa fecha usa el peso
   **anterior** (`0.0`), y el día siguiente ya usa `1.0`.
2. **Primer día:** `ret.iloc[0]` es `0.0` (o `−costo_apalancamiento.iloc[0]`
   si se pasa un costo de apalancamiento no nulo en esa fecha);
   `turnover.iloc[0] == 0.0`.
3. **Turnover y costo:** dos activos, pesos que cambian de `(0.5, 0.5)` a
   `(1.0, 0.0)` de una fila a la siguiente → turnover de esa transición
   es `1.0` (`|0.5| + |0.5|`), costo = `costo_por_lado · 1.0`, aplicado en
   la fila donde ese peso ya rezagado empieza a generar retorno (no en la
   fila donde se "decidió").
4. **Validación: `pesos` con `NaN` lanza `ValueError`.**
5. **Validación: posición en activo sin retorno ese día lanza
   `ValueError`** (peso rezagado distinto de `0.0` en una fecha donde
   `retornos` tiene `NaN` para ese activo); el mismo caso con peso `0.0`
   en esa fecha **no** lanza nada (el activo simplemente no se opera).
6. **`equity`** es monótono-consistente con `ret`: `equity.iloc[-1] ==
   (1 + ret).prod()` (dentro de tolerancia de punto flotante).
7. **`metricas`**: con una serie de retornos diarios constantes positivos,
   `max_drawdown == 0.0` y `calmar` es `NaN` (no `inf`, no excepción); con
   una serie sin retornos negativos, `sortino` es `NaN`; `cagr` de una
   serie conocida (p. ej. retorno diario constante `r` por `N` días)
   coincide con el cálculo manual usando la fórmula de arriba.

Todos los DataFrames/Series de prueba son sintéticos, construidos a mano
(sin red, sin datos reales).

## `prl.growth_max.exp002` (orquestador)

A diferencia de los módulos anteriores, **este sí importa** a los demás
módulos de `prl.growth_max` (`signals`, `portfolio`, `backtest`, `grid`,
`evaluation`) y a `prl.data.macro_vintage` — su trabajo es conectarlos
con datos reales, igual que `prl.emergency.exp001` hace para EXP-001.
También hace E/S (lee `.parquet` de `inputs_dir`, escribe
`run_dir/results.json`) y usa `json`/`pathlib` además de
`pandas`/`numpy`. Debe ser **determinista**: mismas entradas → mismo
`results.json` byte a byte.

`escalar_por_regimen(pesos_base: pd.DataFrame, regimen: pd.Series, k: float)
-> pd.DataFrame`: multiplica **cada fila completa** de `pesos_base` por
`k` en las fechas donde `regimen ∈ {3.0, 4.0}` (contracción de liquidez),
y por `1.0` en el resto (incluido cuando `regimen` es `NaN`) — sin
importar qué método de construcción produjo `pesos_base` (familia de
señal 5 del pre-registro: *"la exposición bruta **total** se escala por
un factor `k`"*, aplica a los 4 métodos por igual, no solo a
`kelly_frac`). Función pura, independiente de `run()` — así es
testeable por separado sin tener que ejecutar el orquestador completo.

**Caso de prueba obligatorio para `escalar_por_regimen`:** con
`pesos_base` constante (misma fila todos los días) y `regimen` que
alterna entre `1.0` (concuerda, sin escalar) y `3.0` (contracción), el
resultado en los días de régimen `3.0` debe ser exactamente
`pesos_base * k`, y en los días de régimen `1.0` debe ser idéntico a
`pesos_base` sin cambios; con `regimen = NaN` en una fila, esa fila
tampoco se escala.

`run(inputs_dir, run_dir, discovery_end="2015-12-31",
validation_end="2019-12-31", n_boot=500, seed=0) -> dict`. Usa
`escalar_por_regimen` en el paso 6 de abajo. Escribe
`run_dir/results.json` (`NaN` → `null`) y lo devuelve. Pasos:

1. **Universo (65 ids, orden fijo):** `SPY, QQQ, IWM, DIA, EFA, EEM, EWJ,
   XLK, XLE, XLF, XLV, XLP, XLU, XLY, XLI, XLB, EWG, EWQ, EWU, EWL, EWI,
   EWP, EWN, EWA, EWH, EWS, EWZ, EWW, EWY, EWT, MCHI, INDA, EIDO, EZA,
   TUR, EPOL, MTUM, QUAL, USMV, VLUE, TLT, IEF, SHY, BIL, HYG, LQD, TIP,
   EMB, BNDX, MBB, GLD, SLV, USO, UNG, DBC, DBA, UUP, FXE, FXY, FXB, FXF,
   FXC, FXA, VNQ, VNQI`. Lee `inputs_dir/<ID>.parquet` (columna
   `adj_close`) para cada uno; arma un `DataFrame` de precios con índice
   = unión ordenada de todas sus fechas — **no recorta a un "inicio
   común"**: un activo antes de su propia primera fecha real queda `NaN`
   (ver aclaración v1.5). `retornos = precios.pct_change()`.
2. **Tasa de cash:** lee `inputs_dir/DTB3.parquet` (columna `value`,
   % anual); `tasa_cash_diaria = value / 100 / 252`, propagada hacia
   adelante y alineada al índice de `precios`.
3. **Régimen macro point-in-time:** lee `inputs_dir/M2.parquet`,
   `FED_BALANCE.parquet`, `LEADING.parquet` (formato de vintages de
   `prl.data.macro_vintage`). Para cada una,
   `prl.data.macro_vintage.serie_conocida_en(vintages, fechas=índice de
   precios)` da el valor conocido en cada día de trading (columna
   `value`). Liquidez = promedio de los cambios trailing de 126 días
   (`signals.signo_cambio_trailing(serie, 126)`) de M2 y FED_BALANCE —
   si ambas están disponibles esa fecha, su signo promedio redondeado al
   signo más cercano (`1.0` si la suma de signos `> 0`, `-1.0` si `< 0`,
   `0.0` si se cancelan exactamente); si solo una está disponible, se usa
   esa; si ninguna, `NaN`. Crecimiento = `signals.signo_cambio_trailing`
   de LEADING a 126 días. `regimen = signals.regimen_macro(liquidez,
   crecimiento)`; `es_rango = signals.es_regimen_de_rango(regimen)`;
   `cash_pct_regimen = portfolio.cash_pct_dinamico(regimen)`.
4. **Señales por combinación única `(L_meses, W_dias, B_dias, V_dias)`**
   (36 combinaciones — no 17 280; `construccion`/`cash_politica`/
   `leverage`/`spread`/`k` no afectan la señal, solo la construcción del
   portafolio, así que se calculan una sola vez por combinación y se
   reutilizan): para cada uno de los 65 activos, momentum
   (`ts_momentum_signal(precio, L_meses)`), tendencia
   (`trend_signal(precio, W_dias)`), breakout
   (`breakout_signal(precio, B_dias)`) → compuesta direccional =
   `composite_score` con pesos iguales (`1.0` cada una). Reversión fija
   en `Z_dias = 10` (`senal_reversion(precio, 10)`). Señal final =
   `senal_compuesta_con_overlay(direccional, reversion, es_rango)`.
   Volatilidad = `volatilidad_realizada(precio, V_dias)`. Para Kelly:
   `mu = retorno_esperado_trailing(retornos, V_dias)`,
   `varianza = varianza_trailing(retornos, V_dias)` (reutiliza `V_dias`,
   no un parámetro nuevo — ver aclaración v1.2).
5. **Fecha de inicio del backtest:** la primera fecha en la que al menos
   40 de los 65 activos tienen `retornos` no `NaN` (umbral del
   pre-registro). Todo lo anterior a esa fecha se descarta del backtest
   (pero no de los activos individuales: un activo puede seguir
   entrando después).
6. **Para cada una de las 17 280 variantes de `grid.build_grid()`:**
   tome la matriz de señales/vol/mu/varianza de su combinación
   `(L_meses, W_dias, B_dias, V_dias)` (paso 4). Construya `pesos_base`
   según `construccion`/`construccion_param` (`portfolio.pesos_equal`,
   `pesos_inv_vol`, `pesos_vol_target`, o `pesos_kelly_frac`, según
   corresponda). **Después**, sin importar el método, aplique
   `escalar_por_regimen(pesos_base, regimen, k)` (definida arriba) —
   esto es la familia de señal 5 del pre-registro: *"la exposición
   bruta **total** se escala por un factor `k`"*, aplica a los **4**
   métodos de construcción por igual, no solo a `kelly_frac` (la
   combinación `(construccion="equal", k=0.5)` y `(construccion="equal",
   k=0.75)` deben dar resultados distintos — si no, `k` no tendría
   efecto en 3 de los 4 métodos, lo
   que invalidaría esa dimensión de la grilla).
   `cash_pct` = fijo según `cash_politica` (`0.0/0.05/0.10/0.20`) o
   `cash_pct_regimen` si `cash_politica == "cash_dinamico"`. Pesos
   finales = `portfolio.aplicar_leverage_y_cash(pesos_base, leverage,
   cash_pct)`. Agregue una columna `"CASH"` a esos pesos (valor =
   `cash_pct` de cada fila) y a `retornos` (valor = `tasa_cash_diaria`)
   — ver aclaración v1.5. `costo_apalancamiento =
   portfolio.costo_apalancamiento_diario(leverage, tasa_cash_anual=
   value de DTB3 (no la tasa diaria), spread_anual=spread)`.
   `resultado = backtest.ejecutar_backtest(pesos, retornos_con_cash,
   costo_apalancamiento, costo_por_lado=0.001)`, recortado a partir de
   la fecha de inicio del paso 5. Divida `resultado["ret"]` en
   `discovery` (hasta `discovery_end`), `validation` (`discovery_end+1`
   a `validation_end`) y `locked_test` (después de `validation_end`).
   Guarde solo lo necesario para el paso 7 (no los 17 280 DataFrames
   completos en memoria todo el tiempo, por rendimiento — detalle de
   implementación, no de contrato).
7. **Selección:** para cada variante, `log_wealth_validation[v] =
   evaluation.tasa_crecimiento_geometrica(ret_validation[v])`;
   `prob_perdida_50[v]` y `prob_perdida_75[v]` =
   `evaluation.probabilidad_perdida` sobre `ret_discovery[v]` concatenado
   con `ret_validation[v]`, con `tamano_bloque=20`, `n_replicas=n_boot`,
   `seed=seed` (umbrales `0.5` y `0.75`). `ganador, motivo =
   evaluation.elegir_variante(log_wealth_validation, prob_perdida_50,
   prob_perdida_75)`.
8. **Si `ganador is None`:** `results.json` con `"label": "INCONCLUSIVE"`,
   `"motivo_seleccion"` (el de `elegir_variante`), y las claves de abajo
   en `null`/vacías donde no aplique. No se calcula nada más (el locked
   test set nunca se toca).
9. **Si hay `ganador`:** para cada uno de los 5 niveles de apetito
   (`Conservative`: `cash_20`, `L=1.0`; `Growth25`: `cash_10`, `L=1.0`;
   `Growth50`: `cash_5`, `L=1.5`; `Growth75`: `cash_0`, `L=1.5`; `Max`:
   `cash_0`, `L=2.0` — mismo `spread`/`k`/combinación de señal que
   `ganador`, solo cambia cash/leverage), recalcule los pesos (mismo
   método de construcción del ganador) y corra el backtest **solo sobre
   `locked_test`** (discovery+validation ya están "gastados"). Guarde
   `backtest.metricas(ret)` y `evaluation.probabilidad_perdida(ret,
   umbral)` para `umbral ∈ {0.5, 0.75, 0.9, 0.99}`, por nivel.
10. **Benchmark:** 60% equal-weight `{SPY, EFA, EEM}` + 40% equal-weight
    `{TLT, IEF, LQD}`, pesos fijos diarios (sin señal), mismo
    `ejecutar_backtest` (sin costo de apalancamiento, `costo_por_lado=
    0.001`), sobre `locked_test`.
11. **Comparación y etiqueta:** `comparacion =
    evaluation.comparacion_bootstrap(ret_locked["Growth50"],
    ret_locked["benchmark"], tamano_bloque=20, n_replicas=n_boot,
    seed=seed)`. `label = evaluation.etiqueta(comparacion["ci_cagr_modelo"],
    comparacion["frac_supera_benchmark"], prob_ruina_75 de Growth50 (del
    paso 9), n_dias_locked_test=len(ret_locked["Growth50"]))`.
12. **Placebo y DSR:** `placebo =
    evaluation.placebo_circular(ret_locked["Growth50"], n_placebos=n_boot,
    seed=seed)`; `percentil =
    evaluation.percentil_real_vs_placebo(tasa_crecimiento_geometrica(
    ret_locked["Growth50"]), placebo)`. `dsr =
    evaluation.deflated_sharpe_ratio(ret_validation[ganador],
    n_trials=17280)`.
13. **`results.json`** con claves: `experiment` (`"EXP-002"`),
    `variant_id_ganador` (o `null`), `motivo_seleccion`, `n_variants`
    (`17280`), `fecha_inicio_backtest`, `discovery_end`, `validation_end`,
    `n_dias_locked_test`, `niveles` (dict por nombre de nivel → `metricas`
    + `probabilidad_ruina` por umbral, vacío si `ganador is None`),
    `comparacion_bootstrap_growth50` (`ci_cagr_modelo`,
    `frac_supera_benchmark`), `label`, `deflated_sharpe`,
    `percentil_vs_placebo`, `notes` (lista: limitaciones ya conocidas —
    aproximación de `vol_target` sin correlaciones, universo solo
    ETF/índice, macro limitada a 3 series point-in-time).

### Casos de prueba obligatorios (test de integración, datos sintéticos)

Mismo patrón que `tests/emergency/test_exp001.py`: un *fixture* que
genera `.parquet` sintéticos para los 65 ids + `DTB3` + `M2` +
`FED_BALANCE` + `LEADING` (estas 3 últimas en formato de vintages, con
una sola versión vigente por fecha — no hace falta simular revisiones
para este test) en `tmp_path`, con suficiente historia para que
`discovery_end`/`validation_end` de prueba (más tempranos que los del
pre-registro, p. ej. `discovery_end="2009-12-31"`,
`validation_end="2010-12-31"` sobre datos sintéticos 2006-2012) dejen
años utilizables en cada tramo.

1. **`run` escribe `results.json` con las claves esperadas** (lista de la
   sección 13 de arriba); `label` ∈ `{VALIDATED, REJECTED, INCONCLUSIVE}`;
   si `variant_id_ganador` no es `null`, `niveles` tiene exactamente las
   5 claves (`Conservative, Growth25, Growth50, Growth75, Max`) y cada
   una trae `metricas` con `{cagr, max_drawdown, calmar, sharpe, sortino,
   n_days}` y `probabilidad_ruina` con las 4 claves `{0.5, 0.75, 0.9,
   0.99}` (como strings o floats, pero las 4 presentes).
2. **`run` es determinista:** dos corridas con los mismos insumos y
   `n_boot` chico (p. ej. `30`) dan el mismo `results.json` byte a byte.

Dado el volumen de cómputo (17 280 variantes), el test usa `n_boot`
chico y un universo/historia sintéticos cortos — el valor por defecto
(`n_boot=500`) y el historial real (~20 años, 207 series) son para la
corrida real vía `run-experiment.yml`, no para este test.

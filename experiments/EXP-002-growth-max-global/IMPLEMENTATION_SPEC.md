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

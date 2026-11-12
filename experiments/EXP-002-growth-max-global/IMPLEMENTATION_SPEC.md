# EXP-002 — Contrato de implementación: `prl.data.macro_vintage`

Este documento y los tests en `tests/test_macro_vintage.py` son el
**contrato**. El código de `src/prl/data/macro_vintage.py` debe hacerlos
pasar sin tocarlos. Ver `DATA_INFRA_MACRO_VINTAGE.md` para el porqué.

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
* Filas con `realtime_start` posterior a `obs_date` en más de 50 años,
  o `realtime_start` **anterior** a `obs_date` → `ValueError` (un valor
  no puede conocerse antes del período que describe; ver
  `validar_vintages` para el chequeo reutilizable).
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

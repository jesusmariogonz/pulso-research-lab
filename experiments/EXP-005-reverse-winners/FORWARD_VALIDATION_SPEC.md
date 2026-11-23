# EXP-005 Forward Validation — Contrato de implementación

## `prl.reverse_winners.forward_validation`

Implementa las métricas y desgloses de la sección 3 de
`FORWARD_VALIDATION.md`. Tests en
`tests/reverse_winners/test_reverse_winners_forward_validation.py`.
Solo `pandas`/`numpy`/`typing`. Sin red, sin archivos, sin variables de
entorno. Funciones puras. **No importa `prl.growth_max` ni
`prl.emergency`**; sí puede importar `prl.reverse_winners.evaluation`
para reutilizar `concentracion_maxima` y `leave_one_ticker_out_signo`
(no se reimplementan — están en el mismo paquete, a diferencia del
aislamiento entre experimentos).

Convención de entrada común a casi todas las funciones: `senales` es
un `pd.DataFrame` con una fila por señal (una combinación fecha×ticker
elegida por el bucket, el mismo formato que ya usa
`prl.reverse_winners.exp005`), columnas mínimas `["fecha", "ticker",
"retorno_30d"]` (`fecha` es `pd.Timestamp`).

### Serie por fecha de corte

* `serie_por_fecha(senales: pd.DataFrame, columna_retorno: str =
  "retorno_30d") -> pd.Series`: `senales.groupby("fecha")[
  columna_retorno].mean()`, ordenada por fecha ascendente. `pd.Series`
  vacía si `senales` está vacío.

### Métricas sobre una serie por fecha (no sobre señales individuales)

* `retorno_acumulado(serie: pd.Series) -> float`: `(1 +
  serie).prod() - 1`. `NaN` si `serie` está vacía. **Nota de método**:
  compone los retornos de fechas de corte consecutivas como si fueran
  periodos secuenciales, aunque las ventanas de 30 días se solapen
  entre sí (paso de 10 sesiones) — mismo tipo de limitación declarada
  que el resto del proyecto (autocorrelación serial), no corregida
  aquí; se documenta, no se inventa un ajuste.
* `volatilidad(serie: pd.Series) -> float`: `serie.std(ddof=1)`. `NaN`
  si `len(serie) < 2`.
* `sharpe(serie: pd.Series, periodos_por_anio: float = 25.2) -> float`:
  `serie.mean() / serie.std(ddof=1) * sqrt(periodos_por_anio)`. `NaN`
  si `std` es `0` o `NaN`, o si `len(serie) < 2`. `periodos_por_anio`
  por defecto `25.2` (≈ 252 sesiones / 10 de paso — una fecha de corte
  nueva cada 10 sesiones hábiles).
* `max_drawdown(serie: pd.Series) -> float`: `equity = (1 +
  serie).cumprod()`; resultado `= (equity / equity.cummax() -
  1).min()`. `NaN` si `serie` está vacía.

### Métricas sobre señales individuales

* `hit_rate(senales: pd.DataFrame, columna_retorno: str =
  "retorno_30d") -> float`: fracción de filas con
  `columna_retorno > 0` — **estrictamente mayor que cero, `0.0` exacto
  NO cuenta como acierto** (misma convención que `frac_positivo` de
  `prl.reverse_winners.exp005._metricas` en la corrida original, que
  usa `v30 > 0`, no `>= 0` — se declara así explícitamente porque es
  fácil confundirlo). Sobre las filas no-`NaN`. `NaN` si no hay filas
  no-`NaN`.
* `turnover_por_fecha(composiciones: dict[pd.Timestamp, set[str]]) ->
  pd.Series`: `composiciones` ya viene con las fechas en el orden
  deseado (no se reordena — el llamador decide el orden cronológico).
  Para cada fecha a partir de la segunda, `turnover =
  max(len(entradas), len(salidas)) / len(simbolos_t_menos_1)`, con
  `entradas = simbolos_t - simbolos_t_menos_1` y `salidas =
  simbolos_t_menos_1 - simbolos_t` (fracción mínima garantizada de la
  composición anterior que cambió — nota de implementación v1.1: la
  primera versión de este contrato decía
  `symmetric_difference/anterior`, pero el caso de prueba 6 siempre
  exigió `max(entradas,salidas)/anterior`; se corrige la prosa para
  que coincida con lo realmente probado e implementado, sin volver a
  despachar por un cambio que no afecta ningún resultado ya
  reportado). `NaN` si `simbolos_t_menos_1` está vacío. La primera
  fecha no tiene valor (no
  aparece en el resultado — no hay turnover sin una fecha anterior).
* `concentracion_del_efecto(senales: pd.DataFrame, columna_retorno: str
  = "retorno_30d", top_n: int = 5) -> dict`: `media_total =
  mean(columna_retorno)` (sobre no-`NaN`). `media_sin_top_n` = media
  de `columna_retorno` **excluyendo** las `top_n` filas con el valor
  más alto de `columna_retorno` (si hay empates en el límite, se
  excluyen exactamente `top_n` filas, desempatadas por índice original
  — el orden de `senales.nlargest(top_n, columna_retorno)`, sin
  reordenar más). Devuelve `{"media_total": float,
  "media_sin_top_n": float, "depende_de_pocas_senales": bool}` — el
  booleano es `True` si `media_sin_top_n <= 0` mientras `media_total >
  0` (el resultado positivo total se explica solo por un puñado de
  señales extraordinarias). Si `len(senales) <= top_n`, no hay
  suficientes filas para excluir — `media_sin_top_n = NaN`,
  `depende_de_pocas_senales = False` (no se puede afirmar dependencia
  sin suficientes observaciones para probarla).

### Comparación contra benchmark

* `exceso_vs_benchmark(serie_bucket: pd.Series, serie_benchmark:
  pd.Series) -> pd.Series`: `serie_bucket - serie_benchmark`, alineado
  por índice (`pd.Series.sub`, que ya deja `NaN` donde falta un lado —
  sin relleno). Serie por fecha, no un escalar — el resumen (media del
  exceso) lo calcula el llamador con `.mean()` si lo necesita.

### Desgloses

* `desglose_por_periodo(senales: pd.DataFrame, columna_fecha: str =
  "fecha", columna_retorno: str = "retorno_30d", frecuencia: str =
  "Q") -> pd.DataFrame`: agrupa `senales` por
  `pd.PeriodIndex(senales[columna_fecha], freq=frecuencia)`
  (`frecuencia="Q"` = trimestre calendario, el valor por defecto —
  alias de `pandas.Period`, no de `pandas.offsets`: usar `"Q"`/`"M"`,
  **no** `"QE"`/`"ME"`, que son alias de *offset* y no de `Period` —
  "M" para mensual si se pide explícitamente). Por grupo: `media`,
  `mediana`, `hit_rate` (misma fórmula que arriba, sobre ese
  subconjunto), `n` (conteo de filas). Índice = el periodo (como
  texto, `str(periodo)`, ordenado cronológicamente), columnas
  `["media", "mediana", "hit_rate", "n"]`.
* `desglose_por_regimen_vix(senales: pd.DataFrame, vix_por_fecha:
  pd.Series, columna_fecha: str = "fecha", columna_retorno: str =
  "retorno_30d") -> pd.DataFrame`: para cada fecha única en
  `senales[columna_fecha]`, busca el valor de `vix_por_fecha` en esa
  fecha exacta (`vix_por_fecha.reindex(fechas_unicas)` — si no hay un
  valor exacto esa fecha, `NaN`, sin relleno hacia adelante). Calcula
  terciles **sobre las fechas únicas presentes en `senales`** (no
  sobre todo el histórico de VIX): `rank(pct=True)` de esos valores,
  `"bajo"` si `< 1/3`, `"medio"` si `< 2/3`, `"alto"` en otro caso;
  fechas con VIX `NaN` quedan en un grupo `"sin_dato"` aparte, no se
  excluyen ni se asignan a un tercil al azar. Une esa etiqueta de
  vuelta a cada señal (por fecha) y agrupa igual que
  `desglose_por_periodo` (`media`, `mediana`, `hit_rate`, `n`), índice
  = `["bajo", "medio", "alto", "sin_dato"]` (los que no tengan
  ninguna señal, fila con todo `NaN`/`n=0`, no se omiten de la tabla).
* `desglose_por_volatilidad(senales: pd.DataFrame, columna_vol: str =
  "vol_realizada_20d_cruda", columna_retorno: str = "retorno_30d") ->
  pd.DataFrame`: terciles de `senales[columna_vol]` (valor crudo de la
  propia señal, no percentil — cada fila ya trae su propio valor de la
  feature), mismo patrón de `rank(pct=True)` con cortes en 1/3 y 2/3,
  mismas columnas de salida que arriba, índice `["bajo", "medio",
  "alto"]` (aquí no aplica "sin_dato": si la columna tiene `NaN`, esa
  fila se excluye del desglose antes de calcular terciles, declarado
  así — distinto del caso VIX porque esta columna es parte de la señal
  misma, no un dato externo que pueda faltar por fecha).

### Etiqueta final (fijada en `FORWARD_VALIDATION.md`, no ajustable después de ver resultados)

* `etiqueta_forward(n_fechas_acumuladas: int, supera_los_5_benchmarks:
  bool, depende_de_pocas_senales: bool) -> str`: `"inconclusa"` si
  `n_fechas_acumuladas < 10`; si no, `"negativa"` si NO
  `supera_los_5_benchmarks`; si no, `"inconclusa"` si
  `depende_de_pocas_senales`; si no, `"favorable"`.

### Casos de prueba obligatorios

1. **`serie_por_fecha`**: 2 fechas con 2 señales cada una → media
   correcta por fecha; `senales` vacío → `Series` vacía.
2. **`retorno_acumulado`**: serie `[0.10, -0.05, 0.10]` →
   `1.10*0.95*1.10 - 1` calculado a mano; serie vacía → `NaN`.
3. **`volatilidad`** y **`sharpe`**: serie conocida de 3+ valores,
   comparar contra cálculo manual; serie de 1 valor → ambas `NaN`.
4. **`max_drawdown`**: serie `[0.10, -0.20, 0.05]` → drawdown calculado
   a mano sobre la curva de equity compuesta.
5. **`hit_rate`**: 10 señales sintéticas, 6 positivas → `0.6`; todas
   `NaN` → `NaN`.
6. **`turnover_por_fecha`**: 3 fechas sintéticas con composiciones
   `{A,B}`, `{A,C}`, `{A,C,D}` → turnover de la 2ª fecha = 1/2 (B sale,
   C entra, sobre tamaño anterior 2), turnover de la 3ª = 1/2 (D entra,
   sobre tamaño anterior 2); primera fecha no aparece en el resultado.
7. **`concentracion_del_efecto`**: 10 señales sintéticas donde quitar
   las 2 de mayor retorno vuelve la media `<= 0` mientras la media
   total es positiva → `depende_de_pocas_senales=True`; un caso donde
   la media sin esas 2 sigue siendo positiva → `False`;
   `len(senales) <= top_n` → `media_sin_top_n=NaN`,
   `depende_de_pocas_senales=False`.
8. **`exceso_vs_benchmark`**: dos series con índices parcialmente
   distintos → resta alineada, `NaN` donde falta un lado.
9. **`desglose_por_periodo`**: señales sintéticas en 2 trimestres
   distintos → 2 filas, métricas correctas por grupo.
10. **`desglose_por_regimen_vix`**: 6 fechas sintéticas con VIX
    conocido (2 bajas, 2 medias, 2 altas) y una fecha sin dato de VIX
    → 4 filas (`bajo/medio/alto/sin_dato`), la de `sin_dato` con
    exactamente las señales de esa fecha.
11. **`desglose_por_volatilidad`**: señales sintéticas con
    `vol_realizada_20d_cruda` conocida, terciles verificados a mano;
    una fila con `NaN` en esa columna queda excluida.
12. **`etiqueta_forward`**: los 4 casos de la tabla de prioridad,
    incluido que `n_fechas_acumuladas < 10` gana aunque el resto sería
    `"favorable"`.

Todas las tablas de prueba son sintéticas, construidas a mano (sin red,
sin datos reales).

## `prl.reverse_winners.forward_runner`

Aplica el bucket **congelado** (y los baselines, y `SPY` como
referencia) sobre un conjunto de fechas de corte ya determinadas como
"nuevas" — a diferencia de `exp005.py`, **nunca descubre ni
selecciona** nada; solo ejecuta una regla fija sobre fechas dadas.
Tests en `tests/reverse_winners/test_reverse_winners_forward_runner.py`.
Reutiliza `features.calcular_features_simbolo`,
`features.normalizar_percentil_cross_sectional`, `grid.aplicar_bucket`,
`baselines.*`, y de `exp005`: `ajustar_ohlc`, `retorno_forward` (se
importan, **se llaman con la firma exacta que ya tienen, documentada
en sus propios contratos — nunca se adivina el orden de argumentos
probando combinaciones, nunca se reimplementa su lógica "por si acaso"
la llamada real falla**). Regla transversal obligatoria: un
`try/except` que oculte un `TypeError`/`KeyError` de una llamada mal
hecha y la reemplace por un resultado vacío o por una reimplementación
propia **no es aceptable en este módulo** — si una llamada a una
función ya probada falla, la excepción se propaga (el llamador de
`construir_senales_para_fechas`, no esta función, decide qué hacer con
un error). El único manejo de excepción permitido explícitamente es el
ya descrito en el pre-registro: un símbolo sin archivo `.parquet` se
omite.

* `construir_senales_para_fechas(inputs_dir: Path, universo_path: Path,
  fechas: list[pd.Timestamp], bucket_congelado: dict, benchmark: str =
  "SPY", min_historia: int = 252) -> dict[str, pd.DataFrame]`:
  * Carga universo + benchmark igual que el paso 1 de `exp005.run`
    (mismo manejo de símbolos sin archivo: se omiten, sin excepción).
  * Para cada símbolo, features de historia completa — **llamada
    exacta, los dos argumentos posicionales son obligatorios, no
    tiene valor por defecto**: `features.calcular_features_simbolo(
    df_ajustado, benchmark_ajustado.reindex(df_ajustado.index))`
    (idéntica línea que usa `exp005.run` en su paso 2 — **copiarla
    literal, no omitir el segundo argumento ni envolver la llamada en
    un `try/except` que la convierta en silencio en un `DataFrame`
    vacío si falla**: un error aquí debe propagarse, no esconderse).
    Un único `calcular_features_simbolo` por símbolo (sobre toda su
    historia), no uno por fecha. También `retorno_forward` a
    10/20/30/60 días sobre el mismo `close` ajustado.
  * Para cada fecha en `fechas` (ya se asume que tiene retorno de 30
    días completo — esta función no lo valida, es responsabilidad del
    llamador): construye la tabla cross-sectional (mismo criterio dual
    de elegibilidad que `exp005.run` paso 4: ≥`min_historia` filas de
    precio original **y** fila de features sin `NaN`), normaliza por
    percentil, aplica:
    * `bucket_congelado` → método `"ganador"`: llama **literalmente**
      `grid.aplicar_bucket(bucket_congelado, tabla_norm)` — **en ese
      orden exacto de argumentos** (`variant: dict` primero,
      `features_percentil: pd.DataFrame` segundo; es el orden real de
      la firma ya implementada y probada de `grid.aplicar_bucket`,
      ver `src/prl/reverse_winners/grid.py`). **Prohibido**: adivinar
      el orden de argumentos probando varias combinaciones, envolver
      la llamada en un `try/except` genérico que oculte un error de
      firma, o reimplementar la lógica de umbrales por cuenta propia
      como alternativa/respaldo — si la llamada falla, debe propagar
      la excepción, no devolver una selección calculada de otra
      forma. El caso de prueba 1 exige que el resultado de esta
      función coincida, símbolo por símbolo, con llamar
      `grid.aplicar_bucket` directamente con los mismos datos — no
      basta con verificar que las fechas sean correctas.
    * `baselines.baseline_momentum_simple` → `"baseline_momentum_simple"`.
    * `baselines.baseline_buy_hold` (sobre la lista de elegibles esa
      fecha) → `"baseline_buy_hold"`.
    * `baselines.baseline_rsi_simple` → `"baseline_rsi_simple"`.
    * `baselines.baseline_combo_ingenuo` (sobre `features_crudas`) →
      `"baseline_combo_ingenuo"`.
    * `"spy"`: una sola señal por fecha, `ticker="SPY"`,
      `retorno_30d` = el propio retorno forward de 30 días de `SPY` esa
      fecha (de su serie `retorno_forward(close_ajustado, 30)` — no
      pasa por el filtro de elegibilidad del universo, es el índice
      mismo).
  * Para cada método, cada señal es un `dict` con `fecha`, `ticker`,
    `retorno_10d`, `retorno_20d`, `retorno_30d`, `retorno_60d`, y
    `vol_realizada_20d_cruda` (valor crudo de esa feature para ese
    símbolo esa fecha — **no** aplica a la señal de `"spy"`, que no
    tiene esa columna).
  * Devuelve `{"ganador": pd.DataFrame, "baseline_momentum_simple":
    pd.DataFrame, "baseline_buy_hold": pd.DataFrame,
    "baseline_rsi_simple": pd.DataFrame, "baseline_combo_ingenuo":
    pd.DataFrame, "spy": pd.DataFrame}` — cada `DataFrame` puede tener
    0 filas (sin excepción) si ninguna fecha tuvo señales de ese
    método.

### Casos de prueba obligatorios

1. **Caso de referencia completo, direcciones "alto" y "bajo"**:
   universo sintético de 6-8 símbolos con historia suficiente (≥260
   filas) + `SPY`, 2 fechas de corte sintéticas. Probar **dos**
   buckets congelados sobre los mismos datos: uno con una sola feature
   dirección `"alto"`, otro con una sola feature dirección `"bajo"` —
   para cada uno, calcular por separado (en el test, llamando
   `grid.aplicar_bucket` directamente sobre la tabla de percentiles
   esperada) qué símbolos debía seleccionar, y verificar que el
   conjunto de `ticker`s en el `DataFrame` `"ganador"` de
   `construir_senales_para_fechas` coincide **exactamente** (no un
   subconjunto, no un superconjunto) con ese cálculo independiente —
   este caso existe específicamente para atrapar un error de
   "mirroring" del umbral en la dirección `"bajo"` (percentil
   `p` dirección `"bajo"` selecciona `valores <= 1 - p`, **no**
   `valores <= p`).
2. **`"spy"`**: con 2 fechas, el método `"spy"` tiene exactamente 2
   filas, `ticker="SPY"` en ambas, valores iguales a
   `retorno_forward(close_SPY_ajustado, 30)` en esas fechas.
3. **Símbolo sin archivo**: se omite sin excepción (igual que
   `exp005.run`).
4. **Elegibilidad**: un símbolo con <252 filas de historia en una
   fecha dada queda fuera de la tabla cross-sectional esa fecha (no
   aparece en ningún método esa fecha).
5. **Determinismo**: dos llamadas idénticas dan `DataFrame`s idénticos
   (sin aleatoriedad en ninguna parte de esta función).

Todos los datos de prueba son sintéticos, construidos a mano.

## `prl.reverse_winners.forward_check`

Determina qué fechas de corte son nuevas, acumula el log de señales
entre corridas sucesivas (persistido como JSON plano, sin pandas, para
que sobreviva entre ejecuciones del workflow programado), y calcula
las métricas del reporte sobre el log acumulado. Tests en
`tests/reverse_winners/test_reverse_winners_forward_check.py`. Reutiliza
`exp005.fechas_t0` y todas las funciones de `forward_validation` (no
reimplementa ninguna). Misma regla transversal que `forward_runner`:
**ninguna llamada a una función ya probada se envuelve en un
`try/except` que oculte un error de firma o la reemplace por una
reimplementación propia** — un error se propaga.

* `determinar_fechas_nuevas(calendario: pd.DatetimeIndex,
  ultima_fecha_procesada: pd.Timestamp, discovery_start: str =
  "2010-01-01", paso_dias: int = 10, ventana_forward: int = 30) ->
  list[pd.Timestamp]`: `todas = exp005.fechas_t0(calendario,
  inicio=discovery_start, paso=paso_dias)` — **se reutiliza esta
  función tal cual, no se reimplementa el grid de fechas** (debe
  coincidir exactamente con la grilla de la corrida original, ancla en
  `discovery_start`, no en `ultima_fecha_procesada`). De esas, recorta
  a las que tienen `ventana_forward` sesiones de `calendario` después
  (igual criterio que `exp005.run`), y de esas devuelve solo las
  estrictamente posteriores a `ultima_fecha_procesada`. Lista vacía si
  no hay ninguna — **no es un error, es el caso esperado la mayoría de
  las veces que corre este chequeo**.
* `actualizar_log(log_existente: dict[str, list[dict]],
  nuevas_senales: dict[str, pd.DataFrame]) -> dict[str, list[dict]]`:
  `log_existente` y el valor de retorno son `dict[método, lista de
  señales como dict]` (formato JSON-plano, una entrada por señal, cada
  una con al menos `fecha` como string ISO y `ticker`) — representación
  elegida porque debe persistirse en disco entre corridas del workflow
  sin depender de serialización de pandas. Para cada método en
  `nuevas_senales` (mismas 6 claves que `forward_runner`:
  `"ganador"`, los 4 baselines, `"spy"`), convierte el `DataFrame` a
  lista de `dict` (`fecha` → `.isoformat()`) y la agrega a la lista ya
  existente de ese método (`log_existente.get(metodo, [])`) —
  **deduplicando** por la tupla `(fecha, ticker)`: si una señal con esa
  tupla ya existe en el log, no se duplica (permite volver a correr el
  chequeo sobre el mismo rango de fechas sin ensuciar el log,
  idempotente). El orden final de cada lista queda ordenado por
  `fecha` ascendente.
* `calcular_metricas_reporte(log_acumulado: dict[str, list[dict]],
  vix_por_fecha: pd.Series, ultima_fecha_original: str =
  "2026-09-30") -> dict`: reconstruye un `pd.DataFrame` por método a
  partir de `log_acumulado[metodo]` (vacío si la clave no existe o la
  lista está vacía), y calcula, usando **únicamente** funciones ya
  implementadas de `forward_validation` (no fórmulas nuevas en este
  módulo):
  * `n_fechas_acumuladas`: número de fechas únicas en
    `log_acumulado["ganador"]` (0 si está vacío).
  * `n_senales_ganador`: `len(log_acumulado["ganador"])`.
  * Para `"ganador"`, cada baseline, y `"spy"`: `retorno_acumulado`,
    `sharpe`, `max_drawdown` (los 3 sobre `serie_por_fecha` de ese
    método), `hit_rate` (sobre las señales individuales).
  * `exceso_vs_momentum` = media de `exceso_vs_benchmark(serie_por_
    fecha("ganador"), serie_por_fecha("baseline_momentum_simple"))`
    (ignorando `NaN`); `exceso_vs_spy` análogo contra `"spy"`.
  * `concentracion` = `evaluation.concentracion_maxima` (del paquete
    `prl.reverse_winners.evaluation`, se importa) sobre el `DataFrame`
    de `"ganador"` completo.
  * `leave_one_ticker_out` = `evaluation.leave_one_ticker_out_signo`
    sobre el `DataFrame` de `"ganador"` completo.
  * `concentracion_del_efecto` = `forward_validation.
    concentracion_del_efecto` sobre `"ganador"`.
  * `desglose_periodo`, `desglose_vix`, `desglose_volatilidad`: los 3
    desgloses de `forward_validation` sobre `"ganador"`.
  * `supera_los_5_benchmarks` = `retorno_acumulado("ganador") >
    retorno_acumulado(m)` para cada uno de los 5 (`AND` de las 5
    comparaciones; `False` si algún `retorno_acumulado` es `NaN`).
  * `label` = `forward_validation.etiqueta_forward(n_fechas_acumuladas,
    supera_los_5_benchmarks,
    concentracion_del_efecto["depende_de_pocas_senales"])`.
  * `ultima_fecha_original`: el parámetro tal cual (para que el
    reporte pueda mostrar desde cuándo empieza el periodo forward).
  Devuelve un `dict` con todas esas claves (los `pd.Timestamp`/`NaN` se
  convierten a `str`/`None` antes de devolver — este `dict` debe ser
  directamente serializable a JSON con `json.dumps`, sin pasos
  adicionales por parte del llamador).

### Casos de prueba obligatorios

1. **`determinar_fechas_nuevas`**: calendario sintético donde se conoce
   a mano qué fechas del grid de paso 10 (anclado en `discovery_start`)
   quedan después de `ultima_fecha_procesada` y tienen ventana completa
   → lista exacta esperada; `ultima_fecha_procesada` posterior a la
   última fecha con ventana completa → lista vacía.
2. **`actualizar_log` deduplica**: `log_existente` con una señal
   `(fecha=X, ticker="A")`; `nuevas_senales["ganador"]` con esa misma
   señal repetida más una nueva `(fecha=Y, ticker="B")` → el resultado
   tiene exactamente 2 entradas para `"ganador"`, no 3.
3. **`actualizar_log` con log vacío**: `log_existente={}` → el
   resultado tiene las 6 claves, cada una con las señales nuevas tal
   cual (convertidas a dict, fechas en ISO).
4. **`calcular_metricas_reporte` con log vacío**: `log_acumulado` con
   las 6 claves en listas vacías → `n_fechas_acumuladas=0`,
   `n_senales_ganador=0`, `label="inconclusa"` (por el criterio de
   `etiqueta_forward`, `n_fechas_acumuladas < 10`), sin excepción.
5. **`calcular_metricas_reporte` caso con datos**: log sintético de
   ≥10 fechas construido a mano donde el método `"ganador"` supera
   claramente a los otros 4 en cada fecha → `supera_los_5_benchmarks
   == True`, `label == "favorable"` (si además
   `depende_de_pocas_senales` da `False` con esos datos — construir el
   caso para que así sea).
6. **Determinismo de `calcular_metricas_reporte`**: mismo
   `log_acumulado` dos veces → mismo `dict` (comparar
   `json.dumps(resultado, sort_keys=True)` de ambas llamadas).

Todos los datos de prueba son sintéticos, construidos a mano.

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
  `columna_retorno > 0` (sobre las no-`NaN`). `NaN` si no hay filas
  no-`NaN`.
* `turnover_por_fecha(composiciones: dict[pd.Timestamp, set[str]]) ->
  pd.Series`: `composiciones` ya viene con las fechas en el orden
  deseado (no se reordena — el llamador decide el orden cronológico).
  Para cada fecha a partir de la segunda, `turnover =
  len(simbolos_t.symmetric_difference(simbolos_t_menos_1)) /
  len(simbolos_t_menos_1)` (fracción de la composición anterior que
  cambió — entradas más salidas, sobre el tamaño anterior). `NaN` si
  `simbolos_t_menos_1` está vacío. La primera fecha no tiene valor (no
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

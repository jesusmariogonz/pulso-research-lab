# LOG — EXP-004 Short Pressure Reversal

## 2026-11-20 — Pre-registro

El usuario propuso el experimento completo (13 secciones: factores de
short pressure/price exhaustion, búsqueda automática de buckets
candidatos, 6 baselines, validación walk-forward, robustez, criterios
de etiqueta). Antes de diseñar nada se investigó viabilidad real de
datos:

* **Short volume diario (FINRA Reg SHO)**: confirmado accesible por
  HTTP directo, sin auth, desde 2019-01-02 (403 antes de esa fecha).
* **Short interest bi-mensual (FINRA)**: confirmado accesible por HTTP
  directo, sin auth, con `days_to_cover` y `change_pct` ya calculados
  por FINRA (no hay que derivarlos). Limitación real encontrada: no
  hay float histórico gratis point-in-time — se sustituye "short
  interest/float" por las 3 métricas que FINRA sí da directo.
* Se verificó (no se asumió) que las tablas de S&P 400/600 de
  Wikipedia son accesibles y parseables (6,062 celdas `<td>` detectadas
  en la de S&P 400) para construir el universo S&P 1500 sin tener que
  pelear con la protección anti-bot de iShares (intento fallido,
  documentado: la descarga directa de holdings de IWB devolvió HTML,
  no CSV).

Con la viabilidad confirmada, se preguntó al usuario dos decisiones
reales de alcance antes de bloquear nada: amplitud del universo
(eligió S&P 1500/Russell 1000 sobre S&P 500 solo o todo FINRA) y si
arrancar ya con el pre-registro aceptando que esto toma varias
sesiones, como EXP-002 (eligió arrancar ya).

Se escribió y bloqueó `PREREGISTRATION.md` v1: universo S&P 1500
actual, 3 familias de features normalizadas por percentil
cross-sectional, grilla cerrada de 140 variantes (5 umbrales de short
pressure × 4 de price exhaustion × 7 configuraciones de confirmación),
split discovery 2019-2022/validation 2023-2024H1/locked test
2024H2-2026, 6 baselines, criterios VALIDATED/REJECTED/INCONCLUSIVE
fijados antes de correr nada.

**Siguiente paso**: fase de infraestructura de datos (precios de
~1,500 acciones + short volume/interest de FINRA) — no se ha corrido
nada todavía, no se ha tocado ningún dato real.

## 2026-11-21 — Infraestructura de datos (universo, FINRA, precios)

Construidos 2 módulos nuevos, escritos directamente (no vía DeepSeek:
son plomería de red/parsing, mismo criterio que `build.py` existente —
`macro_vintage.py` sí fue vía DeepSeek por ser cómputo de
reconstrucción point-in-time, categoría distinta).

**`src/prl/data/equity_universe.py`** — universo S&P 1500: descarga
real de S&P 500 (GitHub) + S&P 400 + S&P 600 (Wikipedia, confirmado
parseable con `pandas.read_html` + `lxml`, agregado a `pyproject.toml`).
Normaliza símbolos tipo "BRK.B"→"BRK-B" (gotcha real de yfinance).
**Resultado real: 1,502 símbolos únicos** (S&P500=503, S&P400=400,
S&P600=603, con solapamiento esperado entre índices). Congelado en
`data/universes/sp1500_short_pressure.txt` + manifiesto con hash
SHA-256 de cada fuente cruda. Agregado a `data/catalog.yaml` como
`universes: sp1500_short_pressure`, reusando el mecanismo YA existente
(`trading_universe` ya lo usaba) — no hizo falta tocar `build.py`.
5 tests, todos sobre funciones puras (parsing/normalización/dedupe),
nunca contra la red real.

**`src/prl/data/finra.py`** — short volume diario + short interest
bi-mensual, con el mecanismo point-in-time explícito (`fecha_publicacion`
= settlement + 7 días hábiles; `ultimo_short_interest_vigente` nunca
devuelve un snapshot antes de su fecha de publicación real — probado
explícitamente con un caso que distingue "antes de publicarse" de
"después"). 8 tests sobre funciones puras.

**Bug real encontrado y corregido antes de confiar en el parseo**: el
archivo de short volume diario trae una línea de pie con el conteo de
registros (un solo campo, sin pipes, ej. "12343") que `pandas.read_csv`
no rechaza — la rellena con NaN en el resto de columnas, y revienta
después al convertir esa fila a fecha. Se corrigió descartando filas
incompletas antes de la conversión de tipos, con test de regresión
(`test_parse_short_volume_diario_descarta_linea_de_pie`).

**Descarga real completa 2019-02-01 → 2026-11-21** (filtrada al
universo de 1,502 símbolos antes de acumular, con `ThreadPoolExecutor`
de 10 hilos — ambas fuentes cubren TODO el mercado, no solo nuestro
universo):
* Short volume diario: 2,036 días hábiles intentados, **1,963
  exitosos**, 73 fallidos — los 73 son feriados bursátiles reales
  (verificados uno por uno contra el calendario: Good Friday, Memorial
  Day, Juneteenth, 4 de julio, Labor Day, Thanksgiving, Navidad, Año
  Nuevo, MLK, Presidents Day — cero fallos "raros"). 2,723,471 filas.
  Tiempo real: 224.4s (~3.7 min).
* Short interest bi-mensual: 187 settlements intentados, **186
  exitosos** — el único fallido (2026-11-13, el settlement de
  noviembre ajustado por caer el 15 en domingo) todavía no se ha
  publicado (7 días hábiles después caen después de hoy) — es el
  comportamiento point-in-time CORRECTO, no un error. 258,109 filas.
  Tiempo real: 31.7s.
* Ambas consolidadas en un parquet único por fuente (no miles de
  archivos sueltos) + `data/raw/finra_manifest.json`.

**Precios/indicadores (reusando `build.py` existente sin tocarlo, vía
`construir(only=["sp1500_short_pressure"])`)**: **1,501 de 1,502
símbolos exitosos** en 13.1 minutos. Único fallo: `CWEN-A` (Clearway
Energy clase A) — yfinance no devuelve datos para ese símbolo exacto
("possibly delisted"), probablemente necesita otro formato de ticker;
documentado en `data/manifest.json["fallidas"]` por el propio
mecanismo existente de `build.py`, no se ocultó ni se forzó.

**Suite completa: 207/207 tests pasan** (sin regresión en nada
existente). `data/raw/` creció a 461MB (gitignored, no se commitea —
mismo patrón que el resto del repo).

**Siguiente paso**: contrato de implementación (`IMPLEMENTATION_SPEC.md`)
para los módulos de cómputo vía DeepSeek (features, grid, baselines,
evaluation, orquestador) — todavía no empieza.

## 2026-11-21 — Corrección: bug de `construir(only=...)` en `build.py`

Antes de cerrar la fase de arriba, verificando el manifiesto final a
mano se encontró que `src/prl/data/build.py::construir()` siempre
partía de un manifiesto VACÍO, nunca cargaba el existente — correr
`construir(only=["sp1500_short_pressure"])` había borrado las 207
series de ETF/macro de EXP-001/EXP-002 de `data/manifest.json`
(SPY, GSPC, VIX, etc.), dejando solo las 1,501 acciones nuevas. Los
archivos crudos en `data/raw/` seguían intactos (nada se perdió de
verdad), pero el manifiesto —la prueba de hash/procedencia que
sostiene la reproducibilidad ya publicada de esos 2 experimentos—
quedó incompleto. Es un bug pre-existente de `build.py` (nunca antes
se había usado `only` con un universo nuevo sobre un manifiesto ya
poblado), no algo introducido por la corrida de EXP-004 en sí.

**Corrección**: `construir()` ahora carga el manifiesto previo (si
existe) como base y solo actualiza las series que procesa esa corrida
(limpiando su entrada vieja de `series`/`fallidas` antes de
reintentarla, para que una serie que antes falló y ahora tiene éxito
no quede duplicada en ambos lados). 4 tests de regresión nuevos en
`tests/test_build.py` (no existía ningún test para este módulo antes)
— cubren: corrida sin `only`, corrida con `only` no debe borrar una
serie de una corrida previa, re-correr una serie existente debe
actualizarla, y una serie que falló y luego tiene éxito debe salir de
`fallidas`.

Se restauró `data/manifest.json`/`quality_report.md` al estado previo
al bug (las 207 series intactas) y se volvió a correr la descarga real
del universo de EXP-004 con el código ya corregido — no hizo falta
re-descargar los datos de FINRA (módulo separado, no afectado).
**Resultado final correcto: 1,621 series únicas** (207 originales +
1,501 nuevas, con ~87 traslapes esperados entre el universo
`trading_universe` ya existente y el `sp1500_short_pressure` nuevo —
mismo ticker, la entrada queda con los datos de la corrida más
reciente, sin duplicarse). Único fallo: `CWEN-A`, igual que antes.

**Suite completa: 211/211 tests pasan** (207 + 4 nuevos). Pusheado.

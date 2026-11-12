# Infraestructura de datos: macro point-in-time (ALFRED)

**Estado:** diseño, previo a implementación. Prerrequisito de EXP-002
(decisión del responsable del proyecto, 2026-11-12).

## El problema que resuelve

`data/catalog.yaml` ya documenta por qué NFCI y STLFSI4 están excluidos:
son índices que se **revisan hacia atrás**. Si yo entreno una señal con el
valor de NFCI "de hoy" para una fecha de 2009, en realidad estoy usando
información que no existía en 2009 — la serie se corrigió años después.
Eso es look-ahead, y el pre-registro de EXP-001 lo prohíbe explícitamente.

El mismo problema aplica a **cualquier** serie macro publicada con
rezago y sujeta a revisión: CPI, PCE, producción industrial, desempleo,
M2, índices líderes, etc. `prl.data.build` hoy descarga la serie
**actual** vía `fredgraph.csv` (el valor con todas las revisiones ya
aplicadas) — sirve para "¿qué pasó?", no para "¿qué sabía el modelo en
ese momento?".

FRED resuelve esto con **ALFRED** (Archival FRED): para cada serie,
guarda todas las versiones ("vintages") que existieron, cada una con su
propio rango de vigencia (`realtime_start`, `realtime_end`).

## Qué vamos a construir

Un módulo nuevo, `prl.data.macro_vintage`, con dos responsabilidades
separadas:

1. **Descarga** (I/O, red, requiere `FRED_API_KEY`; análoga a
   `descargar_fred` en `build.py`, NO pasa por TDD con DeepSeek — es
   plomería, no cómputo): pide a ALFRED el historial completo de vintages
   de una serie con una sola llamada por serie.
2. **Reconstrucción point-in-time** (función pura, sin red, sin
   secretos; SÍ pasa por el ciclo TDD con DeepSeek vía
   `implement-module.yml`, con el contrato en `IMPLEMENTATION_SPEC.md`):
   dado el historial de vintages y una fecha de corte *D*, devuelve
   exactamente lo que un observador sabía en *D* — ni más, ni menos.

### Cómo se pide el historial completo de vintages a ALFRED

Verificado contra la documentación oficial
(`https://fred.stlouisfed.org/docs/api/fred/series_observations.html`)
el 2026-11-12:

```
GET https://api.stlouisfed.org/fred/series/observations
    ?series_id=<ID>
    &api_key=<FRED_API_KEY>
    &file_type=json
    &realtime_start=1776-01-01
    &realtime_end=9999-12-31
    &output_type=1
```

Con `output_type=1` (default) y una ventana de tiempo real que cubre
"siempre", ALFRED devuelve **todas** las filas `(date, value,
realtime_start, realtime_end)` que existieron: una fila por cada
combinación única de período observado × versión vigente. Una sola
llamada por serie trae el historial completo de revisiones — no hace
falta pedir día por día.

(La alternativa `vintage_dates=D&output_type=2` reconstruye el snapshot
completo tal como existía en *D*, pero requiere una llamada por fecha de
corte — correcto pero muy caro si necesitamos miles de fechas de corte
(un día de trading cada una). Por eso bajamos **un historial completo
una vez por serie** y reconstruimos localmente, en código puro, el valor
conocido en cualquier fecha de corte.)

### Qué significa cada fila

* `date`: el período que describe el dato (p. ej. "2015-06-01" para el
  CPI de junio 2015).
* `value`: el valor publicado para ese período, en esa versión.
  `realtime_start` ≤ `date` es **imposible** y es señal de datos
  corruptos (no se puede conocer un valor antes del período que
  describe) — se valida y se rechaza.
* `realtime_start` / `realtime_end`: el valor fue "la versión vigente"
  desde `realtime_start` hasta `realtime_end` (inclusive). Una revisión
  posterior cierra el `realtime_end` de la versión anterior y abre una
  nueva fila con `realtime_start` = fecha de la revisión.
* `realtime_end = "9999-12-31"` significa "la versión más reciente
  conocida hoy, vigente hasta nueva revisión".

### La función de reconstrucción (lo que resuelve el look-ahead)

Para una fecha de corte *D* (un día de trading cualquiera del backtest),
"lo que el modelo podía saber en *D*" es: entre todas las filas con
`realtime_start ≤ D ≤ realtime_end`, la que tiene el `date` (período
observado) más reciente. Si ninguna fila cumple la condición, el dato
**no existía todavía** en *D* → NaN explícito, nunca se rellena hacia
atrás ni se asume el valor "actual".

Esto es exactamente lo que el contrato en `IMPLEMENTATION_SPEC.md`
formaliza, con tests que incluyen series sintéticas (no se puede probar
esto contra la red real en un sandbox sin secretos).

## Series elegidas para EXP-002 (lista acotada, no "lo que se pueda
encontrar")

Siguiendo la misma disciplina del catálogo actual (ninguna serie sin
limitaciones documentadas), y limitando el alcance a lo que es
razonablemente point-in-time en FRED/ALFRED:

| id | FRED series_id | rol | rezago típico de primera publicación | notas |
|---|---|---|---|---|
| FED_BALANCE | WALCL | liquidez | ~semanal, pocos días | activos totales de la Fed |
| M2 | M2SL | liquidez | mensual, ~2 semanas | oferta monetaria M2 |
| CPI | CPIAUCSL | inflación | mensual, ~2 semanas | índice de precios al consumidor |
| PCE_PRICE | PCEPI | inflación | mensual, ~1 mes | deflactor de gasto personal |
| IND_PROD | INDPRO | crecimiento | mensual, ~2 semanas | producción industrial |
| UNEMP | UNRATE | crecimiento | mensual, ~1 semana | tasa de desempleo (sujeta a revisión por ajuste estacional) |
| LEADING | USSLIND | crecimiento | mensual, ~1 mes | índice líder de la Fed de St. Louis |
| FEDFUNDS | FEDFUNDS | política monetaria | mensual, inmediato | tasa de fondos federales efectiva |

**Deliberadamente fuera** (ya excluidas en `data/catalog.yaml` por otras
razones que ALFRED no resuelve):
* OAS ICE BofA (`BAMLH0A0HYM2`, `BAMLC0A0CM`): FRED solo entrega los
  últimos 3 años por licencia — es un límite de **disponibilidad**, no de
  look-ahead. ALFRED no soluciona esto. Seguimos usando `BAA10Y`/`AAA10Y`
  (ya en el catálogo, diarios, sin problema de revisión real porque son
  tasas de mercado, no estadísticas estimadas).
* % de acciones del S&P 500 sobre su SMA200: requiere constituyentes
  históricos point-in-time, no disponibles gratis. Sin cambios.

NFCI/STLFSI4 **no entran a esta lista** aunque en principio ALFRED podría
tener sus vintages: son índices compuestos cuya *metodología* se revisa
periódicamente (no solo sus inputs), lo que complica la interpretación de
"qué sabía el modelo". Preferimos construir nuestro propio índice de
condiciones financieras a partir de series primarias point-in-time
(spreads de crédito ya en catálogo + lo de esta tabla) en vez de heredar
un índice cuya definición cambia bajo nuestros pies.

## Qué falta para que esto corra de verdad

1. `FRED_API_KEY`: clave gratuita de FRED (registro en
   `https://fred.stlouisfed.org/docs/api/api_key.html`), guardada como
   secret de GitHub Actions (igual que `DEEPSEEK_API_KEY`). **Pendiente
   de confirmar con el responsable del proyecto si ya existe.**
2. El módulo `prl.data.macro_vintage` (contrato en
   `IMPLEMENTATION_SPEC.md`, implementado por DeepSeek vía
   `implement-module.yml`, revisado antes de aceptar).
3. Extender `prl.data.build` y `data/catalog.yaml` con un nuevo tipo de
   fuente `fred_vintage` que use este módulo y guarde el historial crudo
   de vintages (inmutable, con su propio SHA-256 en el manifiesto, igual
   que las demás series).
4. Correr `data-build.yml` para congelar la primera versión de estos
   datos y generar el manifiesto que EXP-002 citará al bloquear su
   pre-registro.

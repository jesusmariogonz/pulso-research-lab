# LOG — EXP-002 Growth-Max Global

## 2026-11-12

* **Depuración de `data-build.yml` contra la API real de ALFRED** (6
  corridas): (1) `FRED_API_KEY` no se inyectaba como variable de entorno
  al paso de descarga — corregido. (2) El error 400 "api_key is not
  registered" resultó ser engañoso: la clave era válida; el problema real
  eran los parámetros `realtime_start=1776-01-01` (el mínimo real es
  `1776-07-04`) y `realtime_end=9999-12-31` (la API no lo acepta como
  entrada, solo como valor de salida — hay que pedir hasta hoy y
  normalizar la versión vigente de vuelta a `9999-12-31`). Verificado
  probando la API directamente antes de cambiar el código, no a ciegas
  reintentando el workflow. (3) Con eso corregido, M2/PCE/producción
  industrial/FEDFUNDS seguían fallando por un chequeo **mío**, de más,
  en `parse_vintage_observations`: rechazaba revisiones a más de 50 años
  del dato original como "corruptas". Es un supuesto incorrecto — estas
  series SÍ se re-benchmarkean décadas después (cambios de metodología de
  la agencia publicadora), y es información real, no corrupción. Se quitó
  la regla de `IMPLEMENTATION_SPEC.md` y de `macro_vintage.py` (ningún
  test dependía de ella).
* Propuesta inicial del responsable del proyecto: cambiar la función
  objetivo respecto a EXP-001 (de "reducir drawdown sin sacrificar CAGR"
  a "maximizar crecimiento geométrico compuesto, aceptando pérdidas
  extremas"), con universo global de activos, biblioteca amplia de
  señales, régimen macro, motor de apuestas con Kelly/fractional Kelly,
  y una frontera de apetito de riesgo 0–100 con probabilidad de ruina.
* Revisión de factibilidad contra la infraestructura real del lab
  (`data/catalog.yaml`, `prl.data.build`): solo Yahoo + FRED (serie
  revisada, no point-in-time), sin point-in-time de constituyentes de
  acciones, sin datos de costo de margen/financiamiento por activo.
  Riesgo de combinatoria/pruebas múltiples señalado explícitamente.
* Tres decisiones del responsable del proyecto (vía pregunta estructurada):
  1. **Invertir primero en infraestructura macro point-in-time** (ALFRED)
     antes de pre-registrar EXP-002, en vez de arrancar solo con señales
     de mercado o declarar todo lo macro exploratorio desde el día 1.
  2. **Apalancamiento con tope realista + costo de préstamo explícito**
     pre-registrado (no leverage libre sin costo).
  3. **Grilla grande** de señales/construcción de portafolio, controlada
     con disciplina de **discovery / validation / locked test set**
     estricta (no solo corrección Deflated Sharpe sobre una grilla
     pequeña como en EXP-001).
* Se crea esta carpeta como **fase 0** (infraestructura), no como
  pre-registro todavía. El pre-registro de EXP-002 se escribe después de
  que la infraestructura macro point-in-time esté construida y validada.
* Verificada contra la documentación oficial de FRED
  (`fred.stlouisfed.org/docs/api/fred/series_observations.html`) la
  semántica de `realtime_start`/`realtime_end`/`output_type` de ALFRED.
  Diseño documentado en `DATA_INFRA_MACRO_VINTAGE.md`: una sola llamada
  por serie con `output_type=1` y ventana de tiempo real completa trae
  todo el historial de vintages; la reconstrucción point-in-time se hace
  localmente, en código puro (sin red), para cualquier fecha de corte.
* Escrito el contrato (`IMPLEMENTATION_SPEC.md`) y 17 tests
  (`tests/test_macro_vintage.py`) para `prl.data.macro_vintage`. Validado
  con una implementación de referencia **descartable** (no se commiteó)
  antes de mandar el contrato a DeepSeek, para no gastar iteraciones en
  un contrato con bugs. En el proceso se corrigió una ambigüedad propia
  (el chequeo "REALTIME_START_NO_CRECIENTE" era redundante con
  superposición; se unificó en `VENTANAS_INCONSISTENTES`, que cubre
  superposición y huecos de vigencia).
* Generalizado `prl.implement` (antes codificado a mano para
  `src/prl/emergency/*` y `experiments/EXP-001-*`) a un registro
  `MODULOS` que declara spec/destino/test por módulo, y el workflow
  `implement-module.yml` para leer el destino real del `verdict.json` de
  la corrida en vez de asumir la ruta de EXP-001. Esto es infraestructura
  del propio ciclo TDD, no un módulo de análisis — lo escribí yo
  directamente, no DeepSeek.
* Siguiendo el mismo patrón que EXP-001 usó para `exp001`/`daily`
  (commits "CI: reactiva los tests de..."), se agrega
  `--ignore=tests/test_macro_vintage.py` a los tres workflows que corren
  `pytest -q` completo (`data-build.yml`, `run-experiment.yml`,
  `daily-indicator.yml`) para no romper el cron semanal/diario mientras
  el módulo todavía no existe. Se retira ese `--ignore` cuando
  `macro_vintage.py` pase sus tests y se integre.
* **Pendiente de confirmar con el responsable del proyecto:** si ya
  existe `FRED_API_KEY` como secret de GitHub Actions (necesaria para la
  descarga real vía ALFRED; el `fredgraph.csv` actual no la necesita
  porque no da vintages).

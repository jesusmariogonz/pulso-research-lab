# EXP-003 — Validación estadística y robustez del motor de trading

**Estado:** `LOCKED`

Pre-registrado y bloqueado el 2026-11-18 en el repositorio
`jesusmariogonz/algo_trading_platform`
(`research/exp-003-validacion-motor-produccion/PREREGISTRATION.md`,
commit `8e147ba`), antes de correr ninguna capa. Este documento es una
copia fiel de ese pre-registro, adaptada al formato de este
repositorio — ver la "Nota de alcance" abajo sobre por qué este
experimento no sigue el pipeline propio de `prl` (DeepSeek-TDD,
`data/manifest.json`).

## Nota de alcance — por qué este experimento vive en otro repositorio

EXP-003 no valida nada del universo/catálogo de `pulso-research-lab`.
Valida la configuración de producción del **motor de trading
algorítmico** de `jesusmariogonz/algo_trading_platform` (3 buckets:
`largo_plazo`/`time_series_momentum`, `mediano_plazo`/`trend_following`,
`riesgo_alto`/`momentum_breakout` — ADR 0027 de ese repo), un sistema
distinto, con su propio pipeline de datos (yfinance vía
`src/data/download.py`/`src/indicators/compute.py`, no el
`data/catalog.yaml`/`manifest.json` de este repo) y sin la
infraestructura de DeepSeek-TDD que usan los experimentos EXP-001/
EXP-002. El código, los datos intermedios y los resultados completos
de las 7 capas viven ahí, versionados desde el día 1 (nunca
gitignored — ver ADR 0041 de ese repo, una lección aprendida
directamente de la disciplina de reproducibilidad de este laboratorio).

Esta entrada existe para que el experimento quede catalogado con el
mismo rigor científico que EXP-001/EXP-002, con una referencia
auditable de vuelta al repositorio y los commits donde realmente se
ejecutó — no para duplicar esa evidencia aquí.

**Referencia de la ejecución real:**
`jesusmariogonz/algo_trading_platform`, directorio
`research/exp-003-validacion-motor-produccion/`, commits
`8e147ba`..`c971560` (pre-registro → síntesis final), rama `main`.

## Pregunta

¿Tiene la configuración EXACTA de producción de hoy (no una variante,
no una mejora propuesta) de cada uno de los 3 buckets del motor de
trading una ventaja de rendimiento distinguible del azar — y, si la
tiene, esa ventaja es robusta a supuestos de ejecución realistas,
perturbaciones de parámetros, concentración sectorial y sesgo de
selección del universo?

## Hipótesis

* **H1 (alternativa):** la configuración de producción de cada bucket
  muestra una ventaja de Sharpe distinguible de (a) un reordenamiento
  al azar de los mismos retornos históricos (placebo) y (b) el mejor
  resultado esperable por puro azar dado el número real de
  configuraciones ya exploradas en la historia del proyecto (DSR sobre
  el espacio de búsqueda de los ADR) — y esa ventaja no depende de un
  parámetro específico, un sector específico, un supuesto de ejecución
  optimista, o de que el universo esté elegido con el diario de lo que
  ya ganó.
* **H0 (nula):** el rendimiento reportado no se distingue, con las
  pruebas de arriba, de lo que produciría un sistema sin ninguna
  ventaja real, una vez puestas estas pruebas.

A diferencia de EXP-001/EXP-002, **no es un experimento de una sola
hipótesis con una sola etiqueta**: son 3 estrategias × 7 capas
independientes, cada una con su propio criterio fijado de antemano. El
pre-registro original (ver cita abajo) fue explícito: "No es un
promedio ni una votación de las 7 capas... Si el usuario pide
explícitamente un semáforo agregado, eso se decide al final, con las 7
capas ya corridas y visibles, nunca antes."

## Alcance — qué se valida

La configuración de producción EXACTA de hoy: las 3 estrategias, sus
universos actuales, sizing por riesgo sobre equity actual, fricción
real (0.05%+0.05% por lado), blend SPY/GLD para cash ocioso. Se
excluye explícitamente: la canasta `benchmark_diversificado` (punto de
comparación, no lo que se valida) y los 2 candidatos de filtro de
sizing pendientes de un experimento anterior de ese mismo repositorio
(ADR 0033/0040) — cualquier decisión sobre ellos espera el resultado
de EXP-003, no al revés.

## Las 7 capas y su criterio (fijado antes de correr nada)

1. **Walk-forward rolling** (5 ventanas, 12m train/6m test, paso 4
   meses, sin filtro): VALIDATED si ≥4/5 ventanas con Sharpe OOS>0 y
   ninguna ventana aporta >60% del retorno; INCONCLUSIVE si
   exactamente 3/5, o alguna ventana con <10 operaciones; REJECTED si
   ≤2/5.
2. **Sesgo de supervivencia**: comparar universo curado a mano contra
   un universo neutral más amplio. VALIDATED si diferencia de retorno
   anualizado ≤30% relativo; INCONCLUSIVE si no es reconstruible con
   esfuerzo razonable; REJECTED si >30%.
3. **DSR + PBO sobre el espacio de búsqueda histórico** (Deflated
   Sharpe Ratio de Bailey & López de Prado, corrigiendo por el número
   real de configuraciones ya probadas en la historia documentada del
   proyecto; PBO vía Combinatorially Symmetric Cross-Validation):
   VALIDATED si DSR>0.95 Y PBO<0.5; INCONCLUSIVE si DSR entre 0.5-0.95
   o PBO no calculable; REJECTED si DSR≤0.5.
4. **Placebo con potencia verificada** (block-bootstrap de retornos
   diarios, NUNCA de la señal ya generada — lección directa de
   EXP-002: un placebo mal especificado puede tener potencia
   estadística cero sin ser obvio; se verifica la varianza entre
   réplicas ANTES de interpretar cualquier percentil): VALIDATED si el
   Sharpe real cae en el percentil ≥95 con potencia confirmada;
   INCONCLUSIVE si no hay potencia confirmada o percentil 80-95;
   REJECTED si percentil <80 con potencia confirmada.
5. **Cross-sectional leave-one-group-out**: VALIDATED si quitar
   cualquier grupo/sector individual no hace caer el Sharpe más de
   40%; INCONCLUSIVE si algún universo tiene <3 grupos distinguibles;
   REJECTED si algún grupo individual causa una caída >40% o vuelve el
   Sharpe negativo.
6. **Superficie de perturbación de parámetros** (±10%/±20%, un
   parámetro a la vez): VALIDATED si ningún punto dentro de ±15%
   produce una caída de Sharpe >50%; INCONCLUSIVE si la malla es
   demasiado ruidosa; REJECTED si alguna perturbación ≤15% sí la
   produce.
7. **Robustez a supuestos de ejecución** (fill al open del día
   siguiente + 2x fricción, combinados): VALIDATED si Sharpe>0 y
   retorno neto positivo bajo ambos supuestos pesimistas; REJECTED si
   no.

## Registro de cambios

* v1 (2026-11-18): pre-registro inicial, las 7 capas y criterios tal
  como quedan arriba.
* Corrección del 2026-11-19 (post-registro, documentada como tal, no
  retroactiva): se encontró que el harness compartido de las Capas 1,
  4, 5, 6, 7 nunca implementó el filtro de cross-sectional momentum
  que SÍ está activo en producción para `largo_plazo` desde un ADR
  anterior de ese repositorio — una discrepancia entre la
  implementación y el pre-registro, no un cambio de criterio. Se
  corrigió el harness y se re-corrieron esas 5 capas solo para
  `largo_plazo` (`mediano_plazo`/`riesgo_alto` no usan ese filtro, no
  se tocaron). Ver `RESULTADOS.md` para el detalle completo, incluidos
  los números "antes" y "después" sin borrar ninguno.

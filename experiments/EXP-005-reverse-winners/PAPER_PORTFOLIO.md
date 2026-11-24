# EXP-005 — Paper Portfolio (cartera virtual en vivo)

**Estado:** `LIVE` desde la primera corrida de
`.github/workflows/exp005-paper-portfolio.yml` (ver `run_paper_portfolio/
paper_portfolio.json` para el estado actual). No tiene veredicto — es
infraestructura de observación, no un experimento que se cierre con
`VALIDATED`/`REJECTED`.

Este documento existe para que nunca se confunda esto con la
validación forward (`FORWARD_VALIDATION.md`). Son dos cosas distintas
que comparten el mismo bucket congelado:

| | Forward Validation | Paper Portfolio (este documento) |
|---|---|---|
| Qué mide | Retorno agregado de 30 sesiones del bucket vs. 5 baselines, fecha por fecha | Una cartera con capital virtual: efectivo, posiciones, equity, drawdown |
| Cuándo puntúa una fecha | Solo cuando ya existe el retorno forward de 30 sesiones completo | En vivo, el mismo día de la fecha de corte — no espera a poder calificarla |
| Para qué sirve | Responder si el bucket sigue superando a los baselines fuera de la muestra original | Ver cómo se vería operar el bucket como cartera — capital, concentración, drawdown en el tiempo |
| Puede cerrarse con un veredicto | Sí (🟢/🟡/🔴, ver `FORWARD_VALIDATION.md`) | No — no es un experimento, es una vista operativa |

## 1. Lo que SÍ es el bucket ya validado (no cambia nada aquí)

Universo, elegibilidad, las 4 features, los umbrales exactos
(`vol_realizada_20d` alto P90, `drawdown_60d` bajo P90, `dist_max20`
bajo P90, `beta_60d` alto P75), la cadencia de fechas de corte (cada
10 sesiones, `exp005.fechas_t0`) y el horizonte de 30 sesiones son
**idénticos** a `FORWARD_VALIDATION.md` — mismo `BUCKET_CONGELADO`,
nunca reoptimizado. La detección de señales (`paper_portfolio.
detectar_senales`) delega en las mismas funciones ya probadas
(`features.calcular_features_simbolo`, `features.
normalizar_percentil_cross_sectional`, `grid.aplicar_bucket`) que usa
`forward_runner` — no hay una segunda implementación del bucket que
pueda divergir por error de un lado y no del otro.

## 2. Lo que es NUEVO aquí — reglas de cartera, nunca probadas por EXP-005

La corrida original de EXP-005 midió el retorno agregado de las
señales (media, mediana, % positivo) — **nunca construyó una cartera
con capital**. Convertir eso en algo que se pueda "ver operar" exige
reglas de sizing y ejecución que la validación original no tenía ni
necesitaba. Se documentan aparte, explícitamente, para que nadie las
confunda con algo ya validado:

* **Capital inicial**: USD $1,000 virtuales — la misma unidad de
  referencia que usa el resto del sistema de trading de jesus-site,
  para que sea comparable.
* **Tamaño de posición**: el efectivo disponible el día de una fecha
  de corte se reparte en **partes iguales** entre las señales nuevas
  de ese día. Si ya no queda efectivo (cartera totalmente invertida),
  no se abren posiciones nuevas hasta que madure alguna.
* **Señales repetidas del mismo símbolo**: si un símbolo vuelve a dar
  señal en una fecha de corte posterior mientras sigue abierta una
  posición previa, se abre una posición **nueva e independiente** —
  no se deduplica. Esto es fiel a cómo la validación original cuenta
  señales (cada `(fecha, ticker)` es una observación independiente),
  pero en una cartera real esto puede concentrar capital en los
  nombres más persistentes (ver limitaciones).
* **Salida**: exactamente al cumplirse 30 sesiones desde la entrada,
  al precio de cierre ajustado de ese día. Sin stop-loss ni control de
  riesgo por posición — la validación original tampoco midió ninguno
  (retorno crudo a 30 sesiones), así que agregar uno aquí sería una
  regla que nunca se probó.
* **Costos de transacción**: no se aplican — misma decisión y mismo
  motivo que `FORWARD_VALIDATION.md` (comparar manzanas con manzanas
  contra la corrida original, que tampoco los aplicó).

## 3. Cadencia y arranque

Corre semanalmente (domingos, después de `exp005-forward-check.yml`),
limitado por el mismo refresco semanal de datos del repositorio — a
diferencia del motor de producción de jesus-site (que sí corre
diario), esta cartera solo ve fechas nuevas una vez por semana, en
lotes.

**Primera corrida: sin backtest retroactivo.** La cartera arranca con
`fecha_inicio` = la última fecha disponible en el calendario el día
de esa primera corrida — no se simula hacia atrás. Es la misma lógica
que ya se usó para el Motor IBKR de jesus-site (arrancó con historial
corto el día que se prendió, nunca maquillado con un backtest). El
historial que se acumule después es 100% forward, igual de honesto
que la validación forward.

## 4. Limitaciones declaradas

* **Fragmentación**: en una fecha de corte típica pueden calificar
  decenas de símbolos a la vez (ej. 53 el 2026-11-11, verificado
  contra datos reales) — con $1,000 repartidos en partes iguales,
  cada posición puede valer unos pocos dólares. Es virtual, así que no
  hay problema de tamaño mínimo de operación, pero el número no debe
  leerse como "cuánto se invertiría realmente en cada nombre" si esto
  pasara a producción.
* **Concentración por persistencia**: un símbolo que califica varias
  fechas de corte seguidas puede terminar con varias posiciones
  abiertas simultáneas — la corrida original ya reportó baja
  concentración máxima por ticker (1.76%, `CLSK`) en su medición
  agregada, pero esta cartera no tiene ese mismo chequeo incorporado
  todavía; se puede agregar si el historial real lo amerita.
* **Precio faltante**: si a un símbolo le falta el precio de cierre
  justo el día que le toca entrar o salir, se usa el último precio
  conocido (marcado como `exit_price_estimado` en el registro interno)
  en vez de fallar o inventar un precio nuevo.
* **No sustituye la validación forward**: un resultado positivo o
  negativo de esta cartera no mueve el veredicto de
  `FORWARD_VALIDATION.md` — esa sigue siendo la fuente de verdad
  estadística. Esta cartera es la pieza que le faltaba al "Paper Lab"
  de Strategy Lab (jesus-site): ver el bucket operar con capital, no
  solo como estadística agregada.

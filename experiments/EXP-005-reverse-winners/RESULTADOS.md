# EXP-005 — Resultados

Corrida real sobre el universo S&P 1500 completo (`data/universes/
sp1500_short_pressure.txt`, 1,502 símbolos listados, 1,501 con datos —
`CWEN-A` sin archivo), con `prl.reverse_winners.exp005.run()` (commit
`025a906`), parámetros exactamente los fijados en `PREREGISTRATION.md`:
`discovery_start=2010-01-01`, `discovery_end=2018-12-31`,
`validation_end=2021-12-31` (locked test hasta la última fecha
disponible, 2026-11), `n_boot=10000`, `n_placebos=1000`,
`n_particiones_pbo=10`, `seed=0`. Tiempo de ejecución: 272 segundos.
Resultado completo en `run_real/results.json` (versionado en este
commit).

## Veredicto: `INCONCLUSIVE`

No es un "no sé" por falta de datos o por un error — es el resultado
correcto y honesto dado lo que el pre-registro exigía: el bucket
descubierto **sí supera a los 4 baselines** (incluido el de momentum
simple, el que de verdad importaba) con un margen que parece real, pero
**no sobrevive la corrección por haber probado 81 variantes** (Deflated
Sharpe Ratio muy por debajo del umbral exigido). Ninguna de las dos
mitades del resultado se omite para quedarse solo con la que conviene.

## Qué se descubrió en discovery (2010-2018)

De las 15 features candidatas, **4 discriminaron** por encima del
umbral (`|correlación punto-biserial| >= 0.05`) — ninguna feature
"inventada" para llegar a 5, el pre-registro no exigía llegar al
máximo:

| Feature | Dirección | Diferencia de medianas | Correlación punto-biserial |
|---|---|---|---|
| `vol_realizada_20d` | alto | +0.217 | **0.157** |
| `drawdown_60d` | bajo | −0.142 | −0.097 |
| `dist_max20` | bajo | −0.125 | −0.085 |
| `beta_60d` | alto | +0.096 | 0.061 |

Interpretación (aquí sí entra criterio, no solo el hecho): los
ganadores de 30 días, vistos en T0 (antes de ganar), tenían volatilidad
realizada alta, poco drawdown reciente, estaban cerca de su máximo de
20 días y tenían beta alto frente a SPY. Es, en esencia, "momentum con
volatilidad" — no exactamente el momentum de un solo factor que ya
documenta la literatura, pero tampoco una señal completamente nueva:
describe acciones que ya estaban subiendo con fuerza y volatilidad,
consistente con lo que un lector escéptico esperaría de antemano. La
grilla cerrada resultante fue `3^4 = 81` variantes (no 243: solo 4
features discriminaron, no 5 — el límite de 5 nunca se alcanzó y no se
forzó).

## El bucket ganador (elegido en validation 2019-2021, nunca visto el locked test antes)

`vol_realizada_20d: alto, P90 | drawdown_60d: bajo, P90 | dist_max20:
bajo, P90 | beta_60d: alto, P75` — el filtro más exigente disponible en
3 de las 4 dimensiones. Las 81 variantes sobrevivieron el filtro de
soporte (≥30 señales en discovery, ningún ticker >20% de las señales)
— con 1,501 símbolos y 227 fechas de corte en discovery, el soporte
nunca fue el problema.

## Resultado en locked test (2022-2026, ~5 años, bear market + rally de IA — nunca tocado hasta esta corrida)

| | Media retorno 30d | Mediana | % señales positivas |
|---|---|---|---|
| **Ganador** | **2.269%** | −0.358% | 49.4% |
| Baseline 1 — Momentum simple (Top 20%, mom 20d) | 1.941% | 1.119% | 53.7% |
| Baseline 2 — Buy & hold | 1.564% | 0.895% | 53.4% |
| Baseline 3 — RSI simple (mean-reversion) | 1.397% | 0.474% | 51.8% |
| Baseline 4 — Combo ingenuo sin búsqueda | 1.591% | 1.012% | 54.2% |

El ganador supera a los 4 baselines en media — incluido el de momentum
simple, la condición que el pre-registro marcó como la que de verdad
importa para que el experimento no fuera una redescripción tautológica
de momentum ya documentado. Nótese la mediana negativa pese a la media
positiva y el % de señales positivas por debajo de 50%: la distribución
está sesgada por una cola derecha de ganadores grandes (volatilidad
alta + beta alto = más dispersión de resultados, no solo más retorno
esperado) — un patrón consistente con lo que cabría esperar de un
filtro que selecciona explícitamente alta volatilidad realizada.

## Por qué `INCONCLUSIVE` y no `VALIDATED`

Los criterios de `VALIDATED` (pre-registrados, no ajustados después de
ver esto):

| Criterio | Umbral | Valor obtenido | ¿Cumple? |
|---|---|---|---|
| Supera los 4 baselines | sí | sí (ver tabla arriba) | ✅ |
| Bootstrap pareado vs. baseline 1 (bloques de 2 obs.) | ≥80% réplicas a favor | **87.93%** | ✅ |
| Deflated Sharpe Ratio (81 intentos) | **> 0.95** | **0.534** | ❌ |
| Ningún vecino de grilla revierte signo o destruye >50% | sí | sí (0 de 5 vecinos evaluados) | ✅ |
| Ningún ticker aporta >20% de las señales | sí | sí (`CLSK`, máximo **1.76%**, 54 de 3,067 señales) | ✅ |
| ≥20 señales independientes en locked test | ≥20 | **3,067** (promedio ~25.8 señales/fecha de corte) | ✅ |

Un solo criterio falla — pero es el que corrige por haber probado 81
variantes antes de quedarse con la mejor. Un DSR de 0.534 dice que,
después de esa corrección, la señal apenas se distingue del 50/50: es
exactamente el tipo de resultado que el diseño de EXP-005 existía para
detectar (ver "Pregunta" del pre-registro — el riesgo de
redescubrimiento tautológico de momentum, con el riesgo adicional de
sobreajuste por búsqueda de grilla). El bootstrap pareado (87.9%) y el
placebo (ver abajo) sugieren que el efecto no es puro ruido — pero el
DSR, que es la salvaguarda específicamente diseñada contra la
multiplicidad de intentos, no permite llamarlo validado con la
rigurosidad exigida de antemano.

**Tampoco es `REJECTED`**: ninguna de las 4 condiciones de rechazo se
cumple — el bucket sí supera al baseline 1, el DSR (0.534) está por
encima de 0.5 (el umbral de rechazo, no el de validación — son
umbrales distintos a propósito), ningún ticker concentra más del 20% de
las señales, y el placebo sí distingue el resultado del azar (ver
abajo). El resultado cae, correctamente, en la zona intermedia que el
pre-registro anticipó y nombró explícitamente.

## Robustez adicional (reportada, no determina la etiqueta por sí sola)

* **PBO (CSCV, 10 particiones, 252 combinaciones)**: **32.9%** —
  probabilidad de que la variante ganadora en in-sample sea en
  realidad mediocre out-of-sample. Ni alarmante (no roza 100%) ni
  tranquilizador (no está cerca de 0%): consistente con el DSR, apunta
  a una señal real pero débil frente al tamaño de la búsqueda.
* **Placebo**: con potencia confirmada (varianza no trivial entre
  réplicas), el retorno medio real del ganador queda en el percentil
  **99.7%** de 1,000 reordenamientos aleatorios del mismo tamaño — el
  resultado real es claramente mejor que el conjunto de señales al
  azar, lo cual es consistente con que haya *algo* real detrás del
  patrón, aunque no sea suficiente por sí solo para validar dado el
  criterio de DSR.
* **Leave-one-ticker-out**: 516 tickers únicos entre las señales del
  ganador en locked test; ninguno, al excluirlo, revierte el signo del
  efecto.
* **Concentración**: `CLSK` es el ticker más frecuente, con apenas
  1.76% de las señales — nada cerca del umbral de 20% que habría
  disparado un rechazo por riesgo idiosincrático.

## Qué significa esto para el objetivo original del experimento

La pregunta de EXP-005 no era "¿los ganadores tenían ciertas
características antes de ganar?" (eso ya se sabía, es casi tautológico
con la literatura de momentum) — era si esas características, usadas
como filtro, **superan claramente** un baseline de un solo factor. La
respuesta empírica, con el rigor pre-registrado: el filtro SÍ supera al
baseline en esta muestra, pero el margen no sobrevive la corrección por
el tamaño de la búsqueda (81 variantes) con la holgura que el
pre-registro exigió para llamarlo una ventaja validada. Es un "quizás,
pero no con suficiente confianza todavía" — ni la confirmación de una
nueva ventaja real, ni su descarte.

## Limitaciones declaradas (del pre-registro y del `IMPLEMENTATION_SPEC.md`, no nuevas)

* Fuerza relativa vs. sector y concentración por sector: fuera de
  alcance v1 (sin clasificación GICS en este laboratorio).
* MFE, MAE, máximo drawdown post-señal y tiempo-a-objetivo (+5%/+10%):
  fuera de alcance v1 (requieren seguimiento día a día, no solo
  retornos a horizontes fijos).
* Autocorrelación serial: las ventanas forward de 30 días se solapan
  entre sí (paso de 10 sesiones) — declarada, no corregida con un
  ajuste adicional de grados de libertad más allá del DSR/PBO ya
  aplicados.
* Universo S&P 1500 actual (no point-in-time): mismo sesgo de
  supervivencia ya declarado en EXP-004, heredado aquí sin cambios.

## Qué NO se hace a partir de este resultado

No se propone una fase de implementación operativa (el pre-registro
condicionaba eso a `VALIDATED`). No se "ajusta" el umbral de DSR
después de ver que 0.534 no lo alcanza — el criterio se fijó en el
pre-registro, antes de correr nada, y se mantiene. Si se quisiera
reducir la incertidumbre de este resultado intermedio, el camino
honesto sería una réplica con un periodo de validación/discovery
distinto o una muestra out-of-sample adicional — no reinterpretar el
mismo resultado con un criterio más laxo.

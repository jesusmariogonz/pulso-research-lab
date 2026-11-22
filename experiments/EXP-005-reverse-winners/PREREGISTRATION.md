# EXP-005 — Reverse Winners

**Estado:** `LOCKED`

Aprobado por el responsable del proyecto el 2026-11-22 y bloqueado con
el commit que añade esta línea. Desde este punto, cualquier cambio a
las reglas se registra en el *Registro de cambios* como nueva versión;
todo lo decidido después de ver resultados es **exploratorio** y no
puede mover la etiqueta final.

## Pregunta

¿Qué características observables, medidas el día en que todavía NO han
empezado a subir (T0), distinguen sistemáticamente a las acciones que
se convertirán en las mayores ganadoras de los siguientes 30 días
hábiles — y ese patrón, descubierto y validado fuera de muestra, genera
una ventaja real **por encima de una regla simple de momentum de un
solo factor**?

Esta última condición es el núcleo del diseño, agregada explícitamente
tras una discusión previa a este pre-registro: "los ganadores de 30
días tenían momentum alto antes de ganar" es casi tautológico — es
exactamente lo que ya documenta la literatura de momentum cruzado
(Jegadeesh & Titman, 1993) y lo que ya implementa en producción
`cross_sectional_momentum` (`algo_trading_platform`, ADR 0034). Este
experimento solo aporta algo nuevo si el bucket descubierto, con
varias características combinadas, supera CLARAMENTE a un baseline de
un solo factor — no si simplemente lo iguala con más parámetros y más
riesgo de sobreajuste.

## Hipótesis

* **H1 (alternativa):** existe una combinación de características
  medidas en T0 (momentum multi-horizonte, posición vs. medias
  móviles, volumen, RSI, volatilidad, fuerza relativa) que, usada como
  filtro, selecciona un subconjunto de acciones cuyo retorno a 30 días
  hacia adelante es superior al de un baseline de momentum de un solo
  factor, de forma distinguible del azar y consistente fuera de
  muestra.
* **H0 (nula):** ninguna combinación de la grilla supera al baseline de
  momentum simple de forma distinguible del azar fuera de muestra —
  cualquier ventaja observada es (a) redescubrimiento del factor
  momentum ya conocido, (b) producto de un puñado de eventos
  idiosincráticos (noticias, M&A, FDA, short squeeze) no repetibles, o
  (c) no sobrevive fuera de muestra.
* **H2 (anti-sobreajuste, obligatoria para validar):** la ventaja, si
  existe, sobrevive la corrección por selección múltiple (DSR sobre el
  tamaño real de la grilla), no depende de que un solo sector o <20%
  de los tickers concentre las señales, y es robusta a perturbar el
  umbral ganador a su vecino inmediato en la grilla.

## Universo

**Reutiliza el S&P 1500 ya construido para EXP-004** (`data/universes/
sp1500_short_pressure.txt`, 1,501 símbolos únicos, mismo manifiesto de
fuentes/hashes) — mismo universo, mismas limitaciones ya declaradas:
constituyentes ACTUALES (no point-in-time), elimina selección manual
con hindsight, no elimina sesgo de supervivencia completo. No hace
falta construir nada nuevo de universo para este experimento.

**Filtro de elegibilidad por ventana**: un símbolo participa en una
fecha de corte T0 solo si tiene ≥252 sesiones de historia previa
disponible (para que SMA200 y las demás features de largo plazo estén
bien calculadas, sin inventar datos) — esto excluye naturalmente a los
recién salidos a bolsa de las ventanas tempranas de su propia vida, sin
sesgo adicional: un inversor real en esa fecha tampoco habría podido
calcular esas features para un símbolo que aún no cotizaba suficiente.

## Datos — qué ya existe y qué hay que construir

| Qué | Estado |
|---|---|
| Precios OHLCV diarios del universo (2019-02→hoy mínimo, varios símbolos desde 1990) | **Ya existe** — infraestructura de EXP-004 (`data/manifest.json`, universo `sp1500_short_pressure`). Para este experimento se usa la historia completa disponible por símbolo (no acotada a la ventana de FINRA — este experimento no usa datos de short interest/volumen de FINRA en absoluto). |
| Indicadores derivados (SMA20/50/200, RSI14, ATR, momentum N días, volumen relativo, beta, fuerza relativa vs. SPY) | **No existe todavía** — `pulso-research-lab` no tiene un módulo de indicadores equivalente al de `algo_trading_platform`; se construye como parte de este experimento (`prl.reverse_winners.features`, vía DeepSeek, ver más abajo). |
| Fuerza relativa vs. sector (requiere clasificación GICS por símbolo) | **Limitación declarada**: no existe una clasificación sectorial de los 1,501 símbolos en este laboratorio. Se usan los 9 ETF sectoriales SPDR ya en `data/catalog.yaml` (XLK, XLE, XLF, XLV, XLP, XLU, XLY, XLI, XLB) solo si se construye una clasificación mínima viable (aproximación GICS a mano, mismo criterio ya usado en la Capa 5 de EXP-003 de `algo_trading_platform`); si el costo de construirla no se justifica, esta feature específica se declara **fuera de alcance de v1** y se documenta como tal, sin bloquear el resto del experimento (las demás ~14 features no dependen de clasificación sectorial). |

## Periodo y split (decidido por tamaño real de cobertura del universo, no arbitrario)

Verificado contra el manifiesto real de EXP-004 antes de fijar este
pre-registro: al 2010-01-01 el 74.6% del universo final (1,501
símbolos) ya tiene historia de precio; esa cobertura sube a 89% para
2018 y a 100% para 2026. Se eligió **2010-01-01** como inicio porque
da ~17 años de historia (muchas ventanas de 30 días independientes,
atacando directamente la debilidad de "pocos eventos" que limitó a
EXP-001/EXP-003) sin excluir una porción excesiva del universo final,
y porque cubre 3 regímenes de mercado bien distintos entre los 3
splits (ver abajo) — **no fue elegido buscando el mejor resultado**,
se decidió antes de calcular nada.

* **Discovery**: 2010-01-01 → 2018-12-31 (9 años) — aquí se extraen las
  características discriminantes y se filtra la grilla por soporte
  mínimo.
* **Validation**: 2019-01-01 → 2021-12-31 (3 años, incluye la caída y
  recuperación de COVID — régimen genuinamente distinto) — aquí se
  elige LA variante ganadora.
* **Locked test**: 2022-01-01 → 2026-11-21 (~5 años, incluye el bear
  market de 2022 y el rally de IA 2023-2026 — otro régimen distinto) —
  **nunca se mira hasta la corrida final**.

## Metodología — ventanas rolling (sin look-ahead)

1. **Ventana de etiquetado (solo para identificar "ganadores", nunca
   como entrada de ninguna regla)**: para cada fecha de corte T0 (una
   cada 10 sesiones hábiles dentro de cada split, para reducir
   solapamiento extremo entre observaciones consecutivas — se declara
   la autocorrelación serial residual como limitación conocida, igual
   que el resto del proyecto declara sus propias dependencias
   temporales), se calcula el retorno realizado T0→T0+30 de cada
   símbolo elegible. El **Top 10%** por ese retorno define "ganadores"
   de esa ventana — umbral fijo, no se explora como parte de la grilla
   (evita un grado de libertad adicional sin justificación).
2. **Features, medidas SOLO en T0** (nunca después — este es el punto
   donde un error de look-ahead sería más fácil de cometer, y se prueba
   explícitamente en los tests del módulo): momentum 5/10/20 días,
   distancia a SMA20/50/200, cruce SMA50/SMA200 (binario), ATR14,
   volatilidad realizada 20d, volumen relativo (vs. promedio 20d),
   volume spike (z-score de volumen 5d vs. 60d), RSI14, drawdown previo
   (desde el máximo de 60d), gap del día (open/close anterior - 1),
   fuerza relativa vs. SPY (retorno 20d del símbolo menos el de SPY),
   beta 60d vs. SPY, Sharpe 20d, distancia al máximo/mínimo de 20d,
   aceleración (momentum 5d menos momentum 20d). Todas normalizadas por
   percentil cross-sectional dentro del universo elegible ese día
   (misma convención que EXP-004).
3. **Discovery (solo en la ventana de discovery)**: para cada feature,
   comparar su distribución entre "ganadores" y el resto del universo
   elegible ese día (diferencia de medianas + correlación
   punto-biserial con la etiqueta de ganador) — identifica cuáles
   features discriminan de verdad, antes de construir ningún bucket.
   Si una feature no discrimina con una señal mínima pre-definida
   (|correlación punto-biserial| < 0.05), se excluye de la grilla de
   buckets — no se incluye "porque sí".
4. **Grilla de buckets candidatos**: sobre las features que sí
   discriminaron en el paso 3 (como máximo las 5 con mayor
   discriminación — límite fijado aquí para que la grilla quede
   acotada y declarada, no post-hoc), 3 umbrales cada una (percentiles
   bajo/medio/alto de cada feature, definidos de antemano como P60/P75/
   P90, o su espejo para features donde "bajo" es la dirección
   relevante). **Tamaño máximo de la grilla: 3^5 = 243 variantes** —
   cerrada y enumerada, igual estilo que EXP-002/EXP-004.
5. **Selección (dos fases, nunca sobre el locked test)**: filtro de
   soporte mínimo (≥30 señales independientes en discovery, ningún
   sector/ticker >20% de las señales) → ranking por retorno medio
   30d-forward en validation, entre las que pasaron el filtro.

## Targets

Retorno forward a 10/20/30/60 días; MFE; MAE; máximo drawdown después
de la señal; probabilidad de terminar positivo a 30 días; tiempo hasta
+5%/+10%.

## Baselines (el primero es el que de verdad importa)

1. **Momentum simple de un solo factor** — Top 20% por retorno de 20
   días, sin ningún otro filtro. **Este es el baseline que el bucket
   descubierto debe superar claramente — si no lo supera, el
   experimento no aporta nada nuevo, sin importar qué tan bien se vea
   contra los demás.**
2. **Buy & Hold** del universo completo.
3. **RSI simple** — Top 10% por RSI14 más bajo (mean-reversion puro,
   dirección opuesta a lo que este experimento busca — referencia de
   contraste).
4. **Combo ingenuo sin búsqueda** — momentum 20d>0 AND precio>SMA50 AND
   volumen relativo>1.2, umbrales fijos de referencia nunca elegidos
   por la grilla (mismo propósito que el baseline 6 de EXP-004: aislar
   cuánto aporta el PROCESO DE BÚSQUEDA sobre una combinación a ojo).

## Costos

0.05% comisión + 0.05% slippage por lado — mismo estándar de
`METHODOLOGY.md`.

## Validación y robustez

* **Sin look-ahead**: toda feature de T0 usa solo datos hasta el cierre
  de T0; el retorno "ganador" que define el Top 10% es SOLO para
  identificar qué estudiar en discovery, nunca se usa como insumo de
  ninguna regla (la regla final solo ve features de T0).
* **DSR** sobre las ≤243 variantes de la grilla real (el tamaño exacto
  se reporta, no se asume).
* **PBO** (CSCV) sobre las variantes con suficientes señales por
  partición temporal.
* **Placebo con potencia verificada**: mismo diseño que la Capa 4 de
  EXP-003/EXP-004 — señales en fechas aleatorias (mismo conteo que el
  bucket real), verificando varianza no-trivial entre réplicas antes
  de interpretar cualquier percentil.
* **Concentración (la salvaguarda específica contra "noticia
  idiosincrática, no patrón")**: el bucket se rechaza si >20% de sus
  señales en cualquier split vienen de un solo ticker, o si un leave-
  one-ticker-out revierte el signo del efecto.
* **Sensibilidad**: la grilla ya cubre los vecinos inmediatos de
  cualquier ganador (P60/P75/P90) — si el vecino revierte el signo o
  destruye >50% del efecto, se marca como posible sobreajuste.

## Criterios de éxito (fijados antes de correr)

* **`VALIDATED`**: en el locked test, el bucket ganador supera a **los
  4 baselines**, y en particular al Baseline 1 (momentum simple) por un
  margen donde el bootstrap pareado (bloques de 20 días) da ≥80% de las
  réplicas a favor — **y** DSR > 0.95 sobre el tamaño real de la grilla
  — **y** ningún vecino inmediato revierte el signo o destruye >50% del
  efecto — **y** ningún ticker aporta >20% de las señales del locked
  test — **y** ≥20 señales independientes en el locked test.
* **`REJECTED`**: no supera al Baseline 1 (momentum simple) en el
  locked test, o DSR ≤ 0.5, o el placebo (con potencia confirmada) no
  lo distingue de un reordenamiento al azar, o >20% de las señales
  vienen de un solo ticker.
* **`INCONCLUSIVE`**: cualquier otro caso — p. ej. supera al Baseline 1
  pero con pocas señales, o DSR entre 0.5-0.95, o es sensible a los
  vecinos de la grilla sin llegar a revertir el signo.

## Fuera de alcance

No toca ningún sistema de producción. Fuerza relativa vs. sector queda
fuera de v1 si construir la clasificación GICS mínima no se justifica
(ver tabla de datos) — se documentará esa decisión, no se omite en
silencio. Solo si resulta `VALIDATED` se propondría una fase aparte
(con su propio pre-registro) para evaluar una implementación operativa.

## Registro de cambios

| Fecha | Cambio | Commit |
|---|---|---|
| 2026-11-22 | Pre-registro inicial (v1), formalizando la propuesta del usuario ("Reverse Winners") con una condición de éxito agregada explícitamente (superar un baseline de momentum de un solo factor, no solo describir que los ganadores tenían momentum) tras discusión previa a este documento. Periodo (2010-2026) elegido por cobertura real verificada del universo de EXP-004, no arbitrariamente. | (este commit) |

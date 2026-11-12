# EXP-002 — Growth-Max Global Portfolio

**Estado:** `LOCKED`

Aprobado por el responsable del proyecto el 2026-11-12 y bloqueado con el
commit que añade esta línea. Desde este punto, cualquier cambio a las
reglas se registra en el *Registro de cambios* como nueva versión; todo
lo decidido después de ver resultados es **exploratorio** y no puede
mover la etiqueta final.

## Pregunta

¿Cuál es la máxima tasa de crecimiento geométrico compuesto que puede
obtenerse mediante un sistema sistemático de selección, asignación,
entrada/salida y apalancamiento sobre un universo global de activos (solo
ETFs/índices — ver `README.md` sobre por qué no hay acciones individuales
todavía), usando solo información disponible en cada momento (sin
look-ahead, incluido el macro vía `prl.data.macro_vintage`), y cuáles son
los costos y probabilidades de ruina asociados?

A diferencia de EXP-001, **no** se busca minimizar drawdown. La función
objetivo primaria es la tasa de crecimiento geométrico (log-wealth), sujeta
a un control explícito de probabilidad de ruina — no al revés.

## Hipótesis

* **H1 (alternativa):** existe una configuración sistemática (señales de
  momentum/trend/volatilidad/régimen macro + construcción de portafolio +
  apalancamiento acotado) cuyo CAGR en el *locked test set* es
  distinguible de cero y superior al de un benchmark pasivo global 60/40,
  en el punto de referencia "Growth50" (definido abajo).
* **H0 (nula):** no hay ventaja distinguible del azar o de un benchmark
  simple, una vez pagados los costos de transacción y de apalancamiento.
* **H2:** la ventaja (si existe) sobrevive la corrección por selección
  múltiple (Deflated Sharpe sobre el número real de variantes probadas) y
  el filtro de probabilidad de ruina fijado en la sección de selección. Si
  no, la complejidad no se justifica y el resultado se reporta como tal
  aunque H1 se cumpla de forma cruda.

## Universo (fijo — ningún activo más, ninguno menos)

Solo ETFs/índices del catálogo (`data/catalog.yaml`), nunca acciones
individuales (sin universo point-in-time de constituyentes disponible —
ver `README.md`). **65 instrumentos invertibles:**

| Grupo | Instrumentos (id de catálogo) | N |
|---|---|---|
| Renta variable amplia | SPY, QQQ, IWM, DIA, EFA, EEM, EWJ | 7 |
| Sectores SPDR | XLK, XLE, XLF, XLV, XLP, XLU, XLY, XLI, XLB | 9 |
| Renta variable por país | EWG, EWQ, EWU, EWL, EWI, EWP, EWN, EWA, EWH, EWS, EWZ, EWW, EWY, EWT, MCHI, INDA, EIDO, EZA, TUR, EPOL | 20 |
| Factores (USA) | MTUM, QUAL, USMV, VLUE | 4 |
| Bonos | TLT, IEF, SHY, BIL, HYG, LQD, TIP, EMB, BNDX, MBB | 10 |
| Commodities | GLD, SLV, USO, UNG, DBC, DBA | 6 |
| Divisas | UUP, FXE, FXY, FXB, FXF, FXC, FXA | 7 |
| REIT | VNQ, VNQI | 2 |

**Universo invertible por fecha:** un activo entra a la cartera en la
fecha en que *realmente* tiene datos (según el manifiesto), nunca antes —
esto es deliberado: la cartera en 2005 no pudo invertir en MCHI (no
existía). No se asume un "inicio común" único para todo el universo (eso
tiraría ~15 años de historial solo por los 4 factores, que arrancan en
2011-2013).

**Fecha de inicio del backtest:** la primera fecha en la que al menos
**40 de los 65** instrumentos tienen datos reales. **Confirmada contra el
manifiesto congelado (ver hash abajo): 2006-02-06** (el instrumento 40 en
sumarse es DBC). Cae bien antes de 2015, así que el discovery set es
válido — no hace falta la enmienda prevista para el caso de que cayera
después de 2015.

**Manifiesto de datos citado (SHA-256 de `data/manifest.json`):**
`bd5bae2b97b7725c30a8370e269aba0750fea976c63c0aaa48c07a0c7c7d490b`
(generado 2026-11-12T20:12:27Z, 207 series, 0 fallidas). Hallazgo
documentado (no bloqueante): CPI/PCE_PRICE/IND_PROD tienen huecos reales
en su historial de vintages entre ~1970 y 2003 (el archivo electrónico de
ALFRED no cubre completo esa época) — ver `data/quality_report.md`.

## Señales (familias fijas, combinadas — no se prueba cada familia aislada)

Todas se calculan con expanding/rolling windows sin look-ahead (igual
disciplina que `prl.emergency.features`). La señal compuesta de cada
activo es el promedio simple de las familias 1-3 (todas "momentum/trend");
la familia 4 es un overlay que solo se activa cuando el régimen (familia
5) indica rango, no tendencia.

1. **Momentum de serie de tiempo:** signo del retorno acumulado de
   `L` meses, `L ∈ {3, 6, 12}`.
2. **Tendencia (SMA):** signo de `precio / SMA(W) − 1`, `W ∈ {50, 100, 200}`
   días hábiles.
3. **Breakout (Donchian):** `+1` si el precio de hoy es el máximo de `B`
   días, `−1` si es el mínimo, si no `0`; `B ∈ {55, 252}` días hábiles.
4. **Reversión de corto plazo (overlay, solo en régimen de rango):**
   z-score de `(precio − media móvil) / desv. móvil`, ventana
   `Z ∈ {10, 20}` días.
5. **Régimen macro (point-in-time, vía `prl.data.macro_vintage`):** dos
   ejes fijos — liquidez (signo del cambio trailing de 6 meses de
   M2 + balance de la Fed, point-in-time) y crecimiento (signo del cambio
   trailing de 6 meses del índice líder USSLIND, point-in-time) — dan
   4 regímenes fijos (expansión/contracción de liquidez × crecimiento
   arriba/abajo de tendencia). En régimen de contracción de liquidez, la
   exposición bruta total se escala por un factor `k ∈ {0.5, 0.75}` (grilla).
6. **Volatilidad (no es señal direccional, es insumo de tamaño):**
   volatilidad realizada en ventana `V ∈ {20, 60}` días, usada por los
   métodos de construcción que la necesitan.

## Construcción de portafolio y apalancamiento (grilla fija)

Combinaciones fijas de (método, parámetro) — no un producto cruzado libre,
para que cada combinación tenga sentido económico:

| Método | Parámetro | Valores |
|---|---|---|
| `equal` | — | (un solo valor, no aplica parámetro) |
| `inv_vol` | — | (un solo valor, no aplica parámetro) |
| `vol_target` | volatilidad objetivo del portafolio | {10%, 15%, 20%} |
| `kelly_frac` | fracción de Kelly estimada (media/varianza *trailing*, capada por posición) | {0.25, 0.50, 1.00} |

→ **8 combinaciones** de construcción.

**Apalancamiento:** bruto objetivo `L ∈ {1.0x, 1.5x, 2.0x}` — tope
acordado, no apalancamiento libre. **Costo de apalancamiento (fijado
aquí, nunca estimado "a favor" después de ver resultados):**
`(L − 1) × (tasa_cash + spread)`, tasa_cash = DTB3/BIL (ya en catálogo),
`spread ∈ {100 bps, 200 bps}` (grilla).

**Política de cash (5 fijas):**

| Política | Regla |
|---|---|
| `cash_0` | 0% siempre |
| `cash_5` | 5% siempre |
| `cash_10` | 10% siempre |
| `cash_20` | 20% siempre |
| `cash_dinamico` | 2% en régimen de expansión de liquidez, 10% en contracción (mismos regímenes de la señal 5) |

## Grilla completa (producto cartesiano — ninguna variante más)

| Parámetro | Valores | N |
|---|---|---|
| `L` (momentum, meses) | {3, 6, 12} | 3 |
| `W` (SMA, días) | {50, 100, 200} | 3 |
| `B` (breakout, días) | {55, 252} | 2 |
| `V` (vol, días) | {20, 60} | 2 |
| (construcción, parámetro) | 8 combinaciones de la tabla de arriba | 8 |
| política de cash | 5 de la tabla de arriba | 5 |
| apalancamiento `Lev` | {1.0x, 1.5x, 2.0x} | 3 |
| `spread` de apalancamiento | {100bps, 200bps} | 2 |
| escala por régimen `k` | {0.5, 0.75} | 2 |

**Total: 3×3×2×2×8×5×3×2×2 = 17 280 variantes.** Cada una con un
`variant_id` único (concatenación de sus parámetros, igual estilo que
`grid.py` de EXP-001). Se registra cada intento en
`runs/EXP-002-*/trials.json` para la corrección por selección múltiple.
`Z` (reversión de corto plazo) se fija en 10 días para todas las variantes
de esta grilla — no se agrega como dimensión adicional para no multiplicar
la grilla innecesariamente; `Z=20` queda como análisis exploratorio
post-hoc declarado, no pre-registrado.

## División de datos: discovery / validation / locked test (estricta)

Elegida explícitamente en vez de depender solo de Deflated Sharpe sobre
una grilla pequeña (como EXP-001): con 17 280 variantes, la disciplina
principal contra el sobreajuste es esta separación, no solo la corrección
estadística.

* **Discovery set:** desde la fecha de inicio del backtest (ver Universo)
  hasta **2015-12-31**. Libre para explorar, iterar, incluso sobreajustar
  a propósito para aprender — nada de lo que se vea aquí se reporta como
  resultado final.
* **Validation set:** **2016-01-01 a 2019-12-31**. Se usa **una sola vez**
  para elegir la configuración ganadora (ver criterio de selección abajo).
  Una vez elegida, este set queda "gastado": no se vuelve a mirar para
  ajustar nada.
* **Locked test set:** **2020-01-01 en adelante** (incluye el crash
  COVID-19 y el mercado bajista de 2022 — episodios reales de estrés para
  medir ruina). Se corre **una sola vez**, con la única configuración ya
  elegida, sin excepciones, sin "solo para ver si el pipeline corre".
  El resultado se reporta sea cual sea.

**Criterio de selección (fijado ahora, aplicado solo al validation set):**
entre las 17 280 variantes, se descartan primero las que no cumplan
`P(pérdida ≥ 50%) < 20%` (estimada por block bootstrap sobre
discovery+validation, bloque de 20 días hábiles, 10 000 réplicas). Entre
las que cumplen, se elige la de mayor tasa de crecimiento geométrico
(log-wealth) en el validation set. **Si ninguna variante cumple ese
filtro**, se relaja una sola vez a `P(pérdida ≥ 75%) < 20%` — relajación
ya fijada aquí, no inventada después. **Si tampoco hay ninguna**, el
experimento se reporta directamente `INCONCLUSIVE` ("ninguna configuración
de la grilla pasa el control mínimo de ruina") sin relajar más ni tocar el
locked test set.

## Niveles de apetito de riesgo (la frontera que pide el proyecto)

Los 5 niveles son la **misma** configuración ganadora, escalada únicamente
por (política de cash, apalancamiento) a 5 puntos fijos de la grilla —
fijados aquí, no elegidos después de ver el locked test set:

| Nivel | Cash | Apalancamiento |
|---|---|---|
| Conservative | `cash_20` | 1.0x |
| Growth25 | `cash_10` | 1.0x |
| Growth50 | `cash_5` | 1.5x |
| Growth75 | `cash_0` | 1.5x |
| Max | `cash_0` | 2.0x |

**Growth50 es el punto de referencia para la etiqueta de éxito/fracaso**
(fijado aquí para no elegir *a posteriori* qué nivel "se ve mejor").

## Validación

* **Block bootstrap** (bloque 20 días hábiles, 10 000 réplicas) sobre
  discovery+validation para el filtro de ruina de la selección, y sobre
  cada nivel de apetito de riesgo para los intervalos de confianza del
  CAGR del locked test set.
* **Placebo de desplazamiento circular** de los retornos del locked test
  set, para descartar que el resultado sea artefacto de la estructura
  temporal (misma lógica que EXP-001).
* **Deflated Sharpe Ratio** reportado para las 17 280 variantes
  evaluadas en discovery+validation (de `trials.json`) — chequeo adicional
  de honestidad, no la defensa principal (que es la separación de datos).
* **Monte Carlo de mercados sintéticos:** 10 000 trayectorias por
  block bootstrap, por cada uno de los 5 niveles de apetito de riesgo, para
  calcular: `P(pérdida ≥ 50/75/90/99%)`, `P(no recuperar capital en 1/3/5/10
  años)`, CVaR 95%/99%, asimetría, curtosis, tiempo bajo el agua.
* **Benchmark obligatorio:** 60/40 global pasivo — 60% equal-weight
  {SPY, EFA, EEM}, 40% equal-weight {TLT, IEF, LQD} (con los activos ya
  disponibles en catálogo; no se introduce un benchmark fuera de él).
* **Costos:** 0.05% comisión + 0.05% slippage por lado (igual que
  METHODOLOGY.md) + costo de apalancamiento ya definido arriba.

## Etiqueta (código, nunca un LLM, calculado solo contra el locked test set)

* **`VALIDATED`**: en Growth50, el intervalo de confianza bootstrap del
  CAGR del locked test set es estrictamente positivo **y** supera el CAGR
  del benchmark 60/40 en al menos el 80% de las réplicas bootstrap.
* **`REJECTED`**: el CAGR de Growth50 no supera al benchmark en más del
  50% de las réplicas, **o** la probabilidad de ruina observada
  (pérdida ≥ 75%) en el locked test set excede el 20% fijado como tope de
  diseño en la sección de selección.
* **`INCONCLUSIVE`**: cualquier otro caso, incluidos: ninguna variante pasó
  el filtro de ruina (ver criterio de selección), o el locked test set
  resulta tener menos de 3 años de datos utilizables (muy corto para un
  intervalo de confianza informativo).

Los otros 4 niveles (Conservative, Growth25, Growth75, Max) se reportan
siempre con sus propias métricas de la sección de validación, pero
**ninguno de ellos mueve la etiqueta** — esa es la función exclusiva de
Growth50 contra el locked test set, fijada aquí antes de ver un solo
resultado.

## Registro de cambios

* **2026-11-12 (borrador v1):** primera versión completa, pendiente de (a)
  manifiesto congelado con el universo completo y (b) aprobación para
  bloquear. Decisiones de alcance previas (universo solo ETF/índice,
  apalancamiento con tope + costo explícito, grilla grande con
  discovery/validation/locked-test) ya registradas en `LOG.md` del
  2026-11-12.
* **2026-11-12 (LOCKED v1):** manifiesto congelado (hash citado arriba,
  207 series, 0 fallidas), fecha de inicio del backtest confirmada
  (2006-02-06, sin necesidad de enmienda), y aprobación explícita del
  responsable del proyecto. Bloqueado con este commit — nada de lo de
  arriba se vuelve a tocar salvo como enmienda documentada con fecha,
  nunca después de ver resultados.
* **2026-11-12 (aclaración de implementación v1.1):** antes de empezar a
  escribir código, se detectó que la señal 4 ("overlay, solo en régimen
  de rango") no tenía una definición operable de "rango" — la familia 5
  solo define 4 regímenes por liquidez×crecimiento, ninguno llamado
  "rango". Esto es una aclaración de cómo *implementar* una regla ya
  fijada, no un cambio de criterio (no toca universo, grilla, splits, ni
  criterios de éxito/fracaso). Definición fijada:
  * **Régimen de tendencia** (familia 5 = 1 o 4: liquidez y crecimiento
    *concuerdan* — ambos expansivos o ambos contractivos): la macro
    empuja en una sola dirección clara. El overlay de reversión (familia
    4) permanece **apagado**.
  * **Régimen de rango** (familia 5 = 2 o 3: liquidez y crecimiento
    *discrepan*): señal macro mixta/de transición, sin dirección clara.
    El overlay de reversión (familia 4) se **activa**.
  * Si el régimen macro es `NaN` (dato insuficiente para calcular
    liquidez o crecimiento todavía), el overlay permanece apagado (no se
    asume rango por defecto).
* **2026-11-12 (aclaración de implementación v1.2):** antes de escribir el
  módulo de construcción de portafolio, se detectó que varios detalles
  operables no estaban fijados en números. Igual que v1.1: aclara cómo
  *implementar* reglas ya fijadas, no cambia universo/grilla/splits ni
  criterios de éxito/fracaso.
  * **`equal`:** entre los activos con señal compuesta (con overlay) no
    `NaN` y distinta de `0`, peso = `signo(señal) / N` (N = cantidad de
    esos activos ese día). Gross = 1.0 antes de apalancamiento.
  * **`inv_vol`:** peso ∝ `signo(señal) / volatilidad_realizada(V)` entre
    los activos con señal y volatilidad disponibles (no `NaN`, vol `> 0`),
    normalizado para que la suma de `|peso|` sea 1.0 ese día.
  * **`vol_target`:** parte de `inv_vol` y escala **todos** los pesos de
    ese día por un único factor `objetivo / vol_portafolio_aprox`, donde
    `vol_portafolio_aprox² = Σ(peso_i² · volatilidad_i²)` — **ignora
    correlaciones entre activos a propósito** (no se construye una matriz
    de covarianza completa de 65×65, por la misma razón de estabilidad
    numérica que ya se decidió al excluir "maximum diversification" de la
    grilla). Es una aproximación conservadora y simple, declarada como tal.
  * **`kelly_frac`:** por activo, `kelly_i = μ_i,trailing / σ²_i,trailing`
    (sin covarianza cruzada), usando la **misma ventana `V`** ya en la
    grilla (no se agrega un parámetro de ventana nuevo): `μ_i` = media
    móvil de retornos diarios simples en `V` días, `σ²_i` = varianza móvil
    de esos mismos retornos en `V` días (`ddof=1`). Peso = `signo(señal) ·
    fracción · |kelly_i|`, **capado a ±20% del libro por posición
    individual** (constante de diseño, no variable de la grilla — una
    cartera de 65 activos con tope de posición más laxo concentraría
    demasiado en pocos nombres bajo Kelly agresivo). A diferencia de
    `equal`/`inv_vol`/`vol_target`, el tamaño de `kelly_frac` no se
    normaliza a gross 1.0 por diseño (el tamaño lo determina el propio
    criterio), pero el **gross total del día se recorta a máximo 1.0**
    (manteniendo las proporciones relativas entre posiciones) para que
    "apalancamiento bruto objetivo `L`" signifique lo mismo en los 4
    métodos: todos parten de gross ≤ 1.0 antes de multiplicar por `L`.
  * **Cash + apalancamiento, cómo se combinan:** exposición bruta final =
    `pesos_base · L · (1 − cash_pct)` — el cash reduce la base de capital
    expuesta a riesgo; el apalancamiento multiplica lo que queda después
    del cash (no al revés).
  * **`cash_dinamico` si el régimen macro es `NaN`:** usa el valor
    conservador (10%, el mismo que "contracción"), no el 2% — mismo
    principio que v1.1: ante macro incierta, no se asume el escenario más
    favorable.
  * **Costo de apalancamiento:** `(L − 1) · (tasa_cash_anual/252 +
    spread_anual/252)`, restado del retorno diario del portafolio (no de
    los pesos). `tasa_cash_anual` viene de DTB3 (o BIL una vez disponible,
    según la regla ya usada en `prl.emergency.inputs.build_cash_index` de
    EXP-001 — mismo dato, no se reinventa).

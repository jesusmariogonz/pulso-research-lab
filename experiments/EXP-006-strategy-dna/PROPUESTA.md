# EXP-006 — Strategy DNA

**Reverse Engineering the Alpha: from copying traders to replicating strategies**

**Estado: IDEA, no ejecutada.** Guardada el 2026-11-28 a pedido
explícito del usuario — "Agrega un experimento más, solo guárdalo, no
ejecutes nada ahorita". Nada de lo descrito aquí se ha investigado,
recolectado ni backtesteado.

**Nombre/número:** el usuario lo nombró "EXP-004 — Strategy DNA" al
pedirlo, pero EXP-004 ya está asignado en este repo a Short Pressure
Reversal (en implementación activa en este momento — ver
`experiments/EXP-004-short-pressure-reversal/`) y EXP-005 a Reverse
Winners. Siguiendo el mismo criterio que el usuario fijó para Bucket
Alpha en `algo_trading_platform` (no fijar un número de antemano, usar
el siguiente disponible), se guarda aquí como **EXP-006** — el
siguiente número libre del mismo registro. Si para cuando se ejecute
ya existe un EXP-006 distinto, renumerar al siguiente libre en ese
momento, no forzar este.

**Proyecto:** forma parte de Pulso de Mercado, explícitamente
declarado por el usuario.

**Recomendación del propio usuario sobre cómo ejecutarlo (importante,
no se debe perder al momento de arrancar):** no darle el experimento
completo a la IA para que "lo resuelva" de una sola vez. Hacerlo por
etapas: (1) recolección y reconstrucción de operaciones, (2) Strategy
DNA, (3) hipótesis, (4) backtesting — en ese orden, no todo junto. El
motivo explícito: reducir el riesgo de que el modelo invente una
explicación retrospectiva para justificar las ganancias observadas.

---

## Pregunta central de investigación

¿Podemos identificar, reconstruir y cuantificar las reglas que generan
el desempeño de traders exitosos (de eToro, en la propuesta original),
sin copiar directamente sus operaciones? Es decir: ¿podemos inferir,
formalizar y eventualmente replicar sus metodologías usando solo
información observable y datos públicos — sin asumir que una operación
revela automáticamente la razón por la que fue realizada?

La investigación debe distinguir, en cada hallazgo: correlación,
coincidencia temporal, evidencia de una regla, hipótesis plausible, y
regla formalmente comprobada.

## Hipótesis

**H0 (nula):** el desempeño observado de los traders seleccionados no
puede explicarse de forma consistente mediante una metodología
identificable y reproducible — puede deberse a exposición accidental a
factores, beta, concentración sectorial, régimen de mercado, suerte,
sesgo de supervivencia, leverage implícito, timing, selección
retrospectiva u otras variables no observables.

**H1 (alternativa):** el comportamiento de cada trader puede explicarse
parcialmente mediante un conjunto relativamente estable de reglas,
factores y mecanismos de gestión inferibles de sus operaciones y del
contexto de mercado.

La investigación debe **intentar refutar H1**, no demostrarla a toda
costa. Regla fundamental explícita: si los datos contradicen la
hipótesis, se cambia la hipótesis, nunca los datos. Cualquiera de estas
conclusiones es un resultado válido del experimento: estrategia
replicable, parcialmente replicable, no replicable, alpha explicado
por factores conocidos, alpha potencial, resultado probablemente
circunstancial, o evidencia insuficiente. El objetivo **no** es producir
una estrategia ganadora — es producir evidencia reproducible.

## Sujetos iniciales (4 traders de eToro, con hipótesis de partida)

1. **KeshavLohiya** — hipótesis: Value + Fundamentals + Concentration +
   Long Term. Preguntas guía: ¿usa valuation? ¿compra tras drawdowns
   con recuperación de momentum? ¿hay exposición sistemática a
   energía/tecnología? ¿el alpha desaparece al controlar por factores?
2. **mick_repo** — hipótesis: Value + Asymmetry + Defensive Risk
   Management. Hipótesis específica a falsificar: el desempeño viene
   más de value + control del downside que de simple stock picking.
3. **thomaspj** — hipótesis: Technical Trend + Macro + Valuation.
   Atención especial a si un deterioro reciente es falla de estrategia
   o régimen de mercado desfavorable (no asumir automáticamente lo
   primero).
4. **Momentum-LS** — hipótesis: Systematic Cross-Sectional Momentum +
   Long/Short. Hipótesis a probar: el desempeño viene principalmente de
   exposición sistemática al factor momentum cross-sectional, y de si
   es reproducible.

## Modelo "Strategy DNA" por trader

Cada trader se descompone en: Entry → Position Sizing → Hold → Add →
Reduce → Exit → Rebalance, investigando cada componente por separado
con variables de precio/momentum/volatilidad/drawdown/fundamentals/
mercado/macro (lista extensa de indicadores en el prompt maestro
completo, sección "ENTRY ANALYSIS" — SMA/RSI/MACD, ATR, distancia a
máximos de 52 semanas, P/E, FCF yield, SPY/VIX/breadth, tasas/inflación,
etc.), clasificando cada entrada/salida por categoría (Value, Momentum,
Mean Reversion, Breakout, Trend Following, Fundamental Catalyst,
Earnings, Macro, Sector Rotation, Event Driven, Recovery, Contrarian,
Unknown) con una probabilidad asignada a cada categoría — nunca
causalidad sin evidencia.

Distinción fundamental a investigar en las salidas: ¿son **price
based** o **thesis based**? Y en el sizing: ¿depende de conviction,
volatilidad, liquidez, correlación? ¿las posiciones ganadoras reciben
más capital después (averaging up / conviction sizing)?

## Disciplina metodológica exigida (no negociable)

- **Sesgo de supervivencia**: ¿solo se estudian traders exitosos?
  ¿cuántos similares fracasaron? ¿el track record fue filtrado
  retrospectivamente?
- **Look-ahead bias**: prohibido usar información no disponible en el
  momento de la decisión (ej. resultados financieros publicados
  después de la entrada). Toda variable necesita timestamp y fecha de
  disponibilidad.
- **Data snooping**: si se prueban múltiples hipótesis, registrar
  todas (hipótesis original, número de pruebas, hipótesis
  descartadas, hipótesis seleccionada), con corrección cuando aplique.
- **Factor decomposition**: ¿el trader genera alpha después de
  controlar por beta de mercado, size, value, momentum, quality, low
  vol, profitability, growth, sector, país, tasas, commodities? Si no
  se puede demostrar alpha, decirlo explícitamente.
- **Regime analysis**: separar resultados por bull/bear, alta/baja
  volatilidad, tasas subiendo/bajando, inflacionario/deflacionario,
  risk-on/risk-off. Más importante que el CAGR absoluto: ¿cuándo
  funciona y cuándo deja de funcionar?
- **Drawdown behavior**: ¿el trader reduce, aumenta cash, mantiene, o
  hace averaging down durante un drawdown?
- **Benchmarking** contra S&P 500, Nasdaq 100, MSCI World, factores
  Value/Momentum/Quality — nunca solo CAGR; también Sharpe, Sortino,
  Calmar, win rate, profit factor, alpha, beta, correlación, turnover.
- **Correlation analysis** entre traders y entre estrategias
  reconstruidas (no solo entre traders) — dos nombres distintos pueden
  estar expuestos al mismo factor.
- **Reconstrucción**: convertir patrones consistentes en reglas
  candidatas explícitas (ej. `P/E < mediana_sector AND FCF_yield >
  mediana_sector AND drawdown > 15% AND precio > SMA50 AND momentum_20d
  > 0 → BUY`), tratadas como *candidate rule* hasta validarse.
- **Backtest con IS / OOS / walk-forward** — nunca aceptar una
  estrategia solo porque funciona en el mismo período donde se
  descubrió.
- **Ablation test**: quitar componentes uno por uno (ej. Value, Value+
  Momentum, Value+Drawdown...) para ver cuál realmente aporta.
- **Robustness test**: variar parámetros deliberadamente (SMA 50/100/
  150/200/250, momentum 1M/3M/6M/12M) — si pequeños cambios destruyen
  el resultado, señal de overfitting.
- **Shadow copy trading**: antes de cualquier dinero real, 60-90 días
  registrando diariamente holdings/entradas/salidas/pesos/cash/
  drawdown/régimen de un "shadow portfolio" que siga solo las reglas
  inferidas (no copia automática), comparado contra el trader real.
- **Copy vs. Strategy**: comparar trader real vs. Strategy DNA
  reconstruida vs. implementación independiente de Pulso.
- **Criterios de "replicable"**: reglas explícitas, variables
  públicas, decisiones reproducibles, funciona OOS, robusta a cambios
  de parámetros, sobrevive costos de transacción, no depende de
  información futura ni de un solo activo/sector, funciona en
  múltiples períodos, el desempeño no desaparece al ajustar por
  factores conocidos.
- **Criterios de rechazo**: solo funciona en un período, depende de un
  parámetro específico o de información no observable, desaparece OOS,
  depende de un solo activo/sector, el alpha desaparece tras ajuste por
  factores, no sobrevive costos, evidencia fuerte de overfitting. Es
  preferible concluir "no encontramos evidencia suficiente" que
  inventar una explicación.
- **Regla fundamental**: nunca confundir *performance* con *skill* — un
  rendimiento extraordinario puede venir de beta, leverage,
  concentración, factor exposure, sector exposure, timing afortunado,
  régimen, o sesgo de supervivencia.

## Portfolio simulation (una vez reconstruidas las 4 estrategias)

Comparar, contra S&P 500, cada trader individual y Pulso long-only/
long-short:

- Portfolio A: 25% cada estrategia
- Portfolio B: ponderado por riesgo
- Portfolio C: ponderado por volatilidad inversa
- Portfolio D: ponderado por riesgo ajustado por correlación

## Estructura del documento final esperado

1. Abstract · 2. Research Question · 3. Hypotheses · 4. Data ·
5. Methodology · 6. Trader Profiles · 7. Strategy DNA ·
8. Factor Analysis · 9. Regime Analysis · 10. Risk Analysis ·
11. Backtests · 12. Robustness Tests · 13. Ablation Tests ·
14. Shadow Copy Trading · 15. Strategy Correlation ·
16. Portfolio Simulation · 17. Limitations · 18. Conclusions ·
19. Reproducibility · 20. Next Experiment

Ficha por trader (Strategy DNA): Philosophy, Market Universe, Entry,
Position Sizing, Holding, Add, Reduce, Exit, Risk Management, Market
Regime, Factors, Typical Holding Period, Drawdown Behavior, Long/
Short, Evidence Level — cada conclusión etiquetada 🟢 Strong Evidence /
🟡 Moderate Evidence / 🟠 Weak Evidence / 🔴 Speculation.

## Las 10 preguntas finales que el experimento debe contestar

1. ¿Qué hace diferente cada estrategia?
2. ¿Qué parte de su desempeño se explica por factores conocidos?
3. ¿Dónde aparece alpha potencial?
4. ¿En qué régimen funciona?
5. ¿En qué régimen falla?
6. ¿Qué reglas podemos reconstruir?
7. ¿Son estadísticamente robustas?
8. ¿Podemos convertirlas en código?
9. ¿Pulso puede reproducirlas?
10. ¿Pulso puede mejorarlas?

## Notas para cuando se decida empezar

- Requiere decidir primero la fuente real de datos de los 4 traders
  (eToro no necesariamente expone historial de operaciones público y
  granular sin su API de "Popular Investor" — esto hay que
  confirmarlo antes de prometer nada sobre disponibilidad de datos;
  puede terminar siendo el primer bloqueante real del experimento).
- Seguir la recomendación del usuario: NO entregarle este documento
  completo a un modelo para que "lo resuelva" de una sola corrida.
  Dividir en etapas (recolección/reconstrucción → Strategy DNA →
  hipótesis → backtesting), cada una revisada antes de pasar a la
  siguiente — mismo espíritu de rigor que ya se sigue en este repo
  (contrato escrito antes de implementar, revisión humana del código
  generado aunque los tests pasen, nunca confiar en un resultado de
  backtest sin walk-forward/bootstrap/placebo).
- Autocontención: si se construye código para esto, debe vivir en su
  propio paquete (`prl.strategy_dna` o similar), sin importar de otros
  experimentos, siguiendo la convención ya establecida en el proyecto.

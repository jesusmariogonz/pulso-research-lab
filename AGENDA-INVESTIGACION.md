# Agenda de investigación futura

**Estado: temas guardados, ninguno iniciado.** A diferencia de
`experiments/EXP-006-strategy-dna/PROPUESTA.md` (que ya tiene hipótesis,
metodología y protocolo concretos), esto es un nivel anterior: áreas de
investigación que el usuario quiere explorar más adelante, sin
hipótesis ni diseño todavía. Guardado el 2026-11-28 a pedido explícito
— "Documenta estos también como pendientes por comenzar luego". Nada
de lo descrito aquí se ha investigado, implementado ni corrido.

Cuando se decida arrancar alguno de estos temas, el primer paso es
convertirlo en un pre-registro formal (`experiments/EXP-NNN-<slug>/
PREREGISTRATION.md`, con el siguiente número EXP-NNN libre del
registro — mismo criterio ya fijado para Bucket Alpha y Strategy DNA:
no fijar el número de antemano). Un solo tema de esta lista puede dar
lugar a más de un experimento (ej. "Market Regimes" podría separarse en
un EXP de detección de régimen y otro de si ese régimen es explotable
después de costos).

## Volatility Research

Cómo se comporta y se puede anticipar la volatilidad: memoria de la
volatilidad realizada, agrupamiento de volatilidad y el premio por
riesgo de varianza.

- HAR-RV
- GARCH / EGARCH
- Realized Volatility
- Volatility Clustering

## Return Predictability

Si el retorno pasado de un activo contiene información útil sobre su
retorno futuro, y en qué horizontes y condiciones.

- Time-Series Momentum
- Cross-Sectional Momentum
- Mean Reversion
- Overnight vs. Intraday

## Market Regimes

Si los mercados transitan entre estados estadísticamente distintos
(ej. alta/baja volatilidad, tendencia/lateral) y si ese estado se puede
detectar a tiempo, no solo describir después.

- Hidden Markov Models
- Gaussian Mixture Models
- Markov Switching
- Change Point Detection

## Market Anomalies

Patrones documentados en la literatura (efectos de calendario, anomalía
overnight, baja volatilidad) y si sobreviven al aplicarse al universo
de activos de este proyecto, con costos reales.

- Calendar Effects
- Overnight Anomaly
- Low Volatility Anomaly
- Correlation Anomalies

## Factor Research

Qué variables explican de forma sistemática la diferencia de retornos
entre activos, más allá de una sola estrategia — factores de riesgo
observables y latentes.

- Risk Factors
- Latent Factors
- IPCA
- Factor Timing

## Financial Machine Learning

Modelos de aprendizaje automático aplicados a series financieras, con
el mismo estándar de validación fuera de muestra que cualquier otro
candidato — nunca una caja negra sin auditoría.

- XGBoost
- Random Forest
- Bayesian Models
- Meta-labeling

## Fondos de seguimiento de tendencia

Cómo se comportan las estrategias sistemáticas de seguimiento de
tendencia (CTA / managed futures) frente a acciones y bonos
tradicionales — si aportan diversificación real en crisis ("crisis
alpha") y si sus reglas, en gran parte públicas, se pueden replicar con
instrumentos líquidos.

- CTA / Managed Futures
- Time-Series Momentum Multi-Activo
- Crisis Alpha
- Replicación de Reglas Públicas

## Patrones reconocibles para subir y bajar

Si patrones de precio visualmente reconocibles (banderas, triángulos,
cabeza-hombros, rupturas de rango) tienen poder predictivo real sobre
la dirección futura del precio, más allá de la narrativa que se les
atribuye después de los hechos.

- Chart Patterns
- Candlestick Patterns
- Breakout Detection
- Template Matching

## Notas para cuando se decida empezar cualquiera de estos

- Mismo estándar que ya rige todo el repo (`METHODOLOGY.md`): hipótesis
  pre-registrada antes de ver datos reales, separación discovery/
  validación/locked test, out-of-sample real, DSR/PBO cuando se prueban
  múltiples variantes, un resultado negativo se documenta igual que uno
  positivo.
- Varios de estos temas (Market Regimes, Return Predictability,
  Market Anomalies) ya se tocan tangencialmente en experimentos
  existentes (EXP-004 usa reversión bajo presión short, EXP-005 usa
  momentum/reversión de ganadoras) — antes de abrir un EXP nuevo, revisar
  si no es una extensión natural de uno ya en curso en vez de un
  experimento aislado.
- "Financial Machine Learning" y "Patrones reconocibles" son los dos
  con mayor riesgo de overfitting/data snooping de toda la lista — si se
  arrancan, el contrato de implementación debe fijar de antemano el
  número de variantes/hiperparámetros probados, para poder corregir el
  DSR por el total real de intentos, no solo por los que sobrevivieron.

# Metodología

Este laboratorio sigue el mismo estándar que el sistema de
[Trading Algorítmico](https://jgonzalez.app/pulso-mercado/trading/investigacion)
y el [Research Lab](https://jgonzalez.app/pulso-mercado/research) de
Pulso de Mercado. Aquí se vuelve operativo y verificable.

## 1. Pre-registro antes de mirar resultados

Cada experimento nace como `experiments/EXP-NNN-nombre/PREREGISTRATION.md`
y se **bloquea con un commit** antes de correr cualquier cosa sobre los
datos. Fija de antemano: la hipótesis (y la hipótesis nula), las series,
los períodos de entrenamiento/prueba, la grilla *completa* de
parámetros, las métricas de éxito/fracaso y los costos. Lo que se decide
después de ver resultados es **exploratorio** y se etiqueta como tal.

## 2. Datos

* El catálogo (`data/catalog.yaml`) lista cada serie con sus
  **limitaciones conocidas**. Una serie sin limitaciones documentadas no
  entra.
* Los datos crudos son inmutables y se congelan con un manifiesto
  (`data/manifest.json`: SHA-256, fechas, versiones). Un experimento cita
  el hash del manifiesto que usó.
* Nada se imputa en silencio: los huecos y anomalías se reportan en
  `data/quality_report.md`.
* **Sin look-ahead:** toda variable en el día *t* usa solo datos hasta
  *t*; la señal se ejecuta al cierre/apertura de *t+1*.
* **Sin datos revisados:** no se usan series que se corrigen hacia atrás
  (p. ej. NFCI, STLFSI) ni indicadores publicados con retraso (p. ej.
  recesiones NBER) como entrada de un modelo.
* **Sesgo de supervivencia:** los universos de acciones son tickers
  vivos hoy. Se declara y no se usan para estimar retornos absolutos.

## 3. Validación

* **Fuera de muestra siempre.** Walk-forward con ventanas definidas en
  el pre-registro; los parámetros se eligen solo con datos de
  entrenamiento.
* **Costos reales:** 0.05 % de comisión + 0.05 % de slippage por lado,
  igual que el sistema de trading.
* **Benchmarks simples obligatorios:** buy-and-hold y la regla más
  simple que compita (p. ej. SMA200). Un modelo complejo que no supera a
  una regla simple **no se justifica**.
* **Pocos eventos independientes:** los episodios de estrés son pocos
  (≈ 6 desde 2000). Se reporta el número de eventos, y los intervalos de
  confianza usan *block bootstrap* (los días de un mismo evento no son
  independientes). Con pocos eventos, "INCONCLUSIVE" es un resultado
  legítimo y esperado.
* **Pruebas múltiples:** se lleva un registro de cada variante probada
  (`runs/*/trials.json`); los estadísticos se ajustan por el número de
  intentos (p. ej. Deflated Sharpe).

## 4. Etiquetas de resultado

`EXPERIMENTAL` · `VALIDATED` · `REJECTED` · `INCONCLUSIVE` — siempre junto
a la fecha, el período de datos y el hash del manifiesto. Los resultados
negativos se publican igual que los positivos.

Un hallazgo `VALIDATED` **no** se convierte automáticamente en una
estrategia de producción: requiere además los controles de riesgo y la
validación walk-forward del sistema de trading.

## 5. Uso de modelos de lenguaje (DeepSeek)

Los LLM **no calculan** ni "recuerdan" estadísticas. Su papel:

| Hace el LLM | Lo hace el código |
|---|---|
| Escribir el código del experimento dentro de la spec | Ejecutarlo sobre los datos congelados |
| Redactar el borrador interpretando `results.json` | Producir toda cifra |

Reglas duras (las aplica `prl.verify`, sin LLM):

1. **Toda cifra del borrador debe existir en `results.json`**; si no, el
   borrador se rechaza.
2. El código generado corre en un proceso aislado, **sin secretos** y sin
   red; la llave del LLM nunca llega a ese proceso.
3. Se guardan el prompt, el modelo, los parámetros y la respuesta
   completa de cada llamada (`runs/*/llm_log.jsonl`) para auditar.
4. Un LLM **no puede** cambiar la spec ni el pre-registro; si propone un
   cambio, queda como sugerencia para revisión humana.

# EXP-001 — Modelo de emergencia multifactor (Emergency Model v0)

**Estado:** `LOCKED`

Aprobado por el responsable del proyecto el 2026-11-11 y bloqueado con el
commit que añade esta línea. Desde este punto, cualquier cambio a las
reglas se registra en el *Registro de cambios* como nueva versión;
todo lo decidido después de ver resultados es **exploratorio**.

**Manifiesto de datos citado (SHA-256 de `data/manifest.json`):**
`4cdc4e187fb92ff451f9cf71e48c57e7d321f07371a0e9edfffa35844db3b307`
(datos descargados el 2026-11-11, última fecha de mercado 2026-11-10).

## Pregunta

¿Puede un índice multifactor de estrés de mercado reducir el máximo
drawdown y mejorar el rendimiento ajustado por riesgo de una cartera
accionaria **sin sacrificar materialmente el CAGR de largo plazo**,
frente a reglas simples?

No se pretende "predecir crashes": se evalúa una **política de
exposición** gobernada por un índice de estrés.

## Hipótesis

* **H1 (alternativa):** el índice de estrés + política de exposición mejora
  Calmar y reduce MaxDD frente a buy-and-hold del S&P 500 (SPY), con una
  reducción de CAGR menor a la que se fije abajo.
* **H0 (nula):** no hay mejora distinguible de la que produce una regla
  simple (SMA200) o el azar.
* **H2:** el modelo multifactor supera a la regla simple SMA200. Si no,
  la complejidad no se justifica (se reporta como `REJECTED` aunque H1 se
  cumpla frente a buy-and-hold).

## Datos

Solo series del catálogo `data/catalog.yaml`, congeladas con
`data/manifest.json` (se cita su hash al bloquear). Núcleo: SPY/GSPC,
VIX, VIX3M, HYG, LQD, BAA10Y, RSP, 9 sectores SPDR, TLT/IEF/SHY/BIL, DTB3.
Excluidas por diseño: NFCI, STLFSI, OAS ICE BofA, % de acciones S&P500
sobre SMA200 (no point-in-time). Amplitud = proxies (RSP/SPY, sectores
sobre SMA200).

Cada dimensión usa solo el historial disponible; si una serie empieza
después (HYG: 2007; VIX3M: 2006), esa dimensión se **desactiva** antes de
esa fecha (con su peso redistribuido según regla fija), no se rellena.

## Diseño

1. **Dimensiones** (cada una = z-score *expansivo* del propio historial
   hasta *t*, sin look-ahead): tendencia, volatilidad (nivel y cambio),
   correlación entre sectores, crédito (BAA10Y; HYG/LQD desde 2007),
   amplitud (proxies), velocidad del drawdown.
2. **Índice:** suma ponderada con pesos **fijados aquí** (por defecto
   iguales; ver *Grilla*). Niveles por umbral con **histéresis** y
   persistencia mínima de *k* días (sin saltos 100 % → 0 % por una sola
   señal).
3. **Política:** exposición accionaria objetivo por nivel (100 / 75 / 50 /
   25 / 0 %). La parte fuera de acciones va a un **destino**; se comparan
   los tres: TLT, SHY/BIL (efectivo), 50/50.
4. **Re-entrada:** regla simétrica pre-especificada (el nivel debe bajar y
   mantenerse *m* días). Se evalúa **separada** de la salida.
5. Ejecución en *t+1*, costos 0.05 % + 0.05 % por lado.

## Grilla completa (todas las variantes que se probarán — ninguna más)

| Parámetro | Valores |
|---|---|
| Pesos | iguales; tendencia/volatilidad/crédito ×2 |
| Umbrales de nivel (z) | {0.5, 1.0, 1.5} |
| Persistencia *k* (días) | {2, 3, 5} |
| Re-entrada *m* (días) | {5, 10, 20} |
| Destino | TLT · SHY/BIL · 50/50 |

Total de variantes: 2·3·3·3·3 = **162**. Se reporta el número de
intentos y se ajusta (Deflated Sharpe).

## Validación

* **Walk-forward expansivo:** entrenar (elegir variante) hasta el cierre
  de cada año; probar el año siguiente. Primera prueba: 2003.
* **Episodios de referencia (etiquetados a priori, por drawdown del SPY
  ≥ 20 % desde su máximo, SPY adj_close, calculados con la regla antes de
  cualquier modelo):**

  | Episodio | Máximo previo | Mínimo | Caída máx. |
  |---|---|---|---|
  | Dot-com | 2000-03-24 | 2002-10-09 | −47.5 % |
  | Crisis financiera | 2007-10-09 | 2009-03-09 | −55.2 % |
  | COVID | 2020-02-19 | 2020-03-23 | −33.7 % |
  | 2022 | 2022-01-03 | 2022-10-12 | −24.5 % |

  Son **4 episodios independientes**: la potencia estadística es baja y se
  declara así en cualquier resultado.
* **Métricas:** CAGR, MaxDD, Calmar, Sharpe, Sortino, tiempo en cada nivel,
  rotación y costos pagados; por episodio: días de anticipación, falsos
  positivos (CRISIS sin caída ≥ 10 % en los 60 días siguientes), crashes
  no detectados, **costo de oportunidad** (rally perdido).
* **Benchmarks:** buy-and-hold SPY; SPY con regla SMA200; 60/40.
* **Estadística:** block bootstrap (bloques de 20 días) para intervalos
  de confianza; con ≈ 4-6 eventos se declara explícitamente la baja
  potencia.

## Criterios de éxito (fijados antes de correr)

* **VALIDATED:** en walk-forward fuera de muestra, MaxDD ≤ 70 % del de
  buy-and-hold **y** CAGR ≥ 90 % del de buy-and-hold **y** Calmar mayor
  que SMA200, con el intervalo bootstrap del Calmar relativo excluyendo 0.
* **REJECTED:** no supera a SMA200 o no reduce MaxDD fuera de muestra.
* **INCONCLUSIVE:** cualquier otro caso (p. ej. mejora puntual pero
  intervalos que incluyen 0).

> Los umbrales numéricos de éxito fueron aprobados tal cual el 2026-11-11.

## Fuera de alcance de v0

No toca el motor de paper trading ni IBKR. Solo si resulta `VALIDATED` se
propone una fase aparte (poder de veto sobre las compras) con su propio
pre-registro.

## Registro de cambios

| Fecha | Cambio | Commit |
|---|---|---|
| 2026-11-10 | borrador inicial | bfa9810 |
| 2026-11-11 | aprobado y bloqueado (v1); se añaden fechas de episodios y hash del manifiesto | (este commit) |

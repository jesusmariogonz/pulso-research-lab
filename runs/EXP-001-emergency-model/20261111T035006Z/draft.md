# EXP-001 — Modelo de emergencia multifactor (Emergency Model v0)

## Resumen

Se documenta el resultado del experimento EXP-001 (módulo `prl.emergency.exp001`), correspondiente al modelo de emergencia multifactor v0, con `first_test_year` = 2004. La evaluación fuera de muestra abarca `n_oos_days` = 5751 días y `n_variants` = 162 variantes.

**Etiqueta oficial del resultado: `INCONCLUSIVE`.** Esta etiqueta procede del campo `label` de `results.json`, calculado por código con criterios pre-registrados, y se reproduce aquí sin suavizarla ni reinterpretarla.

Las métricas principales (tal como figuran en `results.json`, en tanto por uno) son:

- **Modelo:** CAGR 0.10894409720447573; max drawdown -0.2642458396269748; Calmar 0.41228311241633064; Sharpe 0.8403523294953362; Sortino 1.189574421331244.
- **Buy & hold:** CAGR 0.1069709141450943; max drawdown -0.5518945546755865; Calmar 0.19382491318105816; Sharpe 0.640189557973637; Sortino 0.9037448996138079.
- **SMA200:** CAGR 0.06859390621853301; max drawdown -0.22314634198374794; Calmar 0.30739426695835687; Sharpe 0.6317374597023013; Sortino 0.8591844601665759.
- **60/40:** CAGR 0.08523554747150786; max drawdown -0.2992278831966436; Calmar 0.28485162064757713; Sharpe 0.8018516911773707; Sortino 1.151870683112597.

La comparación pre-registrada de Calmar frente a SMA200 arroja `value` = 0.10488884545797378 con intervalo de confianza bootstrap [`ci_lo` = -0.12359077235783854, `ci_hi` = 0.5042955914659651], `n_boot` = 1000 y `block` = 20. El intervalo incluye el cero, por lo que la evidencia no permite separar la diferencia observada del ruido de muestreo. Coherentemente, el experimento no se declara exitoso.

## Datos y período

- **Inicio fuera de muestra (`oos_start`):** 2004-01-02.
- **Fin fuera de muestra (`oos_end`):** 2026-11-10.
- **Días fuera de muestra (`n_oos_days`):** 5751.
- **Primer año de prueba (`first_test_year`):** 2004.

Series utilizadas: SPY, VIX, BAA10Y, RSP, XLK, XLE, XLF, XLV, XLP, XLU, XLY, XLI, XLB, TLT, BIL, DTB3.

Episodios excluidos por no ser fuera de muestra (`episodes_excluded_not_oos`): dot-com.

## Resultados

### Comparación de métricas (fuera de muestra)

| Estrategia | CAGR | Max drawdown | Calmar | Sharpe | Sortino |
|---|---|---|---|---|---|
| Modelo | 0.10894409720447573 | -0.2642458396269748 | 0.41228311241633064 | 0.8403523294953362 | 1.189574421331244 |
| Buy & hold | 0.1069709141450943 | -0.5518945546755865 | 0.19382491318105816 | 0.640189557973637 | 0.9037448996138079 |
| SMA200 | 0.06859390621853301 | -0.22314634198374794 | 0.30739426695835687 | 0.6317374597023013 | 0.8591844601665759 |
| 60/40 | 0.08523554747150786 | -0.2992278831966436 | 0.28485162064757713 | 0.8018516911773707 | 1.151870683112597 |

Todas las columnas corresponden a 5751 días (`n_days`).

### Diferencia de Calmar frente a SMA200

- `value`: 0.10488884545797378
- `ci_lo`: -0.12359077235783854
- `ci_hi`: 0.5042955914659651
- `n_boot`: 1000; `block`: 20

El intervalo bootstrap contiene el cero en su rango reportado. No se realiza ninguna afirmación de superioridad estadística.

### Episodios

| Episodio | Peak | Trough | Cross20 | Fecha de detección | Lead (días) | Detectado |
|---|---|---|---|---|---|---|
| crisis financiera | 2007-10-09 | 2009-03-09 | 2008-07-14 | 2007-07-30 | 350 | true |
| COVID | 2020-02-19 | 2020-03-23 | 2020-03-12 | 2020-02-26 | 15 | true |
| 2022 | 2022-01-03 | 2022-10-12 | 2022-06-13 | null | null | false |

### Alarmas

- `n_alarms`: 2
- `n_false`: 1
- `n_unevaluable`: 0
- `false_dates`: ["2020-03-12"]

La única alarma marcada como falsa lleva fecha 2020-03-12, que en el bloque de episodios figura como `cross20` del episodio COVID. El episodio de 2022 figura como no detectado (`detection_date` = null, `detected` = false).

### Régimen y actividad

Fracciones de tiempo por nivel (`level_fractions`):

- Nivel 0: 0.673621978786298
- Nivel 1: 0.1984002782124848
- Nivel 2: 0.0759867849069727
- Nivel 3: 0.024865240827682142
- Nivel 4: 0.027125717266562335

Otras métricas de actividad y diagnóstico reportadas:

- `non_episode_shortfall`: 26.847499468940406
- `deflated_sharpe`: 0.9029922582581005
- `turnover`: 27.5
- `costs_paid`: 0.05500000000000001

### Selección de variante por año

El campo `chosen_by_year` registra una variante elegida para cada año entre 2004 y 2026. La selección no es estable: el año 2004 corresponde a la variante descrita como `tvc2|0.5|3|20|MIX`, mientras que en el resto de los años la familia elegida es `equal`, con variaciones en los parámetros internos y en el refugio (`TLT`). Los años 2023 a 2026 comparten la misma configuración registrada (`equal|0.5|5|5|TLT`). Se reporta como descripción de la trayectoria de selección, sin inferencia sobre su idoneidad.

## Limitaciones

Se recogen íntegramente las notas incluidas en `results.json`:

1. Rebalanceo diario del refugio sin costo de transacción.
2. Crédito medido solo con BAA10Y; sin HYG/LQD en v0.
3. Amplitud medida solo con proxies (RSP/SPY y sectores).
4. Pocos eventos independientes para evaluar la regla.
5.
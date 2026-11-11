# EXP-001 — Modelo de emergencia multifactor (Emergency Model v0)

**Etiqueta oficial: `INCONCLUSIVE`**

## Resumen

Se documenta el resultado del experimento EXP-001 (módulo `prl.emergency.exp001`), que evalúa un modelo de emergencia multifactor sobre 162 variantes, con un período de prueba fuera de muestra comprendido entre `2004-01-02` y `2026-11-10` (`n_oos_days`: `5751`). El resultado se compara de forma descriptiva con tres referencias: comprar y mantener (`buy_hold`), una regla de media móvil de 200 días (`sma200`) y una cartera sesenta/cuarenta (`sixty_forty`).

La etiqueta asignada por el código con criterios pre-registrados es **`INCONCLUSIVE`**. Los resultados se presentan tal cual, sin suavizado: el modelo no alcanza una conclusión estable conforme a los criterios del experimento.

## Datos y período

- Serie evaluada: `SPY`, `VIX`, `BAA10Y`, `RSP`, `XLK`, `XLE`, `XLF`, `XLV`, `XLP`, `XLU`, `XLY`, `XLI`, `XLB`, `TLT`, `BIL`, `DTB3`.
- `first_test_year`: `2004`.
- Inicio fuera de muestra (`oos_start`): `2004-01-02`.
- Fin fuera de muestra (`oos_end`): `2026-11-10`.
- Días fuera de muestra (`n_oos_days`): `5751`.
- Variantes evaluadas (`n_variants`): `162`.
- Episodio excluido por no estar fuera de muestra (`episodes_excluded_not_oos`): `dot-com`.

## Resultados

### Métricas fuera de muestra

| Variante | CAGR | Max drawdown | Calmar | Sharpe | Sortino | n_days |
|---|---|---|---|---|---|---|
| `model` | 0.10894409720447573 | -0.2642458396269748 | 0.41228311241633064 | 0.8403523294953362 | 1.189574421331244 | 5751 |
| `buy_hold` | 0.1069709141450943 | -0.5518945546755865 | 0.19382491318105816 | 0.640189557973637 | 0.9037448996138079 | 5751 |
| `sma200` | 0.06859390621853301 | -0.22314634198374794 | 0.30739426695835687 | 0.6317374597023013 | 0.8591844601665759 | 5751 |
| `sixty_forty` | 0.08523554747150786 | -0.2992278831966436 | 0.28485162064757713 | 0.8018516911773707 | 1.151870683112597 | 5751 |

### Diferencia de Calmar frente a `sma200`

- Valor puntual (`value`): `0.10488884545797378`.
- Intervalo de confianza bootstrap: `ci_lo` = `-0.12359077235783854`, `ci_hi` = `0.5042955914659651`.
- `n_boot`: `1000`; longitud de bloque (`block`): `20`.

El intervalo de confianza incluye el cero, por lo que la diferencia observada no se distingue de forma concluyente de una ausencia de diferencia con los criterios del experimento.

### Episodios

| Episodio | Peak | Trough | cross20 | detection_date | lead_days | detected |
|---|---|---|---|---|---|---|
| crisis financiera | 2007-10-09 | 2009-03-09 | 2008-07-14 | 2007-07-30 | 350 | true |
| COVID | 2020-02-19 | 2020-03-23 | 2020-03-12 | 2020-02-26 | 15 | true |
| 2022 | 2022-01-03 | 2022-10-12 | 2022-06-13 | null | null | false |

### Alarmas

- `n_alarms`: `2`.
- `n_false`: `1`.
- `n_unevaluable`: `0`.
- `false_dates`: `2020-03-12`.

### Otras métricas

- `non_episode_shortfall`: `26.847499468940406`.
- `deflated_sharpe`: `0.9029922582581005`.
- `turnover`: `27.5`.
- `costs_paid`: `0.05500000000000001`.

### Configuración elegida por año (`chosen_by_year`)

| Años | Configuración |
|---|---|
| 2004 | `tvc2\|0.5\|3\|20\|MIX` |
| 2005, 2006, 2007, 2008 | `equal\|0.5\|3\|20\|TLT` |
| 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022 | `equal\|0.5\|2\|20\|TLT` |
| 2023, 2024, 2025, 2026 | `equal\|0.5\|5\|5\|TLT` |

### Fracción de días por nivel (`level_fractions`)

| Nivel | Fracción |
|---|---|
| 0 | 0.673621978786298 |
| 1 | 0.1984002782124848 |
| 2 | 0.0759867849069727 |
| 3 | 0.024865240827682142 |
| 4 | 0.027125717266562335 |

## Limitaciones

- Rebalanceo diario del refugio sin costo de transacción.
- Crédito medido solo con BAA10Y; sin HYG/LQD en v0.
- Amplitud medida solo con proxies (RSP/SPY y sectores).
- Pocos eventos independientes para evaluar la regla.
- Los episodios previos al primer año de prueba no se evalúan fuera de muestra.

Adicionalmente, la etiqueta oficial del experimento es `INCONCLUSIVE`: el intervalo bootstrap de la diferencia de Calmar frente a `sma200` abarca valores negativos y positivos, y el número de episodios evaluables es reducido. Este documento es descriptivo de un experimento de investigación y no constituye una recomendación de inversión.
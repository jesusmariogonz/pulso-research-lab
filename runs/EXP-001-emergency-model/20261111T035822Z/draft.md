# EXP-001 · Modelo de emergencia multifactor (Emergency Model v0)

**Etiqueta oficial: `INCONCLUSIVE`** (calculada por código con criterios pre-registrados).

## Resumen

Se documenta el resultado del experimento EXP-001, que evalúa un modelo de emergencia multifactor (v0) con `first_test_year = 2004` sobre un universo de 162 variantes y 5751 días fuera de muestra. El período de evaluación va de `2004-01-02` a `2026-11-10`.

Las métricas se presentan en tanto por uno y se transcriben tal como figuran en `results.json`, sin redondeo ni transformación. El resultado se etiqueta como `INCONCLUSIVE`: la diferencia de Calmar frente a la referencia SMA200 tiene un intervalo de confianza bootstrap que incluye el cero, y la evidencia episódica disponible es escasa.

## Datos y período

- Series utilizadas: SPY, VIX, BAA10Y, RSP, XLK, XLE, XLF, XLV, XLP, XLU, XLY, XLI, XLB, TLT, BIL, DTB3.
- `first_test_year`: 2004.
- `oos_start`: 2004-01-02; `oos_end`: 2026-11-10; `n_oos_days`: 5751.
- `n_variants`: 162.
- Referencias comparativas: `buy_hold`, `sma200`, `sixty_forty`.
- Bootstrap de la diferencia de Calmar: `n_boot = 1000`, `block = 20`.
- Episodios excluidos por no ser fuera de muestra (`episodes_excluded_not_oos`): `dot-com`.

## Resultados

### Métricas fuera de muestra

| Cartera | cagr | max_drawdown | calmar | sharpe | sortino | n_days |
|---|---|---|---|---|---|---|
| model | 0.10894409720447573 | -0.2642458396269748 | 0.41228311241633064 | 0.8403523294953362 | 1.189574421331244 | 5751 |
| buy_hold | 0.1069709141450943 | -0.5518945546755865 | 0.19382491318105816 | 0.640189557973637 | 0.9037448996138079 | 5751 |
| sma200 | 0.06859390621853301 | -0.22314634198374794 | 0.30739426695835687 | 0.6317374597023013 | 0.8591844601665759 | 5751 |
| sixty_forty | 0.08523554747150786 | -0.2992278831966436 | 0.28485162064757713 | 0.8018516911773707 | 1.151870683112597 | 5751 |

### Diferencia de Calmar frente a SMA200

- `value`: 0.10488884545797378
- `ci_lo`: -0.12359077235783854
- `ci_hi`: 0.5042955914659651
- `n_boot`: 1000; `block`: 20

El intervalo bootstrap abarca valores negativos y positivos: no permite descartar que la diferencia sea nula o de signo contrario.

### Deflated Sharpe

- `deflated_sharpe`: 0.9029922582581005

### Episodios

| Episodio | peak | trough | cross20 | detection_date | lead_days | detected |
|---|---|---|---|---|---|---|
| crisis financiera | 2007-10-09 | 2009-03-09 | 2008-07-14 | 2007-07-30 | 350 | true |
| COVID | 2020-02-19 | 2020-03-23 | 2020-03-12 | 2020-02-26 | 15 | true |
| 2022 | 2022-01-03 | 2022-10-12 | 2022-06-13 | null | null | false |

### Alarmas

- `n_alarms`: 2
- `n_false`: 1
- `n_unevaluable`: 0
- `false_dates`: 2020-03-12

### Otras métricas del experimento

- `non_episode_shortfall`: 26.847499468940406
- `turnover`: 27.5
- `costs_paid`: 0.05500000000000001

### Fracciones de nivel

| Nivel | Fracción |
|---|---|
| 0 | 0.673621978786298 |
| 1 | 0.1984002782124848 |
| 2 | 0.0759867849069727 |
| 3 | 0.024865240827682142 |
| 4 | 0.027125717266562335 |

### Configuración elegida por año (`chosen_by_year`)

- 2004: `tvc2|0.5|3|20|MIX`
- 2005–2008: `equal|0.5|3|20|TLT`
- 2009–2022: `equal|0.5|2|20|TLT`
- 2023–2026: `equal|0.5|5|5|TLT`

La configuración seleccionada cambia a lo largo de la muestra según el procedimiento de selección del experimento.

## Limitaciones

- Rebalanceo diario del refugio sin costo de transacción.
- Crédito medido solo con BAA10Y; sin HYG/LQD en v0.
- Amplitud medida solo con proxies (RSP/SPY y sectores).
- Pocos eventos independientes para evaluar la regla.
- Los episodios previos al primer año de prueba no se evalúan fuera de muestra.
- Etiqueta oficial del experimento: `INCONCLUSIVE`. El intervalo bootstrap de la diferencia de Calmar frente a SMA200 incluye el cero, por lo que el resultado no permite distinguir la regla de la referencia con la evidencia disponible.
- Solo uno de los tres episodios listados no fue detectado (2022), y las alarmas registradas son 2, de las cuales 1 se marca como falsa en `false_dates`. La base episódica es reducida.
- `non_episode_shortfall` se reporta como valor bruto del experimento, sin interpretación adicional.
- La configuración elegida varía entre años, lo que refleja el procedimiento de selección y no una regla fija y única.
- Los resultados son descriptivos y experimentales; no constituyen recomendación de inversión ni implican relación causal.
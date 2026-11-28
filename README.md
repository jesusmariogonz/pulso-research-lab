# Pulso Research Lab

Laboratorio de investigación cuantitativa de
[Pulso de Mercado](https://jgonzalez.app/pulso-mercado/research):
experimentos **pre-registrados, reproducibles y auditables** sobre
volatilidad, predictibilidad de retornos, regímenes y riesgo sistémico.

> Un hallazgo no cuenta como válido sin validación fuera de muestra, y un
> resultado negativo se documenta igual que uno positivo.

## Estructura

```
data/            catálogo de series, manifiesto (hashes) y reporte de calidad
src/prl/         código: descarga, validación (y, próximamente, features y backtest)
experiments/     un directorio por experimento, con su PREREGISTRATION.md
tests/           pruebas del código
METHODOLOGY.md   las reglas que rigen todo lo anterior
```

## Reproducir la base de datos

```bash
pip install -e ".[dev]"
python -m prl.data.build        # descarga, valida y congela (manifest.json)
pytest
```

Los datos crudos no se versionan en git (son grandes y de terceros): se
regeneran con el comando anterior o se descargan de los *Releases* de este
repo, y se verifican contra los SHA-256 del manifiesto.

## Experimentos

| ID | Tema | Estado |
|---|---|---|
| [EXP-001](experiments/EXP-001-emergency-model/PREREGISTRATION.md) | Modelo de emergencia multifactor | `INCONCLUSIVE` (cumple 3 de 4 criterios; pocos episodios independientes para distinguir la mejora de ruido — ver [README](experiments/EXP-001-emergency-model/README.md)) |
| [EXP-002](experiments/EXP-002-growth-max-global/PREREGISTRATION.md) | Growth-Max Global (crecimiento geométrico, universo multi-activo, frontera de apetito de riesgo) | `REJECTED` (no superó al benchmark 60/40 en el locked test 2020–2026 — ver [README](experiments/EXP-002-growth-max-global/README.md)) |
| [EXP-003](experiments/EXP-003-validacion-motor-produccion/PREREGISTRATION.md) | Validación estadística y robustez del motor de trading algorítmico (3 buckets de producción, repositorio externo `algo_trading_platform`) | **mixto, sin etiqueta única** — ninguno de los 3 buckets muestra ventaja distinguible del azar en DSR/placebo; `riesgo_alto` además `REJECTED` por sesgo de supervivencia; ninguno es frágil a parámetros/sector/ejecución — ver [RESULTADOS](experiments/EXP-003-validacion-motor-produccion/RESULTADOS.md) |
| [EXP-004](experiments/EXP-004-short-pressure-reversal/PREREGISTRATION.md) | Short Pressure Reversal (discovery de buckets de reversión bajo presión short elevada + agotamiento de precio, universo S&P 1500, grilla cerrada de 140 variantes) | `EXPERIMENTAL` — pre-registrado y bloqueado; infraestructura de datos ya construida y corrida (universo + precios + short volume/interest de FINRA) — faltan los módulos de cómputo |
| [EXP-005](experiments/EXP-005-reverse-winners/PREREGISTRATION.md) | Reverse Winners (ingeniería inversa de las mayores ganadoras de 30 días: qué características tenían antes de subir, grilla cerrada de hasta 243 variantes, debe superar un baseline de momentum de un solo factor) | `INCONCLUSIVE` — corrida real completa (1,501 símbolos, 2010-2026): el bucket descubierto supera a los 4 baselines pero el Deflated Sharpe Ratio (0.534) no alcanza el umbral de validación (0.95) tras corregir por las 81 variantes probadas. Ver [RESULTADOS.md](experiments/EXP-005-reverse-winners/RESULTADOS.md) |

| [EXP-006](experiments/EXP-006-strategy-dna/PROPUESTA.md) | Strategy DNA (reverse-engineering de las reglas de entrada/sizing/salida de traders de eToro, sin copiar sus operaciones) | **IDEA, no iniciado** — propuesta guardada |

## Agenda de investigación futura

Temas guardados para después, sin hipótesis ni diseño todavía (un
nivel anterior a la lista de experimentos de arriba) — ver
[AGENDA-INVESTIGACION.md](AGENDA-INVESTIGACION.md): Volatility
Research, Return Predictability, Market Regimes, Market Anomalies,
Factor Research, Financial Machine Learning, Fondos de seguimiento de
tendencia (CTA), y patrones de precio reconocibles (chart/candlestick
patterns).

## Aviso

Material de investigación y educativo. No es asesoría de inversión.

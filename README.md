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

## Aviso

Material de investigación y educativo. No es asesoría de inversión.

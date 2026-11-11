# Bitácora EXP-001 (cronológica, 2026-11-11)

| Paso | Decisión / hallazgo |
|---|---|
| Datos | Base de 16 series congeladas con manifiesto SHA-256; Release `data-2026-11-11`. |
| Pre-registro v1.1 | Primer año de prueba 2004 en lugar de 2003: TLT inicia en 2002-07 y se necesitan ≥252 días de entrenamiento. Documentado antes de correr datos reales. |
| Implementación | Ciclo TDD con DeepSeek. Fallos y correcciones: truncado por razonamiento (12k→32k tokens); `git add` con ruta inexistente descartaba evidencia; backtest con NaN daba resultados silenciosos erróneos (se añadieron tests y validación estricta); el módulo diario duplicaba código y divergía (se añadió test de equivalencia). |
| Verificador | Falsos positivos corregidos: "60/40" contado como cifra; años con coma final. |
| Resultado | Etiqueta INCONCLUSIVE: cumple 3 de 4 criterios; la mejora sobre SMA200 no es distinguible de cero (solo 3 episodios evaluables). |
| Apéndice exploratorio | Sensibilidad, bootstrap, placebo, derivación paso a paso del Deflated Sharpe (DSR = 0.9030, N = 162), número efectivo de intentos y análisis de entradas y salidas. Hallazgo: el valor proviene casi todo del episodio 2007–2009 (pagos convexos, baja tasa de acierto). |
| Robustez (hecho) | `robustness_run.py` → `robustness.json`. Costos 0–50 pb: modelo CAGR 11.2%→9.8%, SMA200 colapsa (Calmar 0.43→0.04). Sin 2007-10 a 2009-12: modelo CAGR 10.9%, DD −26.4%, Sharpe 0.95 vs comprar y mantener 12.0%, −33.7%, 0.86. Reality Check (162 variantes): vs comprar y mantener p=0.687; vs SMA200 p=0.0285. Potencia: exceso anual vs SMA200 +4.0 pp (t=2.19, 23 años); se requerirían ≈30 años para 80% de potencia. Exploratorio; no cambia la etiqueta. Salvedad: la selección de variante por año se mantuvo fija al variar costos; el Reality Check usa media de retornos, no Calmar. |
| Literatura (pendiente) | `REFERENCES.md` con citas verificadas por búsqueda web antes de usarlas en el reporte. |

## Reglas de trabajo
- No hacer push a `main` mientras corre un workflow.
- Ningún análisis exploratorio modifica la etiqueta oficial.
- Todo número del reporte sale de un JSON producido por código.

# Estadística descriptiva de SPY (prueba de extremo a extremo del flujo)

**Estado: `EXPERIMENTAL`** · ID: EXP-000-smoke · Serie: SPY (adj_close, frecuencia diaria)

## Resumen

Se ejecutó un cálculo descriptivo sobre la serie diaria de SPY con el único objetivo de verificar que el flujo de datos → cómputo → resultados funciona de extremo a extremo. No hay hipótesis, no hay comparación entre estrategias ni entre series: es una prueba de humo (*smoke test*). Los estadísticos reportados cubren todo el período disponible en la serie y se presentan sin interpretación económica ni inferencial.

## Datos y período

- Serie utilizada: **SPY**, precio de cierre ajustado (`adj_close`), frecuencia diaria.
- Primera fecha: **1993-01-29**.
- Última fecha: **2026-11-10**.
- Número de observaciones: **8504**.

## Resultados

| Estadístico | Valor |
|---|---|
| Primera fecha | 1993-01-29 |
| Última fecha | 2026-11-10 |
| N observaciones | 8504 |
| CAGR | 0.1071922099827245 (10.72 %) |
| Volatilidad anualizada | 0.18529161276073133 (18.53 %) |
| Máximo drawdown | -0.5518945546755859 (-55.19 %) |
| Fecha del mínimo del drawdown | 2009-03-09 |
| Peor retorno diario | -0.10942377857763963 (-10.94 %) |
| Fecha del peor retorno diario | 2020-03-16 |

Notas de lectura:

- El **CAGR** se expresa como fracción anual compuesta sobre el período completo indicado arriba.
- La **volatilidad anualizada** corresponde a la desviación estándar muestral de los retornos diarios simples, anualizada según la convención estándar del laboratorio.
- El **máximo drawdown** se reporta como fracción negativa (caída máxima desde un pico previo hasta el mínimo posterior), junto con la fecha en que se alcanzó ese mínimo.
- El **peor retorno diario** es el retorno simple diario más negativo del período y su fecha.

## Limitaciones

- Se trata de una verificación de flujo (`EXPERIMENTAL`), no de un resultado de investigación: no hay hipótesis contrastada, ni intervalo de confianza, ni test estadístico asociado.
- Los estadísticos son puramente descriptivos del período indicado; no constituyen una estimación de propiedades futuras de la serie.
- El máximo drawdown y el peor retorno diario son estadísticos de cola dependientes de la ventana muestral: un período distinto puede arrojar valores distintos.
- Los resultados dependen de la fuente y del tratamiento de la serie (`adj_close` diario, con los ajustes corporativos que aplique el proveedor); no se realizó auditoría independiente de los datos de entrada.
- No se ha verificado aquí el efecto de dividendos, costes de transacción, liquidez ni husos horarios, por quedar fuera del alcance de esta prueba.
- Este documento no contiene recomendaciones de inversión ni afirmaciones causales.
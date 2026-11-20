# EXP-004 · Short Pressure Reversal — espacio del experimento

Índice único de todo lo que existe sobre este experimento. **Estado:
`EXPERIMENTAL`** (pre-registrado y bloqueado, sin ejecutar todavía).

## Qué investiga

¿Puede identificarse un bucket de activos que, después de una caída
extrema y bajo presión short elevada, tenga una probabilidad
significativamente mayor de recuperación — distinguible del azar y
robusta fuera de muestra? Es un experimento de **discovery**: no se
asume la hipótesis, se explora una grilla cerrada de 140 configuraciones
candidatas (Short Pressure × Price Exhaustion × Reversal Confirmation)
y se deja que los datos decidan.

## Documentos (en este directorio)

| Archivo | Qué es |
|---|---|
| `PREREGISTRATION.md` | Pre-registro (v1, LOCKED 2026-11-20 antes de ver datos reales): universo (S&P 1500 actual), features, grilla de 140 variantes, split discovery/validation/locked test, 6 baselines, criterios de etiqueta. |
| `LOG.md` | Bitácora cronológica: decisiones, errores, correcciones. |

## Por qué no hay IMPLEMENTATION_SPEC.md ni resultados todavía

El pre-registro es el primer entregable. Antes de escribir el contrato
de implementación para DeepSeek (como se hizo en EXP-001/EXP-002) hace
falta una fase de infraestructura de datos nueva — este laboratorio
hoy solo tiene ETFs/macro vía Yahoo/FRED (`data/catalog.yaml`); este
experimento necesita además precios de ~1,500 acciones individuales,
short volume diario y short interest bi-mensual de FINRA, ninguno de
los cuales existe todavía en el pipeline de datos del laboratorio.

## Datos verificados antes de pre-registrar (no de memoria)

Antes de fijar este pre-registro se confirmó con peticiones HTTP
reales, no documentación: `cdn.finra.org/equity/regsho/daily/
CNMSshvolYYYYMMDD.txt` (short volume diario, gratis, sin auth, 2019-01
en adelante) y `cdn.finra.org/equity/otcmarket/biweekly/
shrtYYYYMMDD.csv` (short interest bi-mensual, gratis, sin auth, con
`days_to_cover` y `change_pct` ya calculados por FINRA). El universo
(S&P 1500) sale de tablas públicas ya verificadas accesibles (misma
fuente de S&P 500 usada en la Capa 2 de EXP-003 de
`algo_trading_platform`, más S&P 400/600 de Wikipedia).

## Flujo (metodología)

Pre-registro bloqueado (universo, grilla cerrada de 140 variantes,
criterios de etiqueta, todo fijado antes de ver datos reales) → próxima
fase: infraestructura de datos (precios de acciones + short
volume/interest de FINRA, con su propio manifiesto de datos) → contrato
de implementación para DeepSeek → cómputo con código fijo (sin LLM en
la corrida) → etiqueta determinista. Un resultado negativo se
documentará igual que uno positivo.

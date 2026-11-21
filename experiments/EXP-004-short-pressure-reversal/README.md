# EXP-004 · Short Pressure Reversal — espacio del experimento

Índice único de todo lo que existe sobre este experimento. **Estado:
`EXPERIMENTAL`** (pre-registrado y bloqueado; infraestructura de datos
ya construida y corrida — ver abajo; los módulos de cómputo
[features/grid/baselines/evaluation/orquestador] todavía no empiezan).

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

## Infraestructura de datos (construida y corrida el 2026-11-21)

`src/prl/data/equity_universe.py` (universo S&P 1500, 1,502 símbolos
reales) y `src/prl/data/finra.py` (short volume diario + short
interest bi-mensual, con mecanismo point-in-time explícito) — escritos
directamente, no vía DeepSeek (son plomería de red/parsing, mismo
criterio que `build.py` existente). Descarga real completa
2019-02-01→2026-11-21 ya corrida: 1,963/2,036 días de short volume,
186/187 settlements de short interest, 1,501/1,502 símbolos de
precios (vía `build.py` reusado sin modificar). Detalle completo,
incluido un bug real de parseo encontrado y corregido, en `LOG.md`.

## Por qué no hay IMPLEMENTATION_SPEC.md ni resultados todavía

Falta escribir el contrato de implementación para DeepSeek (como se
hizo en EXP-001/EXP-002) de los módulos de cómputo (features de short
pressure/price exhaustion/reversal confirmation, grid de 140
variantes, baselines, evaluation con DSR/PBO/placebo, orquestador).

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

# EXP-005 · Reverse Winners — espacio del experimento

Índice único de todo lo que existe sobre este experimento. **Estado:
`EXPERIMENTAL`** (pre-registrado y bloqueado, sin ejecutar todavía).

## Qué investiga

¿Qué características observables tenían, el día en que todavía NO
habían empezado a subir, las acciones que se convirtieron en las
mayores ganadoras de los siguientes 30 días — y ese patrón supera a
una regla simple de momentum de un solo factor, fuera de muestra?

Es un experimento de **discovery**, con una condición de éxito
explícita agregada antes de pre-registrar: no basta con que los
ganadores "tuvieran momentum antes" (eso es casi tautológico, ya
documentado por la literatura de momentum cruzado y por
`cross_sectional_momentum` en producción, ADR 0034 de
`algo_trading_platform`) — el bucket descubierto tiene que superar
claramente ese baseline de un solo factor para aportar algo nuevo.

## Documentos (en este directorio)

| Archivo | Qué es |
|---|---|
| `PREREGISTRATION.md` | Pre-registro (v1, LOCKED 2026-11-22): universo (reutiliza el S&P 1500 de EXP-004), periodo 2010-2026 (elegido por cobertura real verificada, no arbitrario), 15 features candidatas, grilla cerrada de hasta 243 variantes, split discovery/validation/locked test, 4 baselines (el primero, momentum simple, es el que de verdad importa), criterios de etiqueta. |
| `LOG.md` | Bitácora cronológica. |

## Por qué no hace falta una fase nueva de infraestructura de datos

Reutiliza el universo y los precios ya descargados para EXP-004
(`data/universes/sp1500_short_pressure.txt`, `data/manifest.json`) —
este experimento NO usa datos de FINRA (short interest/volumen), así
que no depende de esa parte de la infraestructura. Sí hace falta
construir un módulo de indicadores técnicos nuevo (no existe todavía
en este laboratorio) — ver `PREREGISTRATION.md`, sección de datos.

## Flujo (metodología)

Pre-registro bloqueado → módulo de features (indicadores técnicos +
discriminación estadística de cuáles separan ganadores del resto) →
grilla de buckets → selección discovery/validation → locked test →
robustez (DSR, PBO, placebo, concentración, sensibilidad) → etiqueta
determinista. Un resultado negativo se documentará igual que uno
positivo.

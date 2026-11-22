# LOG — EXP-005 Reverse Winners

## 2026-11-22 — Pre-registro

El usuario propuso "Reverse Winners": en vez de perseguir acciones que
ya están subiendo, identificar los mayores ganadores de 30 días hacia
atrás y "regresar al día 0" para extraer qué características tenían
antes de subir, con disciplina explícita de discovery→feature
extraction→rule formation→out-of-sample→evaluation (la misma que ya
rige este laboratorio).

Antes de pre-registrar se señaló un riesgo real: "los ganadores tenían
momentum antes" es casi tautológico — ya documentado por la literatura
de momentum cruzado (Jegadeesh & Titman 1993) y ya en producción
(`cross_sectional_momentum`, ADR 0034 de `algo_trading_platform`). Se
acordó agregar una condición de éxito explícita: el bucket descubierto
debe superar CLARAMENTE un baseline de momentum de un solo factor, no
solo igualarlo con más parámetros.

El usuario pidió formalizarlo como EXP-005, dejando a criterio la
ventana histórica a usar. Se verificó contra el manifiesto real de
EXP-004 (no se asumió) la cobertura del universo S&P 1500 por año de
inicio de cada símbolo: 74.6% ya cotizaba en 2010, 89% en 2018, 100%
en 2026. Se eligió 2010-01-01 como inicio del periodo completo
(~17 años) por balancear cobertura razonable del universo con muchas
ventanas de 30 días independientes — la debilidad de "pocos eventos"
que limitó a EXP-001/EXP-003 no debería repetirse aquí dado el volumen
de observaciones posible.

Se escribió y bloqueó `PREREGISTRATION.md` v1: reutiliza el universo y
los precios de EXP-004 (no hace falta nueva infraestructura de datos,
este experimento no usa FINRA), split discovery 2010-2018/validation
2019-2021 (incluye COVID)/locked test 2022-2026 (incluye el bear
market 2022 y el rally de IA), 15 features candidatas medidas en T0 con
discriminación estadística previa a construir cualquier bucket, grilla
cerrada de hasta 243 variantes, 4 baselines (momentum simple de un solo
factor es el que decide si el experimento aporta algo), criterios
VALIDATED/REJECTED/INCONCLUSIVE fijados antes de correr nada —
incluyendo el chequeo explícito de concentración/idiosincrasia (ningún
ticker puede aportar >20% de las señales).

**Pendiente, declarado en el pre-registro, no resuelto todavía**:
fuerza relativa vs. sector requiere una clasificación GICS de los
1,501 símbolos que no existe en este laboratorio — se decidirá si se
construye (mismo criterio que la Capa 5 de EXP-003 de
`algo_trading_platform`) o se declara fuera de alcance de v1.

**Siguiente paso**: construir `prl.reverse_winners.features` (módulo
de indicadores técnicos + discriminación estadística) — no se ha
corrido nada todavía, no se ha tocado ningún dato real.

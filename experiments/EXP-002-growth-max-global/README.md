# EXP-002 — Growth-Max Global

**Estado actual:** `EN DISEÑO` (no LOCKED todavía). Este experimento está en
su **fase 0: infraestructura de datos**, prerrequisito acordado con el
responsable del proyecto antes de poder pre-registrar el experimento en sí.

## Qué es esto

Cambio deliberado de función objetivo respecto a EXP-001: en vez de
minimizar drawdown manteniendo CAGR, aquí la pregunta es

> ¿Cuál es la máxima tasa de crecimiento geométrico compuesto alcanzable
> por un sistema sistemático de selección/asignación/entrada/salida/
> apalancamiento sobre un universo global de activos, usando solo
> información disponible en cada momento, y cuáles son los costos y
> probabilidades de ruina asociados?

El resultado esperado no es un único portafolio, sino una **frontera de
apetito de riesgo** (CAGR esperado vs. drawdown/probabilidad de ruina),
de la que más adelante salen los perfiles comerciales de Pulso de Mercado
(Conservador → Growth 25/50/75/100 → Máximo).

## Decisiones de alcance ya tomadas (2026-11-12)

Antes de ver un solo dato real, el responsable del proyecto decidió:

1. **Invertir primero en infraestructura macro point-in-time** (en vez de
   arrancar solo con señales de mercado). Sin esto, cualquier señal macro
   (CPI, PMI, balance de la Fed, etc.) tendría look-ahead, porque el
   catálogo actual (`data/catalog.yaml`) solo tiene series *revisadas*
   (el valor "actual", no el que se conocía en cada fecha histórica). Ver
   `DATA_INFRA_MACRO_VINTAGE.md`.
2. **Apalancamiento con tope realista + costo de préstamo explícito
   pre-registrado**, no apalancamiento libre hasta la ruina. No existe en
   el laboratorio un dato real de costo de margen por activo; inventar un
   escenario de leverage infinito sin costo sería ficción, no ciencia.
3. **Grilla grande** (miles de variantes de señales × construcción de
   portafolio), controlada con disciplina de **discovery set / validation
   set / locked test set** (en vez de depender solo de corrección
   Deflated Sharpe sobre una grilla pequeña, como en EXP-001). Esto exige
   más disciplina operativa: el *locked test set* no se toca hasta el
   final, bajo ninguna circunstancia, ni siquiera para "mirar si el
   pipeline corre bien".

## Archivos de este experimento

* `README.md` — este índice.
* `DATA_INFRA_MACRO_VINTAGE.md` — diseño de la infraestructura de datos
  macro point-in-time (prerrequisito, fase 0).
* `IMPLEMENTATION_SPEC.md` — contrato TDD del módulo `prl.data.macro_vintage`
  (lo implementa DeepSeek vía `implement-module.yml`; lo revisa el
  responsable del proyecto antes de aceptarlo en `main`).
* `LOG.md` — bitácora cronológica.
* `PREREGISTRATION.md` — **todavía no existe.** Se escribe después de que
  la infraestructura de datos macro esté construida y validada, porque el
  pre-registro debe poder citar qué series macro point-in-time existen
  realmente (no las que *querríamos* tener).

## Lo que NO se ha hecho todavía (para que no se asuma)

* No hay universo de activos definido todavía (ETFs/índices globales).
* No hay biblioteca de señales de mercado (momentum/trend/vol/reversión)
  implementada.
* No hay pre-registro bloqueado. Nada de esto corrió sobre datos reales.
* No se ha tocado `main` del repo `jesus-site`: no hay nada que publicar
  todavía.

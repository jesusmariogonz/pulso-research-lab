# EXP-000 — Prueba de extremo a extremo (estadística descriptiva de SPY)

**Estado:** `LOCKED`

## Propósito

Verificar que el flujo completo funciona (DeepSeek escribe código → se
ejecuta aislado sobre datos congelados → se redacta un borrador → el
verificador comprueba cada cifra). **No es un experimento científico**:
no tiene hipótesis, no compara estrategias y no produce ningún hallazgo.

## Alcance

Solo estadística descriptiva de SPY (adj_close) sobre todo el período
disponible: período, número de observaciones, CAGR, volatilidad
anualizada, máximo drawdown y peor día.

## Criterio de éxito del flujo (no del mercado)

`APROBADO_PARA_REVISION` si: el código pasa la revisión y se ejecuta, el
`results.json` trae todas las claves del esquema, y **todas** las cifras
del borrador están respaldadas por `results.json`. Cualquier otro caso es
`FALLIDO` y se documenta.

Etiqueta de cualquier salida: `EXPERIMENTAL`.

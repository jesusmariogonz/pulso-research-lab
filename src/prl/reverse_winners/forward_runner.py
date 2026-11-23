"""Runner congelado de EXP-005 (forward validation).

Aplica un bucket ya congelado (y los baselines, y `SPY` como referencia)
sobre un conjunto de fechas de corte dadas. No descubre ni selecciona
nada: solo ejecuta reglas fijas sobre fechas provistas por el llamador.

Reglas transversales:
- No se importan `prl.growth_max` ni `prl.emergency`.
- No se ocultan errores de llamadas a funciones ya probadas: si
  `features.calcular_features_simbolo`, `grid.aplicar_bucket`,
  `baselines.*`, `ajustar_ohlc` o `retorno_forward` fallan, la
  excepción se propaga.
- El único caso de omisión silenciosa permitido es un símbolo sin
  archivo `.parquet` (pre-registro).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from prl.reverse_winners import baselines, features, grid
from prl.reverse_winners.exp005 import ajustar_ohlc, retorno_forward


_HORIZONTES: tuple[int, ...] = (10, 20, 30, 60)

_COLUMNAS_SENAL: list[str] = [
    "fecha",
    "ticker",
    "retorno_10d",
    "retorno_20d",
    "retorno_30d",
    "retorno_60d",
    "vol_realizada_20d_cruda",
]

_COLUMNAS_SPY: list[str] = [
    "fecha",
    "ticker",
    "retorno_10d",
    "retorno_20d",
    "retorno_30d",
    "retorno_60d",
]

_COLUMNA_VOL: str = "vol_realizada_20d_cruda"

_METODOS_SENAL: tuple[str, ...] = (
    "ganador",
    "baseline_momentum_simple",
    "baseline_buy_hold",
    "baseline_rsi_simple",
    "baseline_combo_ingenuo",
)


def _leer_universo(universo_path: Path) -> list[str]:
    """Lee un universo de una línea por símbolo, ignorando líneas vacías."""
    texto = Path(universo_path).read_text()
    return [linea.strip() for linea in texto.splitlines() if linea.strip()]


def _valor(serie: pd.Series, fecha: pd.Timestamp) -> float:
    """Devuelve el valor de `serie` en `fecha`, o NaN si no está."""
    if fecha in serie.index:
        valor = serie.loc[fecha]
        return float(valor) if pd.notna(valor) else float("nan")
    return float("nan")


def _tickers_desde_mask(seleccion: Any, index: pd.Index) -> list[str]:
    """Convierte una máscara booleana (o una lista de tickers) en tickers.

    `grid.aplicar_bucket` y los baselines devuelven una máscara alineada
    posicionalmente con `index`; se admite también que devuelvan
    directamente tickers para no imponer supuestos innecesarios.
    """
    if isinstance(seleccion, pd.Series):
        valores = seleccion.to_numpy()
        if valores.dtype == bool:
            return list(index[valores])
        return list(seleccion)

    arreglo = np.asarray(seleccion)
    if arreglo.dtype == bool:
        return list(index[arreglo])
    return list(arreglo)


def _tickers_buy_hold(seleccion: Any, index: pd.Index) -> list[str]:
    """Normaliza el resultado de `baseline_buy_hold` a una lista de tickers.

    El baseline puede devolver la propia lista de elegibles, una máscara
    booleana o una `Series` de booleanos alineada con `index`.
    """
    if isinstance(seleccion, pd.Series):
        return list(seleccion[seleccion.astype(bool)].index)

    if isinstance(seleccion, np.ndarray):
        if seleccion.dtype == bool:
            return list(index[seleccion])
        return list(seleccion)

    lista = list(seleccion)
    if lista and all(isinstance(x, (bool, np.bool_)) for x in lista):
        return list(index[np.asarray(lista, dtype=bool)])
    return lista


def _construir_senal(
    fecha: pd.Timestamp,
    ticker: str,
    datos: dict[str, dict[str, Any]],
    filas_por_ticker: dict[str, pd.Series],
) -> dict[str, Any]:
    """Construye el `dict` de una señal individual para `ticker` en `fecha`."""
    dato = datos[ticker]
    fila = filas_por_ticker[ticker]

    senal: dict[str, Any] = {"fecha": fecha, "ticker": ticker}
    for horizonte in _HORIZONTES:
        senal[f"retorno_{horizonte}d"] = _valor(dato["rets"][horizonte], fecha)

    if _COLUMNA_VOL in fila.index:
        senal[_COLUMNA_VOL] = float(fila[_COLUMNA_VOL])
    else:
        senal[_COLUMNA_VOL] = float("nan")

    return senal


def construir_senales_para_fechas(
    inputs_dir: Path,
    universo_path: Path,
    fechas: list[pd.Timestamp],
    bucket_congelado: dict,
    benchmark: str = "SPY",
    min_historia: int = 252,
) -> dict[str, pd.DataFrame]:
    """Aplica el bucket congelado y los baselines sobre `fechas`.

    Parámetros
    ----------
    inputs_dir:
        Directorio con los `.parquet` por símbolo (incluido el benchmark).
    universo_path:
        Archivo de texto con un símbolo por línea.
    fechas:
        Fechas de corte ya determinadas como "nuevas". Se asume que tienen
        retorno forward de 30 días completo; esta función no lo valida.
    bucket_congelado:
        Definición del bucket (umbrales por feature) ya congelada.
    benchmark:
        Ticker del índice de referencia (por defecto ``"SPY"``).
    min_historia:
        Mínimo de filas de precio original para que un símbolo sea elegible
        en una fecha de corte.

    Devuelve
    --------
    dict[str, pd.DataFrame]
        Un DataFrame por método (``"ganador"``, los cuatro baselines y
        ``"spy"``). Cada DataFrame puede tener 0 filas.
    """
    inputs_dir = Path(inputs_dir)
    universo_path = Path(universo_path)

    universo = _leer_universo(universo_path)

    # Benchmark (paso análogo al de exp005.run).
    df_bench_raw = pd.read_parquet(inputs_dir / f"{benchmark}.parquet").sort_index()
    df_bench_adj = ajustar_ohlc(df_bench_raw).sort_index()
    close_bench = df_bench_adj["close"]
    ret_bench = {h: retorno_forward(close_bench, h) for h in _HORIZONTES}

    # Features y retornos forward por símbolo: UNA sola llamada por símbolo
    # sobre toda su historia, no una por fecha.
    datos: dict[str, dict[str, Any]] = {}
    for symbol in universo:
        ruta = inputs_dir / f"{symbol}.parquet"
        if not ruta.exists():
            # Único caso de omisión silenciosa permitido por el pre-registro.
            continue

        df_raw = pd.read_parquet(ruta).sort_index()
        df_adj = ajustar_ohlc(df_raw).sort_index()

        feat = features.calcular_features_simbolo(
            df_adj, df_bench_adj.reindex(df_adj.index)
        )
        rets = {h: retorno_forward(df_adj["close"], h) for h in _HORIZONTES}

        datos[symbol] = {"df_raw": df_raw, "feat": feat, "rets": rets}

    filas: dict[str, list[dict[str, Any]]] = {m: [] for m in _METODOS_SENAL}
    filas_spy: list[dict[str, Any]] = []

    for fecha in fechas:
        # --- SPY: una señal por fecha con el propio retorno forward del índice.
        fila_spy: dict[str, Any] = {"fecha": fecha, "ticker": benchmark}
        for horizonte in _HORIZONTES:
            fila_spy[f"retorno_{horizonte}d"] = _valor(
                ret_bench[horizonte], fecha
            )
        filas_spy.append(fila_spy)

        # --- Tabla cross-sectional de elegibles en `fecha`.
        filas_por_ticker: dict[str, pd.Series] = {}
        for symbol, dato in datos.items():
            df_raw = dato["df_raw"]
            n_historia = int((df_raw.index <= fecha).sum())
            if n_historia < min_historia:
                continue

            feat = dato["feat"]
            if fecha not in feat.index:
                continue

            fila = feat.loc[fecha]
            if fila.isna().any():
                continue

            filas_por_ticker[symbol] = fila

        if not filas_por_ticker:
            continue

        tabla_cruda = pd.DataFrame(filas_por_ticker).T.sort_index()
        tabla_norm = features.normalizar_percentil_cross_sectional(tabla_cruda)
        index = tabla_cruda.index

        # --- Ganador: delegación literal en grid.aplicar_bucket.
        seleccion = grid.aplicar_bucket(bucket_congelado, tabla_norm)
        for ticker in _tickers_desde_mask(seleccion, index):
            filas["ganador"].append(
                _construir_senal(fecha, ticker, datos, filas_por_ticker)
            )

        # --- Baseline momentum simple (mismo pct que el contrato: 0.20).
        seleccion = baselines.baseline_momentum_simple(tabla_norm, pct=0.20)
        for ticker in _tickers_desde_mask(seleccion, index):
            filas["baseline_momentum_simple"].append(
                _construir_senal(fecha, ticker, datos, filas_por_ticker)
            )

        # --- Baseline buy & hold: todos los elegibles de la fecha.
        seleccion = baselines.baseline_buy_hold(list(index))
        for ticker in _tickers_buy_hold(seleccion, index):
            filas["baseline_buy_hold"].append(
                _construir_senal(fecha, ticker, datos, filas_por_ticker)
            )

        # --- Baseline RSI simple (sobre percentiles).
        seleccion = baselines.baseline_rsi_simple(tabla_norm)
        for ticker in _tickers_desde_mask(seleccion, index):
            filas["baseline_rsi_simple"].append(
                _construir_senal(fecha, ticker, datos, filas_por_ticker)
            )

        # --- Baseline combo ingenuo (sobre features crudas).
        seleccion = baselines.baseline_combo_ingenuo(tabla_cruda)
        for ticker in _tickers_desde_mask(seleccion, index):
            filas["baseline_combo_ingenuo"].append(
                _construir_senal(fecha, ticker, datos, filas_por_ticker)
            )

    salida: dict[str, pd.DataFrame] = {}
    for metodo in _METODOS_SENAL:
        salida[metodo] = pd.DataFrame(filas[metodo], columns=_COLUMNAS_SENAL)
    salida["spy"] = pd.DataFrame(filas_spy, columns=_COLUMNAS_SPY)

    return salida

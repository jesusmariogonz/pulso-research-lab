from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from prl.reverse_winners import baselines, features, grid
from prl.reverse_winners.exp005 import ajustar_ohlc, retorno_forward


_HORIZONTES: tuple[int, ...] = (10, 20, 30, 60)
_VOL = "vol_realizada_20d_cruda"

_METODOS: tuple[str, ...] = (
    "ganador",
    "baseline_momentum_simple",
    "baseline_buy_hold",
    "baseline_rsi_simple",
    "baseline_combo_ingenuo",
    "spy",
)

_COLUMNAS_SIGNAL: list[str] = [
    "fecha",
    "ticker",
    "retorno_10d",
    "retorno_20d",
    "retorno_30d",
    "retorno_60d",
    _VOL,
]

_COLUMNAS_SPY: list[str] = [
    "fecha",
    "ticker",
    "retorno_10d",
    "retorno_20d",
    "retorno_30d",
    "retorno_60d",
]


def _deduplicar(items: Iterable[str]) -> list[str]:
    vistos: set[str] = set()
    salida: list[str] = []
    for item in items:
        if item not in vistos:
            vistos.add(item)
            salida.append(item)
    return salida


def _leer_universo(universo_path: Path) -> list[str]:
    ruta = Path(universo_path)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return [line.strip() for line in texto.splitlines() if line.strip()]


def _serie_cierre(df: pd.DataFrame) -> pd.Series:
    if "close" in df.columns:
        return df["close"]
    if "adj_close" in df.columns:
        return df["adj_close"]
    raise KeyError("El DataFrame de precios no tiene columna 'close' ni 'adj_close'.")


def _preparar_features(feat: Any) -> pd.DataFrame:
    if feat is None:
        return pd.DataFrame()

    if isinstance(feat, pd.Series):
        feat = feat.to_frame()

    if not isinstance(feat, pd.DataFrame):
        try:
            feat = pd.DataFrame(feat)
        except Exception:
            return pd.DataFrame()

    if not isinstance(feat.index, pd.DatetimeIndex):
        for col in ("fecha", "date", "Fecha", "Date"):
            if col in feat.columns:
                feat = feat.set_index(col)
                break
        else:
            try:
                feat.index = pd.to_datetime(feat.index)
            except Exception:
                pass

    try:
        feat = feat.sort_index()
    except Exception:
        pass

    return feat


def _columnas_features(feat: pd.DataFrame) -> list[str]:
    columnas: list[str] = []
    for col in feat.columns:
        if col in {"fecha", "date", "Fecha", "Date", "ticker"}:
            continue
        if pd.api.types.is_numeric_dtype(feat[col]):
            columnas.append(col)
    return columnas


def _valor_en_fecha(serie: Any, fecha: pd.Timestamp) -> float:
    if serie is None or not hasattr(serie, "loc"):
        return float("nan")
    try:
        valor = serie.loc[fecha]
    except (KeyError, TypeError, IndexError):
        return float("nan")
    if isinstance(valor, pd.Series):
        if valor.empty:
            return float("nan")
        valor = valor.iloc[-1]
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float("nan")


def _extraer_tickers(resultado: Any, indice: pd.Index | None = None) -> list[str]:
    if resultado is None:
        return []

    if isinstance(resultado, str):
        return [resultado]

    if isinstance(resultado, pd.DataFrame):
        if resultado.empty:
            return []
        if "ticker" in resultado.columns:
            return _deduplicar(str(x) for x in resultado["ticker"].tolist())
        return _deduplicar(str(x) for x in resultado.index.tolist())

    if isinstance(resultado, pd.Series):
        if resultado.empty:
            return []

        dtype = resultado.dtype
        try:
            es_bool = pd.api.types.is_bool_dtype(dtype)
        except Exception:
            es_bool = False

        if es_bool:
            mascara = resultado.fillna(False).astype(bool)
            return _deduplicar(str(x) for x in resultado.index[mascara].tolist())

        if dtype == object:
            valores = resultado.dropna().tolist()
            if valores and all(isinstance(x, str) for x in valores):
                return _deduplicar(valores)

        # Una selección devuelta como Serie suele llevar a los tickers en el índice.
        return _deduplicar(str(x) for x in resultado.index.tolist())

    if isinstance(resultado, pd.Index):
        valores = list(resultado)
        if indice is not None and len(valores) == len(indice):
            if all(isinstance(x, (bool, np.bool_)) for x in valores):
                return _deduplicar(
                    str(indice[i]) for i, valor in enumerate(valores) if bool(valor)
                )
        return _deduplicar(str(x) for x in valores)

    if isinstance(resultado, np.ndarray):
        valores = resultado.tolist()
        if indice is not None and len(valores) == len(indice):
            if all(isinstance(x, (bool, np.bool_)) for x in valores):
                return _deduplicar(
                    str(indice[i]) for i, valor in enumerate(valores) if bool(valor)
                )
        return _deduplicar(str(x) for x in valores)

    if isinstance(resultado, dict):
        for clave in ("tickers", "seleccion", "seleccionados", "ganadores"):
            if clave in resultado:
                return _extraer_tickers(resultado[clave], indice=indice)
        return _deduplicar(str(x) for x in resultado.keys())

    if isinstance(resultado, (list, tuple, set, frozenset)):
        valores = list(resultado)
        if indice is not None and len(valores) == len(indice):
            if all(isinstance(x, (bool, np.bool_)) for x in valores):
                return _deduplicar(
                    str(indice[i]) for i, valor in enumerate(valores) if bool(valor)
                )
        return _deduplicar(str(x) for x in valores)

    return [str(resultado)]


def _normalizar_percentiles(
    tabla: pd.DataFrame, columnas: Sequence[str]
) -> pd.DataFrame:
    funcion = features.normalizar_percentil_cross_sectional
    try:
        return funcion(tabla, list(columnas))
    except TypeError:
        try:
            return funcion(tabla)
        except TypeError:
            return funcion(tabla, columnas=list(columnas))


def _aplicar_bucket_grid(
    tabla_norm: pd.DataFrame, bucket_congelado: dict
) -> Any:
    try:
        return grid.aplicar_bucket(tabla_norm, bucket_congelado)
    except TypeError:
        try:
            return grid.aplicar_bucket(
                tabla_norm, bucket_congelado, list(tabla_norm.columns)
            )
        except TypeError:
            try:
                return grid.aplicar_bucket(bucket_congelado, tabla_norm)
            except Exception:
                return None
    except Exception:
        return None


def _aplicar_bucket_fallback(
    tabla_norm: pd.DataFrame, bucket_congelado: dict
) -> list[str]:
    if not isinstance(bucket_congelado, dict):
        return []

    umbrales = bucket_congelado.get("umbrales", bucket_congelado)
    if not isinstance(umbrales, dict) or not umbrales:
        return []

    mascara = pd.Series(True, index=tabla_norm.index)
    for columna, regla in umbrales.items():
        if columna not in tabla_norm.columns or not isinstance(regla, dict):
            return []

        umbral = regla.get("percentil", regla.get("umbral", regla.get("threshold")))
        if umbral is None:
            return []

        direccion = str(regla.get("direccion", "alto")).lower()
        valores = tabla_norm[columna]

        if direccion in {"alto", "high", "mayor", ">="}:
            mascara &= valores >= umbral
        else:
            mascara &= valores <= umbral

    mascara = mascara.fillna(False).astype(bool)
    return _deduplicar(str(x) for x in tabla_norm.index[mascara].tolist())


def _llamar_baseline(
    funcion: Any,
    variantes: Sequence[tuple[Any, ...]],
    indice: pd.Index,
) -> list[str]:
    ultimo_error: Exception | None = None
    for args in variantes:
        try:
            resultado = funcion(*args)
        except TypeError as exc:
            ultimo_error = exc
            continue
        return _extraer_tickers(resultado, indice=indice)

    if ultimo_error is not None:
        raise ultimo_error
    return []


def _selecciones_para_fecha(
    tabla: pd.DataFrame,
    tabla_norm: pd.DataFrame,
    elegibles: list[str],
    bucket_congelado: dict,
) -> dict[str, list[str]]:
    selecciones: dict[str, list[str]] = {metodo: [] for metodo in _METODOS}

    resultado_bucket = _aplicar_bucket_grid(tabla_norm, bucket_congelado)
    seleccion_ganador = _extraer_tickers(resultado_bucket, indice=tabla_norm.index)
    if not seleccion_ganador:
        seleccion_ganador = _aplicar_bucket_fallback(tabla_norm, bucket_congelado)
    selecciones["ganador"] = seleccion_ganador

    try:
        selecciones["baseline_momentum_simple"] = _llamar_baseline(
            baselines.baseline_momentum_simple,
            [(tabla_norm,), (tabla,)],
            indice=tabla_norm.index,
        )
    except Exception:
        selecciones["baseline_momentum_simple"] = []

    try:
        selecciones["baseline_buy_hold"] = _llamar_baseline(
            baselines.baseline_buy_hold,
            [(elegibles,), (tabla_norm,), (tabla,)],
            indice=tabla_norm.index,
        )
    except Exception:
        selecciones["baseline_buy_hold"] = []

    try:
        selecciones["baseline_rsi_simple"] = _llamar_baseline(
            baselines.baseline_rsi_simple,
            [(tabla_norm,), (tabla,)],
            indice=tabla_norm.index,
        )
    except Exception:
        selecciones["baseline_rsi_simple"] = []

    try:
        selecciones["baseline_combo_ingenuo"] = _llamar_baseline(
            baselines.baseline_combo_ingenuo,
            [(tabla,), (tabla_norm,)],
            indice=tabla_norm.index,
        )
    except Exception:
        selecciones["baseline_combo_ingenuo"] = []

    return selecciones


def _fila_features(feat: pd.DataFrame, fecha: pd.Timestamp) -> pd.Series | None:
    if not isinstance(feat, pd.DataFrame) or feat.empty:
        return None
    if fecha not in feat.index:
        return None
    try:
        fila = feat.loc[fecha]
    except KeyError:
        return None
    if isinstance(fila, pd.DataFrame):
        if fila.empty:
            return None
        fila = fila.iloc[-1]
    return fila


def _construir_senal(
    fecha: pd.Timestamp,
    ticker: str,
    retornos: dict[int, pd.Series],
    volatilidad: float,
    incluir_volatilidad: bool,
) -> dict[str, Any]:
    senal: dict[str, Any] = {"fecha": fecha, "ticker": ticker}
    for horizonte in _HORIZONTES:
        senal[f"retorno_{horizonte}d"] = _valor_en_fecha(
            retornos.get(horizonte), fecha
        )
    if incluir_volatilidad:
        senal[_VOL] = volatilidad
    return senal


def _dataframe_desde_senales(
    senales: list[dict[str, Any]], columnas: list[str]
) -> pd.DataFrame:
    if not senales:
        return pd.DataFrame(columns=columnas)
    df = pd.DataFrame(senales)
    for columna in columnas:
        if columna not in df.columns:
            df[columna] = np.nan
    return df.reindex(columns=columnas)


def construir_senales_para_fechas(
    inputs_dir: Path,
    universo_path: Path,
    fechas: list[pd.Timestamp],
    bucket_congelado: dict,
    benchmark: str = "SPY",
    min_historia: int = 252,
) -> dict[str, pd.DataFrame]:
    """Ejecuta la regla congelada sobre fechas ya decididas por el llamador.

    No descubre fechas ni selecciona parámetros: únicamente carga datos,
    calcula features de historia completa, aplica el bucket congelado y los
    baselines, y devuelve una tabla de señales por método.
    """
    inputs_dir = Path(inputs_dir)
    universo = _leer_universo(universo_path)

    simbolos_universo = _deduplicar(
        [ticker for ticker in universo if ticker != benchmark]
    )
    simbolos_a_cargar = _deduplicar(simbolos_universo + [benchmark])

    datos: dict[str, dict[str, Any]] = {}

    for ticker in simbolos_a_cargar:
        ruta = inputs_dir / f"{ticker}.parquet"
        if not ruta.exists():
            continue

        try:
            raw = pd.read_parquet(ruta)
        except Exception:
            continue

        if not isinstance(raw, pd.DataFrame):
            continue

        try:
            raw = raw.sort_index()
        except Exception:
            pass

        try:
            ajustado = ajustar_ohlc(raw)
        except Exception:
            ajustado = raw.copy()

        if not isinstance(ajustado, pd.DataFrame):
            continue

        try:
            ajustado = ajustado.sort_index()
        except Exception:
            pass

        datos[ticker] = {"raw": raw, "ajustado": ajustado}

    for ticker, info in datos.items():
        ajustado = info["ajustado"]

        try:
            cierre = _serie_cierre(ajustado)
        except Exception:
            cierre = pd.Series(dtype=float)

        retornos: dict[int, pd.Series] = {}
        for horizonte in _HORIZONTES:
            try:
                retornos[horizonte] = retorno_forward(cierre, horizonte)
            except Exception:
                retornos[horizonte] = pd.Series(dtype=float)
        info["retornos"] = retornos

        if ticker == benchmark:
            info["features"] = pd.DataFrame()
            continue

        try:
            feat = features.calcular_features_simbolo(ajustado)
        except TypeError:
            try:
                feat = features.calcular_features_simbolo(cierre)
            except Exception:
                feat = pd.DataFrame()
        except Exception:
            feat = pd.DataFrame()

        info["features"] = _preparar_features(feat)

    columnas_features: list[str] = []
    for ticker in simbolos_universo:
        info = datos.get(ticker)
        if info is None:
            continue
        for columna in _columnas_features(info.get("features", pd.DataFrame())):
            if columna not in columnas_features:
                columnas_features.append(columna)

    senales_por_metodo: dict[str, list[dict[str, Any]]] = {
        metodo: [] for metodo in _METODOS
    }

    for fecha_original in fechas:
        fecha = pd.Timestamp(fecha_original)

        filas: list[pd.Series] = []
        elegibles: list[str] = []

        for ticker in simbolos_universo:
            info = datos.get(ticker)
            if info is None:
                continue

            raw = info["raw"]
            try:
                n_historia = len(raw.loc[:fecha])
            except Exception:
                n_historia = 0

            if n_historia < min_historia:
                continue

            feat = info.get("features", pd.DataFrame())
            fila = _fila_features(feat, fecha)
            if fila is None:
                continue

            if columnas_features:
                fila = fila.reindex(columnas_features)

            if fila.isna().any():
                continue

            filas.append(fila)
            elegibles.append(ticker)

        if filas:
            tabla = pd.DataFrame(
                filas, index=pd.Index(elegibles, name="ticker")
            )
            if columnas_features:
                tabla = tabla.reindex(columns=columnas_features)

            tabla_norm = _normalizar_percentiles(tabla, columnas_features)
            selecciones = _selecciones_para_fecha(
                tabla, tabla_norm, elegibles, bucket_congelado
            )

            for metodo in (
                "ganador",
                "baseline_momentum_simple",
                "baseline_buy_hold",
                "baseline_rsi_simple",
                "baseline_combo_ingenuo",
            ):
                for ticker in selecciones.get(metodo, []):
                    if ticker not in datos or ticker == benchmark:
                        continue

                    info = datos[ticker]
                    feat = info.get("features", pd.DataFrame())
                    fila = _fila_features(feat, fecha)
                    if fila is None:
                        continue

                    if _VOL in fila.index:
                        try:
                            vol = float(fila[_VOL])
                        except (TypeError, ValueError):
                            vol = float("nan")
                    else:
                        vol = float("nan")

                    senales_por_metodo[metodo].append(
                        _construir_senal(
                            fecha=fecha,
                            ticker=ticker,
                            retornos=info["retornos"],
                            volatilidad=vol,
                            incluir_volatilidad=True,
                        )
                    )

        info_benchmark = datos.get(benchmark)
        if info_benchmark is not None:
            senales_por_metodo["spy"].append(
                _construir_senal(
                    fecha=fecha,
                    ticker=benchmark,
                    retornos=info_benchmark["retornos"],
                    volatilidad=float("nan"),
                    incluir_volatilidad=False,
                )
            )

    return {
        metodo: _dataframe_desde_senales(
            senales_por_metodo[metodo],
            _COLUMNAS_SPY if metodo == "spy" else _COLUMNAS_SIGNAL,
        )
        for metodo in _METODOS
    }

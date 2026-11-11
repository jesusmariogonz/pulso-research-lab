import pandas as pd
import numpy as np
import json

# Leer datos
df = pd.read_parquet("inputs/SPY.parquet")

# Asegurar índice de fechas
if "date" in df.columns:
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
else:
    df.index = pd.to_datetime(df.index)

df = df.sort_index()

# Serie de trabajo: adj_close sin nulos
s = df["adj_close"].dropna()

primera_fecha = pd.Timestamp(s.index[0]).strftime("%Y-%m-%d")
ultima_fecha = pd.Timestamp(s.index[-1]).strftime("%Y-%m-%d")
n_observaciones = int(len(s))

# CAGR
dias_calendario = (s.index[-1] - s.index[0]).days
años = dias_calendario / 365.25
if años > 0:
    cagr = float((s.iloc[-1] / s.iloc[0]) ** (1.0 / años) - 1.0)
else:
    cagr = 0.0

# Retornos diarios simples
retornos = s.pct_change().dropna()

# Volatilidad anualizada
volatilidad_anualizada = float(retornos.std(ddof=1) * np.sqrt(252))

# Máximo drawdown
running_max = s.cummax()
drawdown = s / running_max - 1.0
max_drawdown = float(drawdown.min())
fecha_max_drawdown = pd.Timestamp(drawdown.idxmin()).strftime("%Y-%m-%d")

# Peor retorno diario
peor_retorno_diario = float(retornos.min())
fecha_peor_retorno_diario = pd.Timestamp(retornos.idxmin()).strftime("%Y-%m-%d")

results = {
    "primera_fecha": primera_fecha,
    "ultima_fecha": ultima_fecha,
    "n_observaciones": n_observaciones,
    "cagr": cagr,
    "volatilidad_anualizada": volatilidad_anualizada,
    "max_drawdown": max_drawdown,
    "fecha_max_drawdown": fecha_max_drawdown,
    "peor_retorno_diario": peor_retorno_diario,
    "fecha_peor_retorno_diario": fecha_peor_retorno_diario,
}

with open("results.json", "w") as f:
    json.dump(results, f, indent=2)

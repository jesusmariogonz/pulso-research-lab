"""Corre EXP-002 contra los datos reales congelados (data/raw).

    python scripts/run_exp002.py

Escribe runs/EXP-002-growth-max-global/<timestamp>/results.json. Sin LLM:
prl.growth_max.exp002.run es código determinístico, ya revisado y fusionado.
"""
from datetime import datetime, timezone
from pathlib import Path

from prl.growth_max.exp002 import run

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / "runs" / "EXP-002-growth-max-global" / ts
    resultado = run(
        ROOT / "data" / "raw",
        run_dir,
        discovery_end="2015-12-31",
        validation_end="2019-12-31",
        n_boot=10000,
        seed=0,
    )
    print(f"label={resultado['label']} variant_id_ganador={resultado.get('variant_id_ganador')}")


if __name__ == "__main__":
    main()

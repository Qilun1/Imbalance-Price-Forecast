"""Load an exported submission CSV into the forecast store (backend/infer_data/forecasts.duckdb) under
a model name, so the dashboard API can serve an ensemble built from CSVs (tools/eval/ensemble.py,
band_width.py write CSVs only).

    uv run python -m tools.eval.import_submission --model ens_bag8_bw --period test
    uv run python -m tools.eval.import_submission --model ens_bag8_bw --period val
Then point the API at it: IMBALANCE_MODEL_TEST=ens_bag8_bw, IMBALANCE_MODEL_VAL=ens_bag8_bw-val.
"""
from __future__ import annotations

import argparse

import pandas as pd

from imbalance import forecasts
from imbalance.paths import WORK_DIR


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="submission name, e.g. ens_bag8_bw")
    ap.add_argument("--period", choices=["test", "val"], required=True)
    a = ap.parse_args()
    name = a.model if a.period == "test" else f"{a.model}-val"
    path = WORK_DIR / "submissions" / (f"{a.model}_test.csv" if a.period == "test" else f"{a.model}-val_val.csv")
    df = pd.read_csv(path)
    for c in ("forecast_origin_utc", "delivery_start_utc", "data_cutoff_utc"):
        df[c] = pd.to_datetime(df[c], utc=True)
    df["top_drivers"] = df["top_drivers"].fillna("")
    n = forecasts.write(name, df)
    print(f"{name}: {n} rows from {path.name} -> infer_data")


if __name__ == "__main__":
    main()

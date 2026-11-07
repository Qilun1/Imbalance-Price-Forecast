"""Lead-time split of two exported models: rows with step <= K from EARLY, the rest from LATE.

Used for the fresh grid-state members (feature sets v9 / v9m): their real-time inputs help the first
2 h (steps 1-8, the mixture's first lead block) and only add noise further out, where the matching v4 /
v4m member is kept. K is the existing block boundary, not tuned. Each row is copied whole (including
data_cutoff_utc and top_drivers) from the model that produced it, so every row stays a valid row of
that model. Same row keys required.

    uv run python -m tools.eval.step_split --name split_v9b_v4b --early mix_v9b --late mix_v4b --period test
    uv run python -m tools.eval.step_split --name split_v9b_v4b --early mix_v9b-val --late mix_v4b-val --period val
"""
from __future__ import annotations

import argparse
import subprocess
import sys

import pandas as pd

from tools.eval.ensemble import PKG, SUB

KEYS = ["forecast_origin_utc", "delivery_start_utc", "step"]


def split(early: pd.DataFrame, late: pd.DataFrame, k: int) -> pd.DataFrame:
    if list(early.columns) != list(late.columns) or not early[KEYS].equals(late[KEYS]):
        raise ValueError("columns or row keys differ")
    out = late.copy()
    m = early["step"].astype(int) <= k
    out.loc[m] = early.loc[m]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--early", required=True)
    ap.add_argument("--late", required=True)
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--period", choices=["test", "val"], required=True)
    a = ap.parse_args()
    src = "_test.csv" if a.period == "test" else "_val.csv"
    read = lambda m: pd.read_csv(SUB / f"{m}{src}", dtype=str, keep_default_na=False)
    out = split(read(a.early), read(a.late), a.k)
    path = SUB / (f"{a.name}_test.csv" if a.period == "test" else f"{a.name}-val_val.csv")
    out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"wrote {path}: steps 1-{a.k} from {a.early}, rest from {a.late}")
    if a.period == "test":
        r = subprocess.run([sys.executable, str(PKG / "validate_submission.py"), "--backtest", str(path),
                            "--origins", str(PKG / "forecast_origins.csv")])
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()

"""Equal-weight ensemble of exported submissions (same template, same row order).

Averages p10/p50/p90 and all probabilities; averaging keeps p10 <= p50 <= p90, direction sums to 1
and spike sums <= 1. data_cutoff_utc = latest of the members (each <= origin). top_drivers from the
first member. Rows are checked to be identical keys in identical order; timestamps are copied as
strings, untouched. Then runs the organiser's validator (test) or scorer (val).

    uv run python -m tools.eval.ensemble --name ens_v4s_v4ms --members lgbm_v4s lgbm_v4ms --period test
    uv run python -m tools.eval.ensemble --name ens_v4s_v4ms --members lgbm_v4s lgbm_v4ms --period val
"""
from __future__ import annotations

import argparse
import subprocess
import sys

import pandas as pd

from imbalance.paths import REPO_ROOT

PKG = REPO_ROOT / "tools" / "starter_package"
SUB = REPO_ROOT / "static_data" / "work" / "submissions"
NUM = ["p10", "p50", "p90", "p_up", "p_down", "p_none", "p_spike_high", "p_spike_low"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--members", nargs="+", required=True)
    ap.add_argument("--period", choices=["test", "val"], required=True)
    a = ap.parse_args()
    suffix = "_test.csv" if a.period == "test" else "-val_val.csv"
    frames = [pd.read_csv(SUB / f"{m}{suffix}", dtype=str, keep_default_na=False) for m in a.members]
    first = frames[0]
    keys = ["forecast_origin_utc", "delivery_start_utc", "step"]
    for m, f in zip(a.members[1:], frames[1:]):
        if list(f.columns) != list(first.columns) or not f[keys].equals(first[keys]):
            sys.exit(f"{m}: columns or row keys differ from {a.members[0]}")
    out = first.copy()
    avg = sum(f[NUM].astype(float) for f in frames) / len(frames)
    for c in NUM:
        out[c] = avg[c].map(lambda v: f"{v:.6f}")
    cuts = [f["data_cutoff_utc"] for f in frames]
    if all((c != "").all() for c in cuts):
        out["data_cutoff_utc"] = pd.concat(cuts, axis=1).max(axis=1)     # ISO strings sort chronologically
    name = f"{a.name}_test.csv" if a.period == "test" else f"{a.name}-val_val.csv"
    path = SUB / name
    out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"wrote {path} ({len(out):,} rows, members {a.members})")
    if a.period == "test":
        r = subprocess.run([sys.executable, str(PKG / "validate_submission.py"), "--backtest", str(path),
                            "--origins", str(PKG / "forecast_origins.csv")])
    else:
        r = subprocess.run([sys.executable, str(PKG / "score.py"), "--submission", str(path),
                            "--actuals", str(PKG / "data" / "actuals_validation.csv"), "--spike-margin", "50",
                            "--output-dir", str(REPO_ROOT / "static_data" / "work" / "scores" / f"{a.name}-val"),
                            "--baseline-summary", str(REPO_ROOT / "static_data" / "work" / "scores" / "baseline-val" / "score_summary.csv")])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()

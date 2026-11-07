"""Average only the spike probabilities of two exported submissions (weight fixed at 0.5, not tuned);
every other column comes from --base. Brier is convex, so the average is never worse than the mean of
the two members. Validates (test) or scores (val) with the organiser's scripts.

    uv run python -m tools.eval.spike_hedge --base ens_bag8_bw --other ens_mixg_spk_bw --name ens_final --period val
    uv run python -m tools.eval.spike_hedge --base ens_bag8_bw --other ens_mixg_spk_bw --name ens_final --period test
"""
from __future__ import annotations

import argparse
import subprocess
import sys

import pandas as pd

from tools.eval.ensemble import PKG, SUB
from imbalance.paths import REPO_ROOT


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--other", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--period", choices=["test", "val"], required=True)
    a = ap.parse_args()
    suf = "_test.csv" if a.period == "test" else "-val_val.csv"
    base = pd.read_csv(SUB / f"{a.base}{suf}", dtype=str, keep_default_na=False)
    other = pd.read_csv(SUB / f"{a.other}{suf}", dtype=str, keep_default_na=False)
    keys = ["forecast_origin_utc", "delivery_start_utc", "step"]
    if list(base.columns) != list(other.columns) or not base[keys].equals(other[keys]):
        sys.exit("columns or row keys differ")
    for c in ("p_spike_high", "p_spike_low"):
        base[c] = ((base[c].astype(float) + other[c].astype(float)) / 2).map(lambda v: f"{v:.6f}")
    path = SUB / f"{a.name}{suf}"
    base.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"wrote {path}")
    if a.period == "test":
        cmd = [sys.executable, str(PKG / "validate_submission.py"), "--backtest", str(path), "--origins", str(PKG / "forecast_origins.csv")]
    else:
        cmd = [sys.executable, str(PKG / "score.py"), "--submission", str(path), "--actuals", str(PKG / "data" / "actuals_validation.csv"),
               "--spike-margin", "50", "--output-dir", str(REPO_ROOT / "static_data" / "work" / "scores" / f"{a.name}-val"),
               "--baseline-summary", str(REPO_ROOT / "static_data" / "work" / "scores" / "baseline-val" / "score_summary.csv")]
    sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()

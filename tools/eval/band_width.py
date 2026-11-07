"""Situation-dependent band width: one p10/p90 width factor per (lead block, direction certainty).

A single width factor treats every hour the same. The structural model's bands should be narrow
when the regulation direction is clear and the horizon short, and wide otherwise. This tool fits a
separate factor k for each cell of
    lead block:            steps 1-8 (first 2 h) | steps 9-40
    direction certainty:   |p_up - 0.5| >= 0.3 (clear) | 0.15-0.3 | < 0.15 (uncertain)
and rescales the band around p50:  p10' = p50 - k (p50 - p10),  p90' = p50 + k (p90 - p50).
p50, the probabilities and the row order are unchanged.

Factors are fitted on VALIDATION rows only (AGENTS.md rule 4) with the organiser's pinball loss.
The held-out check refits them on four validation weeks and scores the fifth, so the reported gain
is out of sample. The final factors (all validation) are applied to the test submission.

    uv run python -m tools.eval.band_width --model ens_mix_spk            # held-out check + fit
    uv run python -m tools.eval.band_width --model ens_mix_spk --apply    # + <model>_bw_test.csv, validated
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

import numpy as np
import pandas as pd

from tools.eval.calibrate import PKG, WORK, score

GRID = np.round(np.arange(0.5, 1.81, 0.05), 2)
BLOCKS = ((1, 8), (9, 40))
CERT = (0.0, 0.15, 0.3, 1.0)


def cells(df: pd.DataFrame) -> pd.Series:
    c = (df["p_up"] - 0.5).abs()
    cert = np.digitize(c, CERT[1:-1])                      # 0 uncertain, 1 medium, 2 clear
    blk = np.where(df["step"] <= BLOCKS[0][1], 0, 1)
    return pd.Series(blk * 3 + cert, index=df.index)


def _pin(y, p50, p10, p90, k):
    return (score.pinball(y, p50 - k * (p50 - p10), 0.1) + score.pinball(y, p50 + k * (p90 - p50), 0.9)) / 2


def fit(df: pd.DataFrame) -> dict[int, float]:
    c, out = cells(df), {}
    for cell in range(6):
        d = df[c == cell]
        if len(d) < 200:
            out[cell] = 1.0
            continue
        losses = {k: _pin(d["imbalance_price"], d["p50"], d["p10"], d["p90"], k) for k in GRID}
        out[cell] = float(min(losses, key=losses.get))
    return out


def apply(df: pd.DataFrame, factors: dict[int, float]) -> pd.DataFrame:
    out = df.copy()
    k = cells(df).map(lambda c: factors[int(c)]).to_numpy(float)
    out["p10"] = df["p50"] - k * (df["p50"] - df["p10"])
    out["p90"] = df["p50"] + k * (df["p90"] - df["p50"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="exported model, e.g. ens_mix_spk (reads <model>-val_val.csv)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sub = score.load_submission(WORK / "submissions" / f"{a.model}-val_val.csv")
    df = sub.merge(score.load_actuals(PKG / "data" / "actuals_validation.csv"), on="delivery_start_utc", how="left")
    d = df[df["imbalance_price"].notna()].copy()
    week = d["forecast_origin_utc"].dt.isocalendar().week.astype(int)
    held = pd.concat([apply(d[week == w], fit(d[week != w])) for w in sorted(week.unique())]).sort_index()
    raw, cv = score.compute_metrics(df, 50.0), score.compute_metrics(held, 50.0)
    print(f"{a.model}: per-cell band width, leave-one-validation-week-out (diagnostic)")
    for k in ("calibration_pinball_mean", "coverage_p10_p90"):
        print(f"  {k:26s} raw {raw[k]:.4f}  held-out {cv[k]:.4f}")
    factors = fit(d)
    names = [f"{'0-2h' if c < 3 else '2-10h'}/{['uncertain', 'medium', 'clear'][c % 3]}" for c in range(6)]
    print("  final factors:", {n: factors[c] for c, n in enumerate(names)})
    print("  rows per cell:", cells(d).value_counts().sort_index().to_dict())
    (WORK / "calibration").mkdir(parents=True, exist_ok=True)
    (WORK / "calibration" / f"{a.model}_bw.json").write_text(json.dumps(factors, indent=2))

    # held-out validation version for score.py
    val = pd.read_csv(WORK / "submissions" / f"{a.model}-val_val.csv", dtype=str, keep_default_na=False)
    for c in ("p10", "p90"):
        val.loc[held.index, c] = held[c].map(lambda v: f"{v:.6f}")
    val.to_csv(WORK / "submissions" / f"{a.model}_bw-val_val.csv", index=False, encoding="utf-8", lineterminator="\n")

    if a.apply:
        t = pd.read_csv(WORK / "submissions" / f"{a.model}_test.csv", dtype=str, keep_default_na=False)
        num = t[["step", "p10", "p50", "p90", "p_up"]].astype(float)
        cal = apply(num, factors)
        for c in ("p10", "p90"):
            t[c] = cal[c].map(lambda v: f"{v:.6f}")
        path = WORK / "submissions" / f"{a.model}_bw_test.csv"
        t.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        print(f"wrote {path}")
        r = subprocess.run([sys.executable, str(PKG / "validate_submission.py"), "--backtest", str(path),
                            "--origins", str(PKG / "forecast_origins.csv")])
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()

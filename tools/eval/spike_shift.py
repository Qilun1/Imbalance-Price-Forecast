"""Spike-only recalibration: one logit shift per spike class, p' = sigmoid(logit(p) + b).

Why only spikes: the base models under-predict spikes on validation in every full week (about 8-9 %
predicted vs 12-13 % observed: training is mostly summer, autumn is spikier). Recalibrating band width
or direction did not help on held-out days (tools/eval/calibrate.py), so those are left untouched.
One parameter per class keeps the ranking of the model and cannot overfit the shape.

The shift is fitted on VALIDATION rows only (AGENTS.md rule 4: never on the test period).

    # held-out check (leave one validation week out) and fit on all validation:
    uv run python -m tools.eval.spike_shift --model ens_v4s_v4ms
    # (also writes <model>_spk-val_val.csv, the held-out validation version, for score.py)
    # apply the fitted shift to the test submission and run the organiser's validator:
    uv run python -m tools.eval.spike_shift --model ens_v4s_v4ms --apply
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

import numpy as np
import pandas as pd

from tools.eval.calibrate import PKG, WORK, logit, score

MARGIN = 50.0
CLASSES = (("p_spike_high", "hi"), ("p_spike_low", "lo"))


def _fit_one(p, y, iters: int = 50) -> float:
    """Maximum-likelihood intercept b with the model's logit as a fixed offset (Newton steps)."""
    z, y, b = logit(np.asarray(p, float)), np.asarray(y, float), 0.0
    for _ in range(iters):
        q = 1 / (1 + np.exp(-(z + b)))
        b -= (q - y).sum() / max((q * (1 - q)).sum(), 1e-12)
    return float(b)


def fit_shift(p_high, y_high, p_low, y_low) -> dict:
    return {"p_spike_high": _fit_one(p_high, y_high), "p_spike_low": _fit_one(p_low, y_low)}


def apply_shift(df: pd.DataFrame, shift: dict) -> pd.DataFrame:
    out = df.copy()
    hi = 1 / (1 + np.exp(-(logit(df["p_spike_high"].to_numpy(float)) + shift["p_spike_high"])))
    lo = 1 / (1 + np.exp(-(logit(df["p_spike_low"].to_numpy(float)) + shift["p_spike_low"])))
    sc = np.where(hi + lo > 0.999, 0.999 / np.maximum(hi + lo, 1e-12), 1.0)   # same cap as the model
    out["p_spike_high"], out["p_spike_low"] = np.clip(hi * sc, 0, 1), np.clip(lo * sc, 0, 1)
    return out


def _labelled(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["imbalance_price"].notna() & df["spot_price"].notna()].copy()
    d["hi"] = (d["imbalance_price"] > d["spot_price"] + MARGIN).astype(int)
    d["lo"] = (d["imbalance_price"] < d["spot_price"] - MARGIN).astype(int)
    return d


def _fit(d: pd.DataFrame) -> dict:
    return fit_shift(d["p_spike_high"], d["hi"], d["p_spike_low"], d["lo"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="name of an exported ensemble/model, e.g. ens_v4s_v4ms")
    ap.add_argument("--apply", action="store_true", help="write <model>_spk_test.csv and validate it")
    a = ap.parse_args()

    sub = score.load_submission(WORK / "submissions" / f"{a.model}-val_val.csv")
    df = sub.merge(score.load_actuals(PKG / "data" / "actuals_validation.csv"), on="delivery_start_utc", how="left")
    d = _labelled(df)
    week = d["forecast_origin_utc"].dt.isocalendar().week.astype(int)
    held = []
    for w in sorted(week.unique()):
        held.append(apply_shift(d[week == w], _fit(d[week != w])))
    held = pd.concat(held).sort_index()
    # honest validation version of the submission: every week shifted by a fit on the other weeks
    # (rows without actuals keep their raw value; they are not scored)
    val = pd.read_csv(WORK / "submissions" / f"{a.model}-val_val.csv", dtype=str, keep_default_na=False)
    assert len(val) == len(df)
    for c in ("p_spike_high", "p_spike_low"):
        val.loc[held.index, c] = held[c].map(lambda v: f"{v:.6f}")
    val.to_csv(WORK / "submissions" / f"{a.model}_spk-val_val.csv", index=False, encoding="utf-8", lineterminator="\n")
    raw, cv = score.compute_metrics(d, MARGIN), score.compute_metrics(held, MARGIN)
    print(f"{a.model}: spike shift, leave-one-validation-week-out ({week.nunique()} weeks; diagnostic)")
    for k in ("brier_spike_high", "brier_spike_low", "brier_spike_mean"):
        print(f"  {k:18s} raw {raw[k]:.4f}  held-out {cv[k]:.4f}  ({100 * (cv[k] / raw[k] - 1):+.2f} %)")
    shift = _fit(d)
    print(f"  final shift (all validation): {json.dumps({k: round(v, 4) for k, v in shift.items()})}")
    out_dir = WORK / "calibration"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{a.model}_spk.json").write_text(json.dumps(shift, indent=2))

    if a.apply:
        src = WORK / "submissions" / f"{a.model}_test.csv"
        t = pd.read_csv(src, dtype=str, keep_default_na=False)
        num = t[["p_spike_high", "p_spike_low"]].astype(float)
        cal = apply_shift(num, shift)
        for c in ("p_spike_high", "p_spike_low"):
            t[c] = cal[c].map(lambda v: f"{v:.6f}")
        path = WORK / "submissions" / f"{a.model}_spk_test.csv"
        t.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        print(f"wrote {path}: mean p_spike_high {num['p_spike_high'].mean():.4f} -> {cal['p_spike_high'].mean():.4f}, "
              f"p_spike_low {num['p_spike_low'].mean():.4f} -> {cal['p_spike_low'].mean():.4f}")
        r = subprocess.run([sys.executable, str(PKG / "validate_submission.py"), "--backtest", str(path),
                            "--origins", str(PKG / "forecast_origins.csv")])
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()

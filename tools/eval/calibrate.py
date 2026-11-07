"""Post-hoc calibration on VALIDATION predictions only (never the test period):
- band widths: separate scale factors for the lower (p10) and upper (p90) half-widths around p50;
- direction: Platt scaling of p_up on the logit scale (p_none kept);
- spikes: Platt scaling of p_spike_high and p_spike_low.

Honest gain estimate by cross-fitting: fit on one half of the validation days, score on the other,
both ways, metrics from the organiser's score.py (imported unchanged). Final parameters are fitted on
all validation rows and written to static_data/work/calibration/<model>.json.

    uv run python -m tools.eval.calibrate --model lgbm_v2s-val
"""
from __future__ import annotations

import argparse
import importlib.util
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from imbalance.paths import REPO_ROOT

PKG = REPO_ROOT / "tools" / "starter_package"
WORK = REPO_ROOT / "static_data" / "work"
_spec = importlib.util.spec_from_file_location("organiser_score", PKG / "score.py")
score = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(score)
GRID = np.round(np.arange(0.5, 2.01, 0.05), 2)
EPS = 1e-4


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def platt_fit(p, y):
    if y.nunique() < 2:
        return (1.0, 0.0)
    m = LogisticRegression(C=1e4).fit(logit(p).reshape(-1, 1), y)
    return (float(m.coef_[0, 0]), float(m.intercept_[0]))


def platt_apply(p, ab):
    return 1 / (1 + np.exp(-(ab[0] * logit(p) + ab[1])))


def fit(df: pd.DataFrame) -> dict:
    y = df["imbalance_price"]
    ok = y.notna()
    best = {}
    for col, q in (("p10", 0.10), ("p90", 0.90)):
        losses = {k: score.pinball(y[ok], df.loc[ok, "p50"] + k * (df.loc[ok, col] - df.loc[ok, "p50"]), q) for k in GRID}
        best[f"k_{col}"] = float(min(losses, key=losses.get))
    d = df[df["direction"].notna()]
    rel = d["p_up"] / (1 - d["p_none"])
    best["up"] = platt_fit(rel.to_numpy(), (d["direction"] == "up").astype(int))
    s = df[df["imbalance_price"].notna() & df["spot_price"].notna()]
    best["spike_high"] = platt_fit(s["p_spike_high"].to_numpy(), (s["imbalance_price"] > s["spot_price"] + 50).astype(int))
    best["spike_low"] = platt_fit(s["p_spike_low"].to_numpy(), (s["imbalance_price"] < s["spot_price"] - 50).astype(int))
    return best


def apply(df: pd.DataFrame, c: dict) -> pd.DataFrame:
    out = df.copy()
    out["p10"] = df["p50"] + c["k_p10"] * (df["p10"] - df["p50"])
    out["p90"] = df["p50"] + c["k_p90"] * (df["p90"] - df["p50"])
    rel = platt_apply((df["p_up"] / (1 - df["p_none"])).to_numpy(), c["up"])
    out["p_up"] = (1 - df["p_none"]) * rel
    out["p_down"] = 1 - out["p_up"] - out["p_none"]
    hi, lo = platt_apply(df["p_spike_high"].to_numpy(), c["spike_high"]), platt_apply(df["p_spike_low"].to_numpy(), c["spike_low"])
    sc = np.where(hi + lo > 0.999, 0.999 / np.maximum(hi + lo, 1e-12), 1.0)
    out["p_spike_high"], out["p_spike_low"] = hi * sc, lo * sc
    return out


KEYS = ["mae_p50", "calibration_pinball_mean", "coverage_p10_p90", "brier_spike_mean", "brier_direction"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    a = ap.parse_args()
    sub = score.load_submission(WORK / "submissions" / f"{a.model}_val.csv")
    act = score.load_actuals(PKG / "data" / "actuals_validation.csv")
    df = sub.merge(act, on="delivery_start_utc", how="left")
    day = df["forecast_origin_utc"].dt.floor("D")
    days = np.sort(day.unique())
    half = day.isin(days[: len(days) // 2])
    cross = pd.concat([apply(df[~half], fit(df[half])), apply(df[half], fit(df[~half]))]).sort_index()
    raw, cal = score.compute_metrics(df, 50.0), score.compute_metrics(cross, 50.0)
    print(f"{a.model}: cross-fitted on validation halves (diagnostic; official numbers come from score.py runs)")
    print(f"{'metric':26s} {'raw':>9s} {'calibrated':>11s} {'change':>8s}")
    for k in KEYS:
        print(f"{k:26s} {raw[k]:9.4f} {cal[k]:11.4f} {100 * (cal[k] / raw[k] - 1):+7.2f}%")
    final = fit(df)
    print("final parameters (all validation):", json.dumps(final))
    out = WORK / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.model}.json").write_text(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()

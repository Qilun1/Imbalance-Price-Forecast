"""Diagnostic: does a validation-fitted spike shift transfer to a model trained on more recent data?

The submission recipe is: fit a logit shift for p_spike_high / p_spike_low on the validation errors
of the "-val" models (trained up to 6 Sep), then apply it to the final models (trained up to 4 Oct)
on the test period. Those are different models, so the validation gain alone does not prove the
recipe. This tool replays the same recipe one period earlier, using training data only:

  early model : spike classifiers trained on targets usable before ORIGIN_EARLY (9 Aug)
  period B    : origins 9 Aug - 6 Sep  -> fit the shift on the early model's errors
  period C    : validation, 7 Sep - 4 Oct -> apply that shift to the existing "-val" ensemble

and scores period C with the organiser's score.py: raw vs transferred shift vs a shift fitted on
period C itself (an optimistic upper bound). Labels are y_spread (imbalance - spot), the scorer's
spike definition. Diagnostic only; nothing is written except the printed table.

    uv run python -m tools.eval.spike_shift_backtest --members lgbm_v4s lgbm_v4ms --name ens_v4s_v4ms
"""
from __future__ import annotations

import argparse

import lightgbm as lgb
import numpy as np
import pandas as pd
import yaml

from imbalance.contract import SPIKE_MARGIN, VALIDATION_FIRST_ORIGIN
from imbalance.model import DEFAULT_CLF
from imbalance.paths import REPO_ROOT

from tools.eval.calibrate import PKG, WORK, score
from tools.eval.spike_shift import apply_shift, fit_shift
from tools.training.feature_table import load_feature_table

ORIGIN_EARLY = pd.Timestamp("2026-08-09T21:00:00Z")    # four weeks before the first validation origin
CONFIGS = REPO_ROOT / "tools" / "training" / "configs"


def early_spike_probs(member: str) -> pd.DataFrame:
    cfg = yaml.safe_load((CONFIGS / f"{member}.yaml").read_text())
    from imbalance.features import feature_columns
    t = load_feature_table(cfg.get("feature_set", "v1")).dropna(subset=["y_spread", "y_dir"])
    cols = cfg.get("features") or feature_columns(t)
    train = t[t["y_target_fu"] <= ORIGIN_EARLY]
    assert train["forecast_origin_utc"].max() <= ORIGIN_EARLY
    period_b = t[(t["forecast_origin_utc"] >= ORIGIN_EARLY) & (t["forecast_origin_utc"] < VALIDATION_FIRST_ORIGIN)]
    clf = {**DEFAULT_CLF, **cfg.get("classifier", {})}
    out = period_b[["forecast_origin_utc", "delivery_start_utc", "y_spread"]].copy()
    for key, y in (("p_spike_high", train["y_spread"] > SPIKE_MARGIN), ("p_spike_low", train["y_spread"] < -SPIKE_MARGIN)):
        out[key] = lgb.LGBMClassifier(**clf).fit(train[cols], y.astype(int)).booster_.predict(period_b[cols])
    print(f"{member}: early model {len(train):,} rows (last origin {train['forecast_origin_utc'].max()}), "
          f"period B {len(period_b):,} rows")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", nargs="+", required=True)
    ap.add_argument("--name", required=True, help="ensemble whose <name>-val_val.csv is period C")
    a = ap.parse_args()

    frames = [early_spike_probs(m) for m in a.members]
    b = frames[0][["forecast_origin_utc", "delivery_start_utc", "y_spread"]].copy()
    for c in ("p_spike_high", "p_spike_low"):
        b[c] = sum(f[c].to_numpy() for f in frames) / len(frames)
    b["hi"], b["lo"] = (b["y_spread"] > SPIKE_MARGIN).astype(int), (b["y_spread"] < -SPIKE_MARGIN).astype(int)
    shift_b = fit_shift(b["p_spike_high"], b["hi"], b["p_spike_low"], b["lo"])

    sub = score.load_submission(WORK / "submissions" / f"{a.name}-val_val.csv")
    df = sub.merge(score.load_actuals(PKG / "data" / "actuals_validation.csv"), on="delivery_start_utc", how="left")
    ok = df["imbalance_price"].notna() & df["spot_price"].notna()
    hi_c = (df.loc[ok, "imbalance_price"] > df.loc[ok, "spot_price"] + SPIKE_MARGIN).astype(int)
    lo_c = (df.loc[ok, "imbalance_price"] < df.loc[ok, "spot_price"] - SPIKE_MARGIN).astype(int)
    shift_c = fit_shift(df.loc[ok, "p_spike_high"], hi_c, df.loc[ok, "p_spike_low"], lo_c)

    print(f"\nperiod B: predicted high/low {b['p_spike_high'].mean():.3f}/{b['p_spike_low'].mean():.3f}, "
          f"observed {b['hi'].mean():.3f}/{b['lo'].mean():.3f}")
    print(f"shift fitted on B (transferred): {shift_b}")
    print(f"shift fitted on C (upper bound): {shift_c}\n")
    rows = {"raw": df, "shift from B": apply_shift(df, shift_b), "shift from C (in-sample)": apply_shift(df, shift_c)}
    print(f"{'period C (validation)':26s} {'brier_spike_mean':>17s} {'brier_high':>11s} {'brier_low':>10s}")
    for k, d in rows.items():
        m = score.compute_metrics(d, 50.0)
        print(f"{k:26s} {m['brier_spike_mean']:17.4f} {m['brier_spike_high']:11.4f} {m['brier_spike_low']:10.4f}")


if __name__ == "__main__":
    main()

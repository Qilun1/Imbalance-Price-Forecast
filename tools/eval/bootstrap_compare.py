"""Day-block bootstrap of the organiser's metrics for two validation submissions (diagnostic only).

Resamples validation days with replacement and recomputes MAE, mean pinball of p10/p90, mean spike
Brier and direction Brier with the organiser's definitions (score.py imported unchanged), reporting
the share of resamples in which model B beats model A on each metric.

    uv run python -m tools.eval.bootstrap_compare --a ens_mixg_spk_bw --b ens_bag8_bw --n 300
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from tools.eval.calibrate import PKG, WORK, score

MARGIN = 50.0


def metrics(df: pd.DataFrame) -> dict:
    y, spot = df["imbalance_price"].to_numpy(float), df["spot_price"].to_numpy(float)
    mae = np.mean(np.abs(df["p50"].to_numpy(float) - y))
    pin = np.mean([score.pinball(pd.Series(y), pd.Series(df[c].to_numpy(float)), q) for c, q in (("p10", 0.1), ("p90", 0.9))])
    hi, lo = (y > spot + MARGIN).astype(float), (y < spot - MARGIN).astype(float)
    spike = np.mean([np.mean((df["p_spike_high"].to_numpy(float) - hi) ** 2), np.mean((df["p_spike_low"].to_numpy(float) - lo) ** 2)])
    d = df["direction"].astype(str)
    oh = np.column_stack([(d == "up"), (d == "down"), (d == "none")]).astype(float)
    p = df[["p_up", "p_down", "p_none"]].to_numpy(float)
    brier_dir = np.mean(((p - oh) ** 2).sum(axis=1))
    return {"mae": mae, "pinball": pin, "spike": spike, "direction": brier_dir}


def load(name: str, actuals: pd.DataFrame) -> pd.DataFrame:
    sub = pd.read_csv(WORK / "submissions" / f"{name}-val_val.csv")
    m = sub.merge(actuals, on="delivery_start_utc", how="inner")
    return m[m["imbalance_price"].notna() & m["spot_price"].notna()].reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--n", type=int, default=300)
    a = ap.parse_args()
    act = pd.read_csv(PKG / "data" / "actuals_validation.csv")
    A, B = load(a.a, act), load(a.b, act)
    assert A[["forecast_origin_utc", "step"]].equals(B[["forecast_origin_utc", "step"]])
    print("full:", {k: f"{v:.4f}" for k, v in metrics(A).items()}, "->", {k: f"{v:.4f}" for k, v in metrics(B).items()})
    days = pd.to_datetime(A["delivery_start_utc"]).dt.floor("D")
    codes, uniq = pd.factorize(days)
    idx_by_day = [np.flatnonzero(codes == i) for i in range(len(uniq))]
    rng = np.random.default_rng(0)
    wins = {k: 0 for k in ("mae", "pinball", "spike", "direction")}
    for _ in range(a.n):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        idx = np.concatenate([idx_by_day[i] for i in pick])
        ma, mb = metrics(A.iloc[idx]), metrics(B.iloc[idx])
        for k in wins:
            wins[k] += mb[k] < ma[k]
    print(f"share of {a.n} day-block resamples ({len(uniq)} days) where {a.b} beats {a.a}:",
          {k: f"{v / a.n:.0%}" for k, v in wins.items()})


if __name__ == "__main__":
    main()

"""Independent leakage check for the event classifiers' inputs.

For random origins o, rebuild every input from scratch using only data usable at o:
  - feature rows of o (and of o - 1 h, for the revision inputs), from observations and weather runs
    that physically exclude every row not usable by then (leakage.rebuild);
  - base and challenger forecasts from the segment model trained only on targets published by the
    segment start, which is <= o (alert_train.segment_bundle, asserted);
then require the result to equal the cached training table the classifiers learn from.

    uv run python -m tools.eval.alert_leakage --n 20
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from imbalance import alert_features, store

from tools.eval.leakage import rebuild
from tools.training.alert_train import BASE, CHALLENGER, load_config, segment_bundle, segment_start, training_table

HOUR = pd.Timedelta(hours=1)


def check(n: int = 20, seed: int = 0) -> bool:
    table = training_table()
    cols: list[str] = []
    pool = pd.DatetimeIndex(table["forecast_origin_utc"].unique())
    pool = pool[pool > pool.min()]                     # the first origin has no earlier forecast
    rng = np.random.default_rng(seed)
    sample = pd.DatetimeIndex(sorted(rng.choice(pool, min(n, len(pool)), replace=False)))
    long = store.load_observations()
    bundles: dict[tuple[str, pd.Timestamp], object] = {}

    def forecast(name: str, o: pd.Timestamp) -> pd.DataFrame:
        start = segment_start(o)
        assert start <= o
        if (name, start) not in bundles:
            bundles[(name, start)] = segment_bundle(name, start)
        feats = rebuild(load_config(name)["feature_set"], long, o)
        pred = bundles[(name, start)].predict(feats)
        return pd.concat([feats[["forecast_origin_utc", "delivery_start_utc", "step"]], pred], axis=1), feats

    bad = 0
    for o in sample:
        cur, feats = forecast(BASE, o)
        prev, _ = forecast(BASE, o - HOUR)
        ch, _ = forecast(CHALLENGER, o)
        ref = alert_features.build(feats, pd.concat([prev, cur], ignore_index=True), ch, pd.DatetimeIndex([o]))
        used = table[table["forecast_origin_utc"] == o].sort_values("window_idx")
        ref = ref.sort_values("window_idx")
        cols = alert_features.input_columns(ref)          # every classifier input, nothing else
        assert len(used) == len(ref) == 3
        same = np.isclose(ref[cols].to_numpy(float), used[cols].to_numpy(float), equal_nan=True, rtol=0, atol=1e-9)
        if not same.all():
            bad += 1
            print("MISMATCH", o, [c for c, ok in zip(cols, same.all(0)) if not ok][:5])
    ok = bad == 0
    print(f"alert leakage check: {len(sample)} origins x 3 windows x {len(cols)} inputs -> "
          f"{'PASS' if ok else f'FAIL ({bad})'}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    raise SystemExit(0 if check(ap.parse_args().n, ap.parse_args().seed) else 1)


if __name__ == "__main__":
    main()

"""Independent leakage check.

For random origins, rebuild every feature from data that physically excludes all rows with
first_usable_origin_utc > origin (the organiser's rule applied literally), and require the result to
equal the cached feature table the models use.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from imbalance import store
from imbalance.features import Store, build, feature_columns

from tools.training.feature_table import load_feature_table


def check(feature_set: str = "v1", n: int = 60, seed: int = 0, origins: pd.DatetimeIndex | None = None) -> bool:
    table = load_feature_table(feature_set)
    long = store.load_observations()
    pool = pd.DatetimeIndex(table["forecast_origin_utc"].unique()) if origins is None else origins
    rng = np.random.default_rng(seed)
    sample = pd.DatetimeIndex(sorted(rng.choice(pool, min(n, len(pool)), replace=False)))
    cols = feature_columns(table)
    bad = 0
    for o in sample:
        visible = long[long["first_usable_origin_utc"] <= o]
        nwp_tables = None
        if feature_set != "v1":
            from imbalance import nwp
            nwp_tables = nwp.load_for(feature_set, visible_before=o)          # runs not yet usable are physically removed
        ref = build(Store(visible), pd.DatetimeIndex([o]), with_targets=False, nwp=nwp_tables)
        used = table[table["forecast_origin_utc"] == o].sort_values("step")
        same = np.isclose(ref[cols].to_numpy(float), used[cols].to_numpy(float), equal_nan=True, rtol=0, atol=1e-9)
        if not same.all():
            bad += 1
            print("MISMATCH", o, [c for c, ok in zip(cols, same.all(0)) if not ok][:5])
    ok = bad == 0
    print(f"leakage check: {len(sample)} origins x 40 steps x {len(cols)} features -> {'PASS' if ok else f'FAIL ({bad})'}")
    return ok

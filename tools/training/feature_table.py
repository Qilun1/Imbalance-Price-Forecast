"""Build or load the cached feature table static_data/processed/features_<set>.parquet."""
from __future__ import annotations

import pandas as pd

from imbalance.features import FEATURE_SET, FEATURE_SETS, build_table
from imbalance.paths import PROCESSED_DIR


def path_for(feature_set: str):
    return PROCESSED_DIR / f"features_{feature_set}.parquet"


def build_feature_table(feature_set: str = FEATURE_SET) -> pd.DataFrame:
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"unknown feature set {feature_set!r} (available: {FEATURE_SETS})")
    df = build_table(with_targets=True, feature_set=feature_set)
    p = path_for(feature_set)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    print(f"features {feature_set}: {len(df)} rows, {df['forecast_origin_utc'].nunique()} origins -> {p}")
    return df


def load_feature_table(feature_set: str = FEATURE_SET) -> pd.DataFrame:
    p = path_for(feature_set)
    return pd.read_parquet(p) if p.exists() else build_feature_table(feature_set)

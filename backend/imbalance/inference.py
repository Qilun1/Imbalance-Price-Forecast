"""Run a trained model for a set of forecast origins and store the result in infer_data."""
from __future__ import annotations

import pandas as pd

from . import forecasts
from .features import build_table
from .model import Bundle


def infer(model_name: str, origins: pd.DatetimeIndex, features: pd.DataFrame | None = None) -> pd.DataFrame:
    """Forecast rows (submission columns) for every origin; also written to infer_data."""
    bundle = Bundle.load(model_name)
    if features is None:
        features = build_table(origins, with_targets=False, feature_set=bundle.meta.get("feature_set", "v1"))
    feats = features[features["forecast_origin_utc"].isin(origins)].reset_index(drop=True)
    missing = set(pd.DatetimeIndex(origins)) - set(feats["forecast_origin_utc"])
    if missing:
        raise RuntimeError(f"no feature rows for {len(missing)} origins, e.g. {sorted(missing)[0]}")
    pred = bundle.predict(feats)
    out = pd.concat([feats[["forecast_origin_utc", "delivery_start_utc", "step", "data_cutoff_utc"]], pred], axis=1)
    forecasts.write(model_name, out)
    return out

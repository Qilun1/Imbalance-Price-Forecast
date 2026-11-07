"""Inputs of the event classifiers: one row per (forecast origin, window).

Everything here is derived from two things that are already availability-safe at the origin:
1. the feature table (features.build, availability-masked, checked by tools/eval/leakage.py), and
2. base forecasts made AT the origin (or at the origin one hour earlier, for the revision inputs), by a
   model trained only on targets published by then (for training rows, see alert_train.oof_forecasts).

No raw store values are read here. Window aggregates only summarise rows already in those two tables.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .events import WINDOWS
from .features import feature_columns

FORECAST_COLS = ["p10", "p50", "p90", "p_up", "p_spike_high", "p_spike_low"]
# Delivery-level inputs whose shape within a window matters (max and min as well as the mean).
SHAPE_COLS = ["spot", "spot_ramp", "spot_vs_horizon_mean", "spot_vs_last_known_spot", "wind_fc", "wind_fc_ramp",
              "wind_fc_change_vs_lag", "resid_load_fc", "cons_fc_vs_last_cons", "solar_fc"]
KEYS = ["forecast_origin_utc", "window"]
HOUR = pd.Timedelta(hours=1)


def window_of_step(step: pd.Series) -> pd.Series:
    out = pd.Series(index=step.index, dtype=object)
    for name, (a, b) in WINDOWS.items():
        out[(step >= a) & (step <= b)] = name
    return out


def _union(p: pd.Series) -> float:
    """P(at least one) if quarters were independent: the naive rule baseline (b) in the plan."""
    return float(1 - np.exp(np.log1p(-np.clip(p.to_numpy(float), 0, 0.999999)).sum()))


def _forecast_inputs(base: pd.DataFrame, challenger: pd.DataFrame | None) -> pd.DataFrame:
    """Per (origin, step) forecast columns, the revision since the origin one hour earlier, and the gap to
    the challenger model. `base` must also hold the previous origin's rows for the revision inputs."""
    cur = base[["forecast_origin_utc", "delivery_start_utc", "step", *FORECAST_COLS]].copy()
    prev = base[["forecast_origin_utc", "delivery_start_utc", "p50", "p_up", "p_spike_high", "p_spike_low"]].copy()
    prev["forecast_origin_utc"] = prev["forecast_origin_utc"] + HOUR      # made one hour before the origin
    cur = cur.merge(prev, on=["forecast_origin_utc", "delivery_start_utc"], how="left", suffixes=("", "_prev"))
    if challenger is not None:
        ch = challenger[["forecast_origin_utc", "delivery_start_utc", "p50", "p_up", "p_spike_high", "p_spike_low"]]
        cur = cur.merge(ch, on=["forecast_origin_utc", "delivery_start_utc"], how="left", suffixes=("", "_ch"))
    else:
        for c in ("p50", "p_up", "p_spike_high", "p_spike_low"):
            cur[f"{c}_ch"] = np.nan
    cur["width"] = cur["p90"] - cur["p10"]
    for c in ("p50", "p_up", "p_spike_high", "p_spike_low"):
        cur[f"rev_{c}"] = cur[c] - cur[f"{c}_prev"]
        cur[f"gap_{c}"] = (cur[c] - cur[f"{c}_ch"]).abs()
    return cur


def build(features: pd.DataFrame, base: pd.DataFrame, challenger: pd.DataFrame | None = None,
          origins: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """(origin, window) rows for `origins` (default: every origin in `base` that has feature rows)."""
    if origins is None:
        origins = pd.DatetimeIndex(base["forecast_origin_utc"].unique())
    origins = pd.DatetimeIndex(origins)
    fc = _forecast_inputs(base, challenger)
    fc = fc[fc["forecast_origin_utc"].isin(origins)]
    ft = features[features["forecast_origin_utc"].isin(origins)]
    cols = [c for c in feature_columns(ft) if c != "step"]
    rows = ft[["forecast_origin_utc", "step", *cols]].merge(
        fc.drop(columns="delivery_start_utc"), on=["forecast_origin_utc", "step"], how="inner")
    rows["window"] = window_of_step(rows["step"])
    rows["spread_fc"] = rows["p50"] - rows["spot"]
    g = rows.groupby(KEYS, sort=False)

    shape = [c for c in SHAPE_COLS if c in cols]
    parts = [
        g[cols].mean().add_prefix("f_"),
        g[shape].max().add_prefix("fmax_"),
        g[shape].min().add_prefix("fmin_"),
        g[["p50", "spread_fc", "p_up"]].agg(["mean", "max", "min"]).set_axis(
            [f"b_{c}_{s}" for c in ("p50", "spread_fc", "p_up") for s in ("mean", "max", "min")], axis=1),
        g[["p90", "p_spike_high", "p_spike_low", "width"]].max().add_prefix("b_max_"),
        g[["p10"]].min().add_prefix("b_min_"),
        g["p_spike_high"].agg(_union).rename("b_union_spike_high").to_frame(),
        g["p_spike_low"].agg(_union).rename("b_union_spike_low").to_frame(),
        g[["rev_p50", "rev_p_up", "rev_p_spike_high", "rev_p_spike_low"]].mean().add_suffix("_mean"),
        g[["rev_p50", "rev_p_spike_high", "rev_p_spike_low"]].max().add_suffix("_max"),
        g[["rev_p50"]].min().add_suffix("_min"),
        g[["gap_p50", "gap_p_up", "gap_p_spike_high", "gap_p_spike_low"]].max().add_suffix("_max"),
    ]
    out = pd.concat(parts, axis=1).reset_index()
    order = {name: i for i, name in enumerate(WINDOWS)}
    out["window_idx"] = out["window"].map(order).astype(float)
    hour = pd.DatetimeIndex(out["forecast_origin_utc"]).tz_convert("Europe/Helsinki")
    out["origin_hour_local"] = hour.hour.astype(float)
    out["origin_weekday"] = hour.day_of_week.astype(float)
    return out.sort_values(["forecast_origin_utc", "window_idx"]).reset_index(drop=True)


def input_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in KEYS]

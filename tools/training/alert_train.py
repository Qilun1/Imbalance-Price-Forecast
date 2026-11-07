"""Training data for the event classifiers (docs/plans/event_notes.md).

Out-of-sample base forecasts: the classifiers read the base model's forecast as an input, so on
training rows that forecast must come from a model that had not seen those targets. As in
hist_heads.py, an expanding window is used: the origins of each segment are forecast by a base
model trained only on targets published by the segment's first origin (y_target_fu <= start).
The last training segment (validation, from 6 Sep 21:00 UTC) is forecast exactly as the "-val"
models are. Test origins are not forecast here; at inference the saved final models are used.

Rows are written to static_data/processed/ (gitignored, AGENTS.md rule 0).

    uv run python -m tools.training.alert_train --build      # OOF forecasts + training table + rates
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from imbalance import alert_features, events
from imbalance.contract import HORIZON_STEPS, TEST_FIRST_ORIGIN, TRAIN_END_DELIVERY, VALIDATION_FIRST_ORIGIN
from imbalance.features import load_store
from imbalance.model import Bundle
from imbalance.paths import CONFIGS_DIR, PROCESSED_DIR

from tools.training.feature_table import load_feature_table

BASE, CHALLENGER = "lgbm_v4s", "lgbm_v4ms"
SEGMENTS = [pd.Timestamp(t) for t in ["2026-06-30T21:00:00Z", "2026-07-31T21:00:00Z", "2026-08-31T21:00:00Z"]] + \
    [VALIDATION_FIRST_ORIGIN, TEST_FIRST_ORIGIN]
VAL_LAST_DELIVERY = VALIDATION_FIRST_ORIGIN - pd.Timedelta(minutes=15)     # labels for the -val variant
OOF_PATH = PROCESSED_DIR / "alert_oof_{name}.parquet"
TABLE_PATH = PROCESSED_DIR / "alert_table.parquet"


def load_config(config_name: str) -> dict:
    return yaml.safe_load((CONFIGS_DIR / f"{config_name}.yaml").read_text())


def segment_start(origin: pd.Timestamp) -> pd.Timestamp:
    """Start of the segment whose base model forecasts this origin."""
    starts = [s for s in SEGMENTS[:-1] if s <= origin]
    if not starts or origin >= SEGMENTS[-1]:
        raise ValueError(f"origin {origin} is outside the out-of-sample segments")
    return starts[-1]


def segment_bundle(config_name: str, start: pd.Timestamp, table: pd.DataFrame | None = None) -> Bundle:
    """Base model trained only on targets published by `start` (y_target_fu <= start)."""
    config = load_config(config_name)
    if table is None:
        table = load_feature_table(config["feature_set"])
    rows = table.dropna(subset=["y_spread", "y_dir"])
    rows = rows[rows["y_target_fu"] <= start]
    assert rows["delivery_start_utc"].max() <= TRAIN_END_DELIVERY
    assert rows["y_target_fu"].max() <= start
    return Bundle.train(f"{config_name}-oof", rows, config)


def oof_forecasts(config_name: str) -> pd.DataFrame:
    """Out-of-sample forecasts for every origin from SEGMENTS[0] up to the first test origin."""
    path = Path(str(OOF_PATH).format(name=config_name))
    if path.exists():
        return pd.read_parquet(path)
    table = load_feature_table(load_config(config_name)["feature_set"])
    frames = []
    for start, end in zip(SEGMENTS[:-1], SEGMENTS[1:]):
        bundle = segment_bundle(config_name, start, table)
        seg = table[(table["forecast_origin_utc"] >= start) & (table["forecast_origin_utc"] < end)].reset_index(drop=True)
        pred = bundle.predict(seg)
        out = pd.concat([seg[["forecast_origin_utc", "delivery_start_utc", "step"]], pred], axis=1)
        out["trained_until"] = start
        frames.append(out)
        print(f"{config_name}: trained on {bundle.meta['train_rows']:,} rows published by {start:%Y-%m-%d %H:%M}, "
              f"forecast {seg['forecast_origin_utc'].nunique()} origins")
    oof = pd.concat(frames, ignore_index=True)
    # Hard guard: no forecast from a model that saw targets published after the forecast's origin.
    assert (oof["trained_until"] <= oof["forecast_origin_utc"]).all()
    path.parent.mkdir(parents=True, exist_ok=True)
    oof.to_parquet(path, index=False)
    return oof


def p50_matrix(base: pd.DataFrame, origins: pd.DatetimeIndex) -> np.ndarray:
    wide = base.pivot(index="forecast_origin_utc", columns="step", values="p50")
    return wide.reindex(index=origins, columns=range(1, HORIZON_STEPS + 1)).to_numpy(float)


def training_table(rebuild: bool = False) -> pd.DataFrame:
    """Inputs and labels for every (origin, window) with origin in [SEGMENTS[0], first test origin).

    Labels use realised values up to the training cutoff only (TRAIN_END_DELIVERY); the -val variant
    later cuts again at VAL_LAST_DELIVERY (see label_cutoff)."""
    if TABLE_PATH.exists() and not rebuild:
        return pd.read_parquet(TABLE_PATH)
    base, challenger = oof_forecasts(BASE), oof_forecasts(CHALLENGER)
    feats = load_feature_table(load_config(BASE)["feature_set"])
    # The first origin has no forecast one hour earlier; keep it but its revision inputs are NaN.
    origins = pd.DatetimeIndex(sorted(base["forecast_origin_utc"].unique()))
    X = alert_features.build(feats, base, challenger, origins)
    store = load_store()
    p50 = p50_matrix(base, origins)
    lab_final = events.labels(store, origins, p50=p50, last_delivery=TRAIN_END_DELIVERY)
    lab_val = events.labels(store, origins, p50=p50, last_delivery=VAL_LAST_DELIVERY)
    lab_val = lab_val.rename(columns={e: f"{e}__val" for e in events.EVENT_IDS})
    table = X.merge(lab_final, on=["forecast_origin_utc", "window"]).merge(lab_val, on=["forecast_origin_utc", "window"])
    table.to_parquet(TABLE_PATH, index=False)
    print(f"alert table: {len(table):,} rows ({table['forecast_origin_utc'].nunique()} origins x "
          f"{table['window'].nunique()} windows), {len(alert_features.input_columns(X))} inputs -> {TABLE_PATH}")
    return table


def label_columns(variant: str) -> dict[str, str]:
    """Event id -> label column for a variant: "val" (labels up to 6 Sep) or "final" (up to 4 Oct)."""
    return {e: (f"{e}__val" if variant == "val" else e) for e in events.EVENT_IDS}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="(re)build OOF forecasts and the training table")
    a = ap.parse_args()
    table = training_table(rebuild=a.build)
    pd.set_option("display.width", 140)
    period = table["forecast_origin_utc"] < VALIDATION_FIRST_ORIGIN
    print("\nEvent rates on training rows before validation (labels up to 6 Sep), by window:")
    print(table[period].groupby("window", sort=False)[list(label_columns("val").values())].mean().T.round(3))


if __name__ == "__main__":
    main()

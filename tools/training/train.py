"""Train a model bundle from a YAML config.

mode "val"  : trains on target quarter-hours published before the first validation origin;
              saved as <name>-val. Use it to score the validation period honestly.
mode "final": trains on target quarter-hours up to 2026-10-04T20:45Z (training cutoff); saved as
              <name>. Use it for the test submission and the dashboard.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from imbalance.contract import TRAIN_END_DELIVERY, VALIDATION_FIRST_ORIGIN
from imbalance.model import Bundle

from tools.training.feature_table import load_feature_table


def train(config_path: Path, mode: str) -> Bundle:
    config = yaml.safe_load(Path(config_path).read_text())
    table = load_feature_table(config.get("feature_set", "v1"))
    labelled = table.dropna(subset=["y_spread", "y_dir"])
    if mode == "val":
        rows = labelled[labelled["y_target_fu"] <= VALIDATION_FIRST_ORIGIN]
        name = f"{config['name']}-val"
    elif mode == "final":
        rows = labelled[labelled["delivery_start_utc"] <= TRAIN_END_DELIVERY]
        name = config["name"]
    else:
        raise ValueError(mode)
    # hard guard: no training target after the training cutoff
    assert rows["delivery_start_utc"].max() <= TRAIN_END_DELIVERY
    assert rows["forecast_origin_utc"].max() <= TRAIN_END_DELIVERY
    print(f"training {name}: {len(rows)} rows, last target {rows['delivery_start_utc'].max()}")
    bundle = Bundle.train(name, rows, config)
    path = bundle.save()
    print(f"saved {path}")
    return bundle

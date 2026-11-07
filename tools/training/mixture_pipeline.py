"""Train, score and export a structural mixture model (backend/imbalance/mixture.py).

Same steps and cutoffs as `tools.cli pipeline`: validation version on targets usable before the first
validation origin, scored with the organiser's score.py; final version on targets up to the training
cutoff, exported through the template and validate_submission.py; leakage check of the feature set.

    uv run python -m tools.training.mixture_pipeline --config tools/training/configs/mix_v6.yaml
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from imbalance import forecasts
from imbalance.contract import TRAIN_END_DELIVERY, VALIDATION_FIRST_ORIGIN
from imbalance.mixture import MixBundle

from tools.cli import cmd_export, cmd_leakage, cmd_score, origins_for
from tools.training.feature_table import load_feature_table


def train(config: dict, table: pd.DataFrame, mode: str) -> MixBundle:
    labelled = table.dropna(subset=["y_spread", "y_dir"])
    if mode == "val":
        rows, name = labelled[labelled["y_target_fu"] <= VALIDATION_FIRST_ORIGIN], f"{config['name']}-val"
    else:
        rows, name = labelled[labelled["delivery_start_utc"] <= TRAIN_END_DELIVERY], config["name"]
    assert rows["delivery_start_utc"].max() <= TRAIN_END_DELIVERY
    assert rows["forecast_origin_utc"].max() <= TRAIN_END_DELIVERY
    print(f"training {name}: {len(rows):,} rows, last target {rows['delivery_start_utc'].max()}")
    b = MixBundle.train(name, rows, config)
    print(f"saved {b.save()}  rows per head {b.meta['rows_per_head']}")
    return b


def infer(b: MixBundle, table: pd.DataFrame, origins: pd.DatetimeIndex) -> None:
    feats = table[table["forecast_origin_utc"].isin(origins)].drop(
        columns=[c for c in table if c.startswith("y_")]).reset_index(drop=True)
    missing = set(origins) - set(feats["forecast_origin_utc"])
    if missing:
        raise RuntimeError(f"no feature rows for {len(missing)} origins")
    out = pd.concat([feats[["forecast_origin_utc", "delivery_start_utc", "step", "data_cutoff_utc"]],
                     b.predict(feats)], axis=1)
    forecasts.write(b.name, out)
    print(f"{b.name}: {out['forecast_origin_utc'].nunique()} origins -> infer_data")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--n", type=int, default=60, help="origins for the leakage check (0 = skip)")
    ap.add_argument("--val-only", action="store_true")
    ap.add_argument("--final-only", action="store_true", help="skip the validation version (already built)")
    a = ap.parse_args()
    config = yaml.safe_load(Path(a.config).read_text())
    fs = config.get("feature_set", "v1")
    table = load_feature_table(fs)
    if not a.final_only:
        b = train(config, table, "val")
        infer(b, table, origins_for("val"))
        cmd_score(argparse.Namespace(model=b.name))
    if a.val_only:
        return
    b = train(config, table, "final")
    infer(b, table, origins_for("all"))
    cmd_export(argparse.Namespace(model=b.name, period="test", out=None))
    if a.n:
        cmd_leakage(argparse.Namespace(set=fs, n=a.n))


if __name__ == "__main__":
    main()

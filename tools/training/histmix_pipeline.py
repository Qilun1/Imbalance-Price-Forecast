"""Mixture model + out-of-sample long-history tail heads (tools/training/hist_tails.py).

Joins static_data/processed/hist_tails.parquet onto the availability-masked feature table of the
config's feature set by (forecast_origin_utc, step), adds the spread versions of the history price
quantiles (history up-price quantile minus the delivery quarter-hour's spot, which is already a
feature), then trains / scores / exports exactly like tools/training/mixture_pipeline.py.

    uv run python -m tools.training.histmix_pipeline --config tools/training/configs/hmix_v4b.yaml --val-only
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from tools.cli import cmd_export, cmd_score, origins_for
from tools.training.feature_table import load_feature_table
from tools.training.hist_tails import OUT as HIST_TAILS
from tools.training.mixture_pipeline import infer, train


def joined_table(feature_set: str) -> pd.DataFrame:
    t = load_feature_table(feature_set)
    h = pd.read_parquet(HIST_TAILS)
    h["forecast_origin_utc"] = pd.to_datetime(h["forecast_origin_utc"], utc=True).dt.as_unit(
        t["forecast_origin_utc"].dt.unit)
    n = len(t)
    t = t.merge(h, on=["forecast_origin_utc", "step"], how="left", validate="one_to_one")
    assert len(t) == n
    t["hist_up_spread_q50"] = t["hist_up_px_q50"] - t["spot"]
    t["hist_up_spread_q90"] = t["hist_up_px_q90"] - t["spot"]
    print(f"joined history tails onto {feature_set}: {t['hist_p_tail200'].notna().mean():.1%} of rows covered")
    return t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--val-only", action="store_true")
    ap.add_argument("--final-only", action="store_true")
    a = ap.parse_args()
    config = yaml.safe_load(Path(a.config).read_text())
    table = joined_table(config.get("feature_set", "v1"))
    if not a.final_only:
        b = train(config, table, "val")
        infer(b, table, origins_for("val"))
        cmd_score(argparse.Namespace(model=b.name))
    if a.val_only:
        return
    b = train(config, table, "final")
    infer(b, table, origins_for("all"))
    cmd_export(argparse.Namespace(model=b.name, period="test", out=None))


if __name__ == "__main__":
    main()

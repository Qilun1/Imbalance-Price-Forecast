"""Bagging members of a structural mixture: same config, different seed / training window / target
transform. Trains the validation version, forecasts the validation origins, exports the submission
and scores it (organiser's score.py); or the final version and the test export. One member per run.

    uv run python -m tools.training.bag --config tools/training/configs/mix_v4b.yaml --member s1 --mode val
    uv run python -m tools.training.bag --config ... --member s2w --mode val
Members: s<k> = seed k; s<k>w = seed k and training window from --train-start; s<k>a = seed k and
asinh target. Member names are appended to the config name: mix_v4b_s1-val.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from imbalance import forecasts
from imbalance.contract import TRAIN_END_DELIVERY, VALIDATION_FIRST_ORIGIN
from imbalance.mixture import MixBundle
from imbalance.paths import WORK_DIR
from tools.cli import origins_for
from tools.eval.organiser import score, templates, validate
from tools.training.feature_table import load_feature_table


def member_config(config: dict, member: str, train_start: str, widen: float | None, widen_mode: str | None,
                  tail: str | None) -> dict:
    c = dict(config)
    c["name"] = f"{config['name']}_{member}"
    seed = int("".join(ch for ch in member if ch.isdigit()))
    c["seed"] = seed
    if member.endswith("w"):
        c["train_start"] = train_start
    if member.endswith("a"):
        c["target_transform"] = "asinh"
    if widen is not None:
        c["widen"] = widen
    if widen_mode:
        c["widen_mode"] = widen_mode
    if tail:
        c["tail"] = tail
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--member", required=True)
    ap.add_argument("--mode", choices=["val", "final"], default="val")
    ap.add_argument("--train-start", default="2026-07-20")
    ap.add_argument("--widen", type=float, default=None)
    ap.add_argument("--widen-mode", default=None)
    ap.add_argument("--tail", default=None)
    a = ap.parse_args()
    base = yaml.safe_load(Path(a.config).read_text())
    config = member_config(base, a.member, a.train_start, a.widen, a.widen_mode, a.tail)
    table = load_feature_table(config.get("feature_set", "v1"))
    labelled = table.dropna(subset=["y_spread", "y_dir"])
    if a.mode == "val":
        rows, name = labelled[labelled["y_target_fu"] <= VALIDATION_FIRST_ORIGIN], f"{config['name']}-val"
    else:
        rows, name = labelled[labelled["delivery_start_utc"] <= TRAIN_END_DELIVERY], config["name"]
    assert rows["delivery_start_utc"].max() <= TRAIN_END_DELIVERY
    b = MixBundle.train(name, rows, config)
    print(f"trained {name}: rows per head {b.meta['rows_per_head']} (window from {config.get('train_start')})")
    b.save()
    period = "val" if a.mode == "val" else "test"
    origins = origins_for(period)
    feats = table[table["forecast_origin_utc"].isin(origins)].drop(
        columns=[c for c in table if c.startswith("y_")]).reset_index(drop=True)
    out = pd.concat([feats[["forecast_origin_utc", "delivery_start_utc", "step", "data_cutoff_utc"]], b.predict(feats)], axis=1)
    tpl, ori = templates(period)
    sub = forecasts.export_submission(name, tpl, WORK_DIR / "submissions" / f"{name}_{period}.csv", frame=out)
    if period == "val":
        ok, rep = score(sub, WORK_DIR / "scores" / name, WORK_DIR / "scores" / "baseline-val" / "score_summary.csv")
        s = pd.read_csv(WORK_DIR / "scores" / name / "score_summary.csv").iloc[0]
        print(f"{name}: mae {s['mae_p50']:.3f} pinball {s['calibration_pinball_mean']:.3f} cov {s['coverage_p10_p90']:.3f} "
              f"spike {s['brier_spike_mean']:.4f} dir {s['brier_direction']:.4f}")
    else:
        ok, rep = validate(sub, ori)
        print(rep.strip().splitlines()[0], "->", sub)
    if not ok:
        raise SystemExit(rep)


if __name__ == "__main__":
    main()

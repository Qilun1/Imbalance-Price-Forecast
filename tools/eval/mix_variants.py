"""Score inference-time variants of a trained mixture model on the validation period (no retraining).

Variants change only MixBundle.predict settings: widen (band factor), widen_mode ("marginal": scale
p10/p90 around p50 after mixing, the original; "component": scale each conditional head around its
median before mixing, so bands and spike probabilities come from one consistent mixture) and tail
("linear" or "exp" extrapolation beyond the 5 %/95 % knots). Each variant is written to infer_data
as <model>__<variant> and scored with the organiser's score.py.

    uv run python -m tools.eval.mix_variants --model mix_v4b-val --widen 1.0 1.2 1.4 --modes marginal component --tails linear exp
"""
from __future__ import annotations

import argparse
import itertools

import pandas as pd

from imbalance import forecasts
from imbalance.mixture import MixBundle
from imbalance.paths import WORK_DIR
from tools.cli import origins_for
from tools.eval.organiser import score, templates, validate
from tools.training.feature_table import load_feature_table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="trained -val mixture bundle")
    ap.add_argument("--widen", nargs="+", type=float, default=[1.0, 1.2, 1.4])
    ap.add_argument("--modes", nargs="+", default=["marginal", "component"])
    ap.add_argument("--tails", nargs="+", default=["linear", "exp"])
    ap.add_argument("--period", choices=["val", "test"], default="val", help="test: export + validate only")
    a = ap.parse_args()
    b = MixBundle.load(a.model)
    table = load_feature_table(b.meta["feature_set"])
    origins = origins_for(a.period)
    feats = table[table["forecast_origin_utc"].isin(origins)].drop(
        columns=[c for c in table if c.startswith("y_")]).reset_index(drop=True)
    ids = feats[["forecast_origin_utc", "delivery_start_utc", "step", "data_cutoff_utc"]]
    rows = []
    for w, mode, tail in itertools.product(a.widen, a.modes, a.tails):
        b.meta.update({"widen": w, "widen_mode": mode, "tail": tail})
        name = f"{a.model}__w{w:.2f}_{mode}_{tail}"
        b.name = name
        out = pd.concat([ids, b.predict(feats)], axis=1)
        tpl, ori = templates(a.period)
        sub = forecasts.export_submission(name, tpl, WORK_DIR / "submissions" / f"{name}_{a.period}.csv", frame=out)
        if a.period == "test":
            ok, rep = validate(sub, ori)
            print(rep.strip().splitlines()[0], "->", sub)
            if not ok:
                raise RuntimeError(rep)
            continue
        ok, rep = score(sub, WORK_DIR / "scores" / name, WORK_DIR / "scores" / "baseline-val" / "score_summary.csv")
        if not ok:
            raise RuntimeError(rep)
        s = pd.read_csv(WORK_DIR / "scores" / name / "score_summary.csv").iloc[0]
        rows.append({"widen": w, "mode": mode, "tail": tail, "mae": s["mae_p50"], "pinball": s["calibration_pinball_mean"],
                     "coverage": s["coverage_p10_p90"], "brier_spike": s["brier_spike_mean"], "brier_dir": s["brier_direction"]})
        print(pd.DataFrame(rows).tail(1).to_string(index=False, header=False))
    if not rows:
        return
    res = pd.DataFrame(rows).sort_values("pinball")
    print("\n" + res.to_string(index=False))
    res.to_csv(WORK_DIR / "scores" / f"{a.model}__variants.csv", index=False)


if __name__ == "__main__":
    main()

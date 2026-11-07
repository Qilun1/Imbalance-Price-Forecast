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

from sklearn.metrics import average_precision_score

from imbalance import alert_features, events
from imbalance.alert_model import FAMILIES, AlertBundle, EventModel
from imbalance.contract import HORIZON_STEPS, TEST_FIRST_ORIGIN, TRAIN_END_DELIVERY, VALIDATION_FIRST_ORIGIN
from imbalance.features import load_store
from imbalance.model import Bundle
from imbalance.paths import CONFIGS_DIR, PROCESSED_DIR, WORK_DIR

from tools.training.feature_table import load_feature_table

BASE, CHALLENGER = "lgbm_v4s", "lgbm_v4ms"
SEGMENTS = [pd.Timestamp(t) for t in ["2026-06-30T21:00:00Z", "2026-07-31T21:00:00Z", "2026-08-31T21:00:00Z"]] + \
    [VALIDATION_FIRST_ORIGIN, TEST_FIRST_ORIGIN]
VAL_LAST_DELIVERY = VALIDATION_FIRST_ORIGIN - pd.Timedelta(minutes=15)     # labels for the -val variant
OOF_PATH = PROCESSED_DIR / "alert_oof_{name}.parquet"
TABLE_PATH = PROCESSED_DIR / "alert_table.parquet"
EVAL_DIR = WORK_DIR / "alerts"                        # diagnostics, gitignored


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


def oof_forecasts(config_name: str, rebuild: bool = False) -> pd.DataFrame:
    """Out-of-sample forecasts for every origin from SEGMENTS[0] up to the first test origin."""
    path = Path(str(OOF_PATH).format(name=config_name))
    if path.exists() and not rebuild:
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
    base, challenger = oof_forecasts(BASE, rebuild), oof_forecasts(CHALLENGER, rebuild)
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


def input_columns(table: pd.DataFrame) -> list[str]:
    labels = set(events.EVENT_IDS) | {f"{e}__val" for e in events.EVENT_IDS}
    return [c for c in table.columns if c not in alert_features.KEYS and c not in labels]


def metrics(p: np.ndarray, lo: np.ndarray, hi: np.ndarray, y: np.ndarray, clim: np.ndarray, threshold: np.ndarray,
            days: float) -> dict:
    """Diagnostics on held-out rows (labelled as such; the official score is score.py's)."""
    eps = 1e-6
    brier, brier_clim = float(np.mean((p - y) ** 2)), float(np.mean((clim - y) ** 2))
    fires = p >= threshold
    hits = int((fires & (y == 1)).sum())
    bins = np.clip((p * 10).astype(int), 0, 9)
    ece = sum(abs(p[bins == b].mean() - y[bins == b].mean()) * (bins == b).mean() for b in range(10) if (bins == b).any())
    return {"rows": len(y), "positives": float(y.mean()), "brier": brier, "bss": 1 - brier / brier_clim,
            "log_loss": float(-np.mean(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1)))),
            "pr_auc": float(average_precision_score(y, p)) if 0 < y.sum() < len(y) else np.nan,
            "ece": float(ece), "mean_interval": float(np.mean(hi - lo)),
            "hit_rate": hits / max(int((y == 1).sum()), 1), "false_alarm_ratio": 1 - hits / max(int(fires.sum()), 1),
            "notes_per_day": float(fires.sum()) / days}


def evaluate(families=FAMILIES) -> pd.DataFrame:
    """Train each family on rows before validation (labels up to 6 Sep), score the validation period."""
    table = training_table()
    inputs = input_columns(table)
    train = table[table["forecast_origin_utc"] < VALIDATION_FIRST_ORIGIN]
    val = table[(table["forecast_origin_utc"] >= VALIDATION_FIRST_ORIGIN) &
                (table["forecast_origin_utc"] < TEST_FIRST_ORIGIN)]
    days = val["forecast_origin_utc"].nunique() / 24
    rows = []
    for event in events.EVENT_IDS:
        tr = train[train[f"{event}__val"].notna()].reset_index(drop=True)
        va = val[val[event].notna()].reset_index(drop=True)
        y_tr, y_va = tr[f"{event}__val"].to_numpy(int), va[event].to_numpy(int)
        for family in families:
            m = EventModel.fit(family, tr[inputs], y_tr, tr["forecast_origin_utc"], tr["window"], event)
            p, lo, hi = m.predict(va[inputs])
            clim = va["window"].map(m.base_rate).to_numpy(float)
            thr = va["window"].map(m.threshold).to_numpy(float)
            for window in [*events.WINDOWS, "all"]:
                k = np.ones(len(va), bool) if window == "all" else (va["window"] == window).to_numpy()
                rows.append({"event": event, "family": family, "window": window,
                             **metrics(p[k], lo[k], hi[k], y_va[k], clim[k], thr[k], days)})
            print(f"{event:22s} {family:6s} BSS {rows[-1]['bss']:+.3f}  PR-AUC {rows[-1]['pr_auc']:.3f}")
    out = pd.DataFrame(rows)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(EVAL_DIR / "eval_validation.csv", index=False)
    return out


def train(variant: str) -> AlertBundle:
    """alerts-val: rows before validation, labels up to 6 Sep. alerts: every row, labels up to 4 Oct."""
    cfg = load_config("alerts")
    table = training_table()
    if variant == "val":
        table = table[table["forecast_origin_utc"] < VALIDATION_FIRST_ORIGIN]
    name = f"{cfg['name']}-val" if variant == "val" else cfg["name"]
    skill = {}
    eval_path = EVAL_DIR / "eval_validation.csv"
    if eval_path.exists():           # validation skill of the chosen family, for the low-skill flag
        ev = pd.read_csv(eval_path)
        ev = ev[ev["window"] == "all"].set_index(["event", "family"])["bss"]
        skill = {e: float(ev.get((e, f), np.nan)) for e, f in cfg["families"].items()}
    print(f"training {name}: {table['forecast_origin_utc'].nunique()} origins")
    bundle = AlertBundle.train(name, table, input_columns(table), cfg["families"], label_columns(variant),
                               extra_meta={"variant": variant, "base_model": cfg["base_model"],
                                           "challenger_model": cfg["challenger_model"],
                                           "validation_bss": skill, "low_skill_bss": cfg["low_skill_bss"]})
    print(f"saved {bundle.save()}")
    return bundle


def infer_periods() -> pd.DataFrame:
    """Event probabilities for validation origins (alerts-val, -val base models) and test origins
    (alerts, final base models), written to the event_probs table of forecasts.duckdb."""
    from imbalance import alert_inference
    from imbalance.contract import TEST_ORIGINS, read_origins
    cfg = load_config("alerts")
    base_feats = load_feature_table(load_config(cfg["base_model"])["feature_set"])
    ch_feats = load_feature_table(load_config(cfg["challenger_model"])["feature_set"])
    val_origins = pd.date_range(VALIDATION_FIRST_ORIGIN, TEST_FIRST_ORIGIN - pd.Timedelta(hours=1), freq="h")
    frames = []
    for suffix, origins in (("-val", val_origins), ("", read_origins(TEST_ORIGINS))):
        out = alert_inference.infer(f"{cfg['name']}{suffix}", origins, base_feats, ch_feats)
        print(f"{cfg['name']}{suffix}: {len(origins)} origins -> {len(out):,} event rows")
        frames.append(out)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="(re)build OOF forecasts and the training table")
    ap.add_argument("--evaluate", action="store_true", help="compare model families on validation")
    ap.add_argument("--train", choices=["val", "final", "both"], help="train and save the event classifiers")
    ap.add_argument("--infer", action="store_true", help="write event probabilities for validation and test origins")
    a = ap.parse_args()
    if a.infer:
        out = infer_periods()
        val = out[out["model"].str.endswith("-val")]          # tier bars are read on validation only
        width = val["p_hi"] - val["p_lo"]
        print("validation interval width quantiles (50/90/98):", np.round(np.nanpercentile(width, [50, 90, 98]), 3))
        print("validation confidence tiers:", val["confidence"].value_counts(normalize=True).round(3).to_dict())
        return
    if a.train:
        for variant in (["val", "final"] if a.train == "both" else [a.train]):
            train(variant)
        return
    if a.evaluate:
        out = evaluate()
        pooled = out[out["window"] == "all"]
        pd.set_option("display.width", 160)
        print("\nValidation Brier skill score vs climatology (diagnostic; higher is better):")
        print(pooled.pivot(index="event", columns="family", values="bss").round(3))
        print("\nValidation PR-AUC:")
        print(pooled.pivot(index="event", columns="family", values="pr_auc").round(3))
        best = pooled.loc[pooled.groupby("event")["brier"].idxmin(), ["event", "family", "bss", "ece", "hit_rate",
                                                                    "false_alarm_ratio", "notes_per_day"]]
        print("\nBest family per event (lowest validation Brier):")
        print(best.round(3).to_string(index=False))
        return
    table = training_table(rebuild=a.build)
    pd.set_option("display.width", 140)
    period = table["forecast_origin_utc"] < VALIDATION_FIRST_ORIGIN
    print("\nEvent rates on training rows before validation (labels up to 6 Sep), by window:")
    print(table[period].groupby("window", sort=False)[list(label_columns("val").values())].mean().T.round(3))


if __name__ == "__main__":
    main()

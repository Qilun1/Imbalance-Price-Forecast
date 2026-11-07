"""DIAGNOSTIC ONLY: how the event classifiers did on the test period (5 Oct - 1 Nov 2026 local).

Scores the stored `alerts` probabilities (event_probs, made with data usable at each origin) against
the events that then happened. AGENTS.md rule 4: test-period data may not be used for training,
tuning, calibration, feature selection or model choice. This report is for reading after the fact
only; nothing here may feed back into events.py, alert_model.py, configs/alerts.yaml or thresholds.
The official score stays the organiser's score.py.

Labels come from realised values (Store.truth) up to the last scored quarter-hour. forecast_miss uses
the lgbm_v4s P50 stored for the same origins, the forecast the classifier read.

    uv run python -m tools.eval.alert_test_report
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from imbalance import events, forecasts
from imbalance.alert_inference import read_probs
from imbalance.contract import TEST_ORIGINS, read_origins
from imbalance.features import load_store

from tools.training.alert_train import EVAL_DIR, load_config, metrics, p50_matrix

LAST_SCORED = pd.Timestamp("2026-11-02T06:45:00Z")      # last delivery quarter-hour of the test period


def chat_bar(threshold: pd.Series, base_rate: pd.Series) -> np.ndarray:
    """The mockup chat's bar (mockup/app.js): max(default threshold, 2 x usual rate, 30 %), at most 80 %."""
    return np.minimum(0.8, np.maximum.reduce([threshold.to_numpy(), 2 * base_rate.to_numpy(), np.full(len(threshold), 0.3)]))


def report() -> pd.DataFrame:
    cfg = load_config("alerts")
    origins = read_origins(TEST_ORIGINS)
    probs = read_probs(cfg["name"], origins)
    if probs.empty:
        raise SystemExit("no test-period event probabilities: run `uv run python -m tools.cli alerts infer`")
    p50 = p50_matrix(forecasts.read(cfg["base_model"], origins), origins)
    labels = events.labels(load_store(), origins, p50=p50, last_delivery=LAST_SCORED)
    long = labels.melt(id_vars=["forecast_origin_utc", "window"], var_name="event", value_name="y")
    df = probs.merge(long, on=["forecast_origin_utc", "window", "event"]).dropna(subset=["y"])
    days = df["forecast_origin_utc"].nunique() / 24
    rows = []
    for event, g in df.groupby("event"):
        for window in [*events.WINDOWS, "all"]:
            k = g if window == "all" else g[g["window"] == window]
            y = k["y"].to_numpy(int)
            p, lo, hi = k["p"].to_numpy(), k["p_lo"].to_numpy(), k["p_hi"].to_numpy()
            base = k["base_rate"].to_numpy()
            row = {"event": event, "window": window,
                   **metrics(p, lo, hi, y, base, k["threshold"].to_numpy(), days)}
            bar = chat_bar(k["threshold"], k["base_rate"])
            said = p >= bar
            # The chat posts when a note crosses its bar (or rises 10 points), not every hour it stays above.
            k = k.assign(said=said).sort_values("forecast_origin_utc")
            crossed = k.groupby("window")["said"].transform(lambda s: s & ~s.shift(fill_value=False))
            row["chat_messages_per_day"] = float(crossed.sum()) / days
            row["chat_hit_rate"] = float((said & (y == 1)).sum() / max((y == 1).sum(), 1))
            row["chat_false_alarm_ratio"] = float(1 - (said & (y == 1)).sum() / max(said.sum(), 1))
            rows.append(row)
    out = pd.DataFrame(rows)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(EVAL_DIR / "test_diagnostic.csv", index=False)
    return out


def main() -> None:
    out = report()
    cfg = load_config("alerts")
    pooled = out[out["window"] == "all"].set_index("event")
    val_path = EVAL_DIR / "eval_validation.csv"
    if val_path.exists():
        val = pd.read_csv(val_path)
        val = val[val["window"] == "all"].set_index(["event", "family"])["bss"]
        pooled["val_bss"] = [val.get((e, cfg["families"][e]), np.nan) for e in pooled.index]
    pd.set_option("display.width", 170)
    cols = ["family", "positives", "val_bss", "bss", "pr_auc", "ece", "hit_rate", "false_alarm_ratio",
            "chat_hit_rate", "chat_false_alarm_ratio", "chat_messages_per_day"]
    pooled["family"] = [cfg["families"][e] for e in pooled.index]
    print("DIAGNOSTIC ONLY, test period 5 Oct - 1 Nov (never use for tuning, AGENTS.md rule 4)\n")
    print(pooled[[c for c in cols if c in pooled]].round(3).to_string())
    print("\nBrier skill by window (vs the training base rate):")
    print(out[out["window"] != "all"].pivot(index="event", columns="window", values="bss")[list(events.WINDOWS)].round(3))
    print(f"\nwritten to {EVAL_DIR / 'test_diagnostic.csv'} (gitignored)")


if __name__ == "__main__":
    main()

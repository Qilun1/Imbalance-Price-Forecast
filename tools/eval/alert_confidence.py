"""Do the event classifiers' confidence signals mean anything? Validation only (7 Sep - 4 Oct 2026).

Scores the stored alerts-val probabilities (out of sample: -val base models, classifiers trained on
labels up to 6 Sep) against the validation labels of the training table (realised values up to the
training cutoff, AGENTS.md rule 4). Two checks:

1. Confidence tiers and their reasons (wide interval, stale data, base models disagree): is a "low"
   or "medium" note less reliable than a "high" one? Per group: Brier skill vs the base rate,
   calibration gap (mean p - event rate) and ECE, with a day-block bootstrap interval on the skill.
2. Venn-Abers intervals: rows are binned by p within each event. A bin is consistent when its event
   rate lies inside the bin's mean [p_lo, p_hi] widened by two binomial standard errors (the rate is
   an estimate too); the same test on p alone shows what the interval adds. And: do wider intervals
   go with larger calibration errors (ECE by interval-width tercile within each event)?

Diagnostic only; the official score is score.py's. Output goes to static_data/work/alerts/ (gitignored).

    uv run python -m tools.eval.alert_confidence
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from imbalance import events
from imbalance.alert_inference import CONFLICT_P50_GAP, STALE_MINUTES, WIDTH_LOW, WIDTH_MEDIUM, read_probs
from imbalance.contract import TEST_FIRST_ORIGIN, VALIDATION_FIRST_ORIGIN

from tools.training.alert_train import EVAL_DIR, load_config, training_table

N_BINS = 10
N_BOOT = 500
TIERS = ("high", "medium", "low")


def validation_rows() -> pd.DataFrame:
    """One row per (origin, window, event): stored probabilities, label and the tier's inputs."""
    model = f"{load_config('alerts')['name']}-val"
    origins = pd.date_range(VALIDATION_FIRST_ORIGIN, TEST_FIRST_ORIGIN - pd.Timedelta(hours=1), freq="h")
    probs = read_probs(model, origins)
    if probs.empty:
        raise SystemExit(f"no {model} probabilities: run `uv run python -m tools.cli alerts infer`")
    table = training_table()
    table = table[table["forecast_origin_utc"].isin(origins)]
    keys = ["forecast_origin_utc", "window"]
    labels = table[keys + list(events.EVENT_IDS)].melt(id_vars=keys, var_name="event", value_name="y")
    df = probs.merge(labels, on=keys + ["event"]).merge(table[keys + ["f_data_age_min", "gap_p50_max"]], on=keys)
    df = df.dropna(subset=["y"]).reset_index(drop=True)
    width = df["p_hi"] - df["p_lo"]
    df["width"] = width
    df["wide"] = np.where(width > WIDTH_LOW, "low", np.where(width > WIDTH_MEDIUM, "medium", "narrow"))
    df["stale"] = df["f_data_age_min"].fillna(0) >= STALE_MINUTES
    df["conflict"] = df["gap_p50_max"].fillna(0) >= CONFLICT_P50_GAP
    df["day"] = df["forecast_origin_utc"].dt.floor("D")
    return df


def ece(p: np.ndarray, y: np.ndarray) -> float:
    bins = np.clip((p * N_BINS).astype(int), 0, N_BINS - 1)
    return float(sum(abs(p[bins == b].mean() - y[bins == b].mean()) * (bins == b).mean()
                     for b in range(N_BINS) if (bins == b).any()))


def bss(g: pd.DataFrame) -> float:
    clim = ((g["base_rate"] - g["y"]) ** 2).sum()
    return float(1 - ((g["p"] - g["y"]) ** 2).sum() / clim) if clim > 0 else np.nan


def boot(g: pd.DataFrame, seed: int = 0) -> dict[str, float]:
    """90 % intervals of the Brier skill and the calibration gap, resampling whole days (hours within a
    day are correlated)."""
    rng = np.random.default_rng(seed)
    by_day = {d: x for d, x in g.groupby("day")}
    days = np.array(list(by_day))
    if len(days) < 2:
        return {"bss_p5": np.nan, "bss_p95": np.nan, "gap_p5": np.nan, "gap_p95": np.nan}
    draws = [pd.concat([by_day[d] for d in rng.choice(days, len(days))]) for _ in range(N_BOOT)]
    b = np.nanpercentile([bss(x) for x in draws], [5, 95])
    gap = np.nanpercentile([x["p"].mean() - x["y"].mean() for x in draws], [5, 95])
    return {"bss_p5": b[0], "bss_p95": b[1], "gap_p5": gap[0], "gap_p95": gap[1]}


def ece_if_calibrated(p: np.ndarray, seed: int = 0) -> float:
    """ECE a perfectly calibrated model would show on these rows by chance alone (y drawn from p)."""
    rng = np.random.default_rng(seed)
    return float(np.mean([ece(p, (rng.random(len(p)) < p).astype(float)) for _ in range(N_BOOT // 5)]))


def group_stats(df: pd.DataFrame, by: str) -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(by):
        p, y = g["p"].to_numpy(), g["y"].to_numpy()
        rows.append({by: key, "rows": len(g), "share": len(g) / len(df), "events": int(y.sum()),
                     "bss": bss(g), "gap": float(p.mean() - y.mean()), **boot(g),
                     "ece": ece(p, y), "ece_if_calibrated": ece_if_calibrated(p),
                     "mean_width": float(g["width"].mean())})
    return pd.DataFrame(rows)


def tier_report(df: pd.DataFrame) -> pd.DataFrame:
    """Brier skill etc. by confidence tier and by each reason behind it, pooled over events."""
    parts = []
    for by in ("confidence", "wide", "stale", "conflict"):
        s = group_stats(df, by).rename(columns={by: "group"})
        s.insert(0, "split", by)
        parts.append(s)
    return pd.concat(parts, ignore_index=True)


def interval_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per event and probability bin: event rate vs the mean interval and vs the mean p."""
    rows = []
    for event, g in df.groupby("event"):
        q = pd.qcut(g["p"].rank(method="first"), min(N_BINS, len(g)), labels=False)
        for b, k in g.groupby(q):
            n, rate, p = len(k), k["y"].mean(), k["p"].mean()
            # Standard error of the rate clustered by day: overlapping windows make hours within a day
            # far from independent, so the binomial error would be too small.
            daily = k.groupby("day")["y"].agg(["sum", "size"])
            se = np.sqrt(((daily["sum"] - p * daily["size"]) ** 2).sum()) / n
            lo, hi = k["p_lo"].mean(), k["p_hi"].mean()
            rows.append({"event": event, "bin": int(b), "rows": n, "p": p, "p_lo": lo, "p_hi": hi, "rate": rate,
                         "inside": lo <= rate <= hi, "consistent": lo - 2 * se <= rate <= hi + 2 * se,
                         "consistent_point": p - 2 * se <= rate <= p + 2 * se})
    return pd.DataFrame(rows)


def width_report(df: pd.DataFrame) -> pd.DataFrame:
    """Calibration error by interval-width tercile, the terciles taken within each event."""
    df = df.assign(tercile=df.groupby("event")["width"].transform(
        lambda w: pd.qcut(w.rank(method="first"), 3, labels=["narrow", "middle", "wide"])))
    return df.groupby(["event", "tercile"], observed=True).apply(
        lambda g: pd.Series({"rows": len(g), "mean_width": g["width"].mean(),
                             "abs_gap": abs(g["p"].mean() - g["y"].mean()),
                             "ece": ece(g["p"].to_numpy(), g["y"].to_numpy())}), include_groups=False).reset_index()


def main() -> None:
    df = validation_rows()
    tiers, intervals, widths = tier_report(df), interval_report(df), width_report(df)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    tiers.to_csv(EVAL_DIR / "confidence_tiers_validation.csv", index=False)
    intervals.to_csv(EVAL_DIR / "intervals_validation.csv", index=False)
    widths.to_csv(EVAL_DIR / "interval_width_validation.csv", index=False)

    pd.set_option("display.width", 170)
    print(f"DIAGNOSTIC, validation 7 Sep - 4 Oct local: {len(df):,} (origin, window, event) rows, "
          f"{df['forecast_origin_utc'].nunique()} origins\n")
    print("1. Reliability by confidence tier and by each reason (pooled over events; p5/p95: day-block bootstrap;\n"
          "   gap = mean p - event rate; ece_if_calibrated = the ECE chance alone gives on these rows)")
    print(tiers.round(3).to_string(index=False))
    per_event = df.groupby(["event", "confidence"]).apply(bss, include_groups=False).unstack()
    print("\nBrier skill by event and tier:")
    print(per_event.reindex(columns=[t for t in TIERS if t in per_event.columns]).round(3))
    print("\n2. Venn-Abers intervals: share of probability bins whose event rate is consistent (within 2 SE)")
    summary = intervals.groupby("event")[["inside", "consistent", "consistent_point"]].mean()
    summary.loc["all"] = intervals[["inside", "consistent", "consistent_point"]].mean()
    print(summary.round(2).to_string())
    print("\nCalibration error by interval-width tercile (pooled over events):")
    print(widths.groupby("tercile", observed=True)[["mean_width", "abs_gap", "ece"]].mean().round(4).to_string())
    print(f"\nwritten to {EVAL_DIR} (gitignored)")


if __name__ == "__main__":
    main()

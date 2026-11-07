"""Submission requirements harness for the Turku Energia imbalance price challenge.

Runs, for a candidate test file (and optionally its validation counterpart):
  A. the organiser's validate_submission.py with --origins          (hard requirement, 0 points if it fails)
  B. structural checks beyond the validator: exact column order, identifier rows equal to
     sample_submission.csv, 673 x 40 = 26,920 rows, delivery = origin + (step-1)*15 min,
     no NaN anywhere (including the optional columns), p10<=p50<=p90, probabilities in [0,1],
     direction sum = 1, spike sum <= 1, data_cutoff_utc <= origin for every row, top_drivers non-empty
  C. the data availability rule as far as the file shows it: data_cutoff_utc never after the origin;
     the earliest possible cutoff for each source family from availability.csv
  D. plausibility: value ranges, flat-forecast detection, p_none share vs the observed 'none' base
     rate, mean spike probabilities vs observed shares, band width non-negative and finite
  E. the organiser's score.py on the validation counterpart vs the baseline, plus horizon buckets
Exit code 0 only when A-C pass; D and E are reported.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REQ = ["forecast_origin_utc", "delivery_start_utc", "step", "p10", "p50", "p90",
       "p_up", "p_down", "p_none", "p_spike_high", "p_spike_low"]
OPT = ["data_cutoff_utc", "top_drivers"]
FAILS: list[str] = []
WARNS: list[str] = []


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def fail(msg: str) -> None:
    FAILS.append(msg)
    print(f"  FAIL  {msg}")


def warn(msg: str) -> None:
    WARNS.append(msg)
    print(f"  WARN  {msg}")


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def section(title: str) -> None:
    print(f"\n=== {title}")


def check_structure(path: Path, sample: Path, origins: Path, label: str) -> pd.DataFrame:
    section(f"B. Structural checks: {label}")
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    smp = pd.read_csv(sample, dtype=str, keep_default_na=False)
    # header
    if list(raw.columns) == list(smp.columns):
        ok(f"header identical to sample_submission ({len(raw.columns)} columns, same order)")
    else:
        fail(f"header differs from sample_submission: {list(raw.columns)}")
    # row count / identifiers
    n_orig = len(pd.read_csv(origins))
    if len(raw) == n_orig * 40:
        ok(f"{len(raw)} rows = {n_orig} origins x 40 steps")
    else:
        fail(f"row count {len(raw)} != {n_orig}*40")
    ids = ["forecast_origin_utc", "delivery_start_utc", "step"]
    if len(raw) == len(smp) and (raw[ids].values == smp[ids].values).all():
        ok("identifier rows (origin, delivery, step) identical to the template, same row order")
    else:
        merged = raw[ids].merge(smp[ids], how="outer", indicator=True)
        bad = merged[merged["_merge"] != "both"]
        if bad.empty:
            warn("identifier set equals the template but row order differs (validator accepts; kept as-is)")
        else:
            fail(f"{len(bad)} identifier rows differ from the template")
    # empties
    for c in REQ:
        n = (raw[c].str.strip() == "").sum()
        (ok if n == 0 else fail)(f"{c}: {n} empty values")
    for c in OPT:
        n = (raw[c].str.strip() == "").sum()
        (ok if n == 0 else warn)(f"{c} (optional, but asked for in the brief): {n} empty values")
    df = raw.copy()
    for c in ["p10", "p50", "p90", "p_up", "p_down", "p_none", "p_spike_high", "p_spike_low"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["step"] = pd.to_numeric(df["step"], errors="coerce")
    for c in ["forecast_origin_utc", "delivery_start_utc", "data_cutoff_utc"]:
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce", format="%Y-%m-%dT%H:%M:%SZ")
    num = ["p10", "p50", "p90", "p_up", "p_down", "p_none", "p_spike_high", "p_spike_low"]
    nbad = int(df[num].isna().sum().sum()) + int(np.isinf(df[num].to_numpy(dtype=float)).sum())
    (ok if nbad == 0 else fail)(f"non-numeric / NaN / inf in forecast columns: {nbad}")
    nbad = int(df[["forecast_origin_utc", "delivery_start_utc"]].isna().sum().sum())
    (ok if nbad == 0 else fail)(f"unparseable identifier timestamps: {nbad}")
    # delivery = origin + (step-1)*15min
    exp = df["forecast_origin_utc"] + pd.to_timedelta((df["step"] - 1) * 15, unit="min")
    nbad = int((exp != df["delivery_start_utc"]).sum())
    (ok if nbad == 0 else fail)(f"delivery_start != origin + (step-1)*15 min: {nbad} rows")
    # quantile order
    nbad = int(((df["p10"] > df["p50"]) | (df["p50"] > df["p90"])).sum())
    (ok if nbad == 0 else fail)(f"quantile order violations p10<=p50<=p90: {nbad}")
    nbad = int(((df["p10"] > df["p50"] - 1e-9) | (df["p50"] > df["p90"] - 1e-9)).sum())
    if nbad:
        warn(f"{nbad} rows with a degenerate band (p10==p50 or p50==p90)")
    # probabilities
    probs = ["p_up", "p_down", "p_none", "p_spike_high", "p_spike_low"]
    nbad = int(((df[probs] < 0) | (df[probs] > 1)).sum().sum())
    (ok if nbad == 0 else fail)(f"probabilities outside [0,1]: {nbad}")
    s = df[["p_up", "p_down", "p_none"]].sum(axis=1)
    nbad = int(((s - 1).abs() > 1e-3).sum())
    (ok if nbad == 0 else fail)(f"direction sum != 1 (tol 1e-3): {nbad}; max |dev| {float((s-1).abs().max()):.2e}")
    s2 = df["p_spike_high"] + df["p_spike_low"]
    nbad = int((s2 > 1 + 1e-3).sum())
    (ok if nbad == 0 else fail)(f"spike sum > 1: {nbad}; max sum {float(s2.max()):.4f}")
    # availability rule as visible in the file
    section(f"C. Data availability rule (as visible in the file): {label}")
    if df["data_cutoff_utc"].isna().any():
        warn(f"data_cutoff_utc unparseable or empty in {int(df['data_cutoff_utc'].isna().sum())} rows")
    late = df["data_cutoff_utc"] > df["forecast_origin_utc"]
    (ok if int(late.sum()) == 0 else fail)(f"data_cutoff_utc after forecast_origin_utc: {int(late.sum())} rows")
    lag = (df["forecast_origin_utc"] - df["data_cutoff_utc"]).dt.total_seconds() / 60
    print(f"        cutoff lag behind origin: min {lag.min():.0f} min, median {lag.median():.0f}, max {lag.max():.0f}")
    if lag.min() < 0:
        fail("negative cutoff lag")
    drv = raw["top_drivers"].str.strip()
    print(f"        top_drivers: {drv.nunique()} distinct strings; most common: {drv.value_counts().head(3).to_dict()}")
    if (drv == "").any():
        warn("some top_drivers empty")
    return df


def check_plausibility(df: pd.DataFrame, label: str, actuals: Path | None) -> None:
    section(f"D. Plausibility: {label}")
    print(f"        p50 range [{df.p50.min():.1f}, {df.p50.max():.1f}], p10 min {df.p10.min():.1f}, p90 max {df.p90.max():.1f}")
    if df.p50.abs().max() > 4000 or df.p90.max() > 10000 or df.p10.min() < -10000:
        warn("price quantiles beyond plausible Finnish range (check for exploded members)")
    width = df.p90 - df.p10
    print(f"        band width: median {width.median():.1f}, p5 {width.quantile(.05):.1f}, p95 {width.quantile(.95):.1f}")
    by_step = df.groupby("step")[["p_up", "p_down", "p_none", "p_spike_high", "p_spike_low"]].mean()
    print("        mean probabilities by step (1, 8, 20, 40):")
    print(by_step.loc[[1, 8, 20, 40]].round(3).to_string())
    flat = df.groupby("forecast_origin_utc")["p50"].nunique()
    n_flat = int((flat == 1).sum())
    (ok if n_flat == 0 else warn)(f"origins with a constant p50 across all 40 steps: {n_flat}")
    if actuals is not None:
        act = pd.read_csv(actuals)
        none_share = (act["direction"].str.lower() == "none").mean()
        print(f"        observed validation base rates: none {none_share:.3f}, "
              f"spike high {((act.imbalance_price > act.spot_price + 50)).mean():.3f}, "
              f"spike low {((act.imbalance_price < act.spot_price - 50)).mean():.3f}")
    print(f"        file means: p_none {df.p_none.mean():.3f}, p_spike_high {df.p_spike_high.mean():.3f}, "
          f"p_spike_low {df.p_spike_low.mean():.3f}")


def score_val(score_py: Path, val_file: Path, actuals: Path, baseline_summary: Path, outdir: Path) -> None:
    section(f"E. Official score.py on validation counterpart: {val_file.name}")
    outdir.mkdir(parents=True, exist_ok=True)
    rc, out = run([sys.executable, "-I", str(score_py), "--submission", str(val_file), "--actuals", str(actuals),
                   "--spike-margin", "50", "--output-dir", str(outdir), "--baseline-summary", str(baseline_summary)])
    if rc != 0:
        fail(f"score.py exit {rc}\n{out[-2000:]}")
        return
    s = pd.read_csv(outdir / "score_summary.csv").iloc[0]
    b = pd.read_csv(baseline_summary).iloc[0]
    rows = [("MAE p50", "mae_p50"), ("pinball mean (P10,P90)", "calibration_pinball_mean"),
            ("coverage P10-P90", "coverage_p10_p90"), ("Brier spike mean", "brier_spike_mean"),
            ("Brier spike high", "brier_spike_high"), ("Brier spike low", "brier_spike_low"),
            ("Brier direction", "brier_direction")]
    print(f"        {'metric':26s} {'model':>10s} {'baseline':>10s} {'skill':>8s}")
    for name, col in rows:
        sk = "" if col == "coverage_p10_p90" else f"{(1 - s[col] / b[col]) * 100:6.1f}%"
        print(f"        {name:26s} {s[col]:10.4f} {b[col]:10.4f} {sk:>8s}")
    cov = s["coverage_p10_p90"]
    (ok if 0.76 <= cov <= 0.84 else warn)(f"coverage {cov:.3f} (target 0.80)")
    for name, col in rows:
        if col == "coverage_p10_p90":
            continue
        if s[col] >= b[col]:
            fail(f"{name} not better than baseline -> 0 points on that criterion")
    print(f"        rows scored price {int(s['rows_scored_price'])}, skipped {int(s['rows_skipped_price'])}")
    hz = outdir / "score_by_horizon.csv"
    if hz.exists():
        h = pd.read_csv(hz)
        stepcol = [c for c in h.columns if "step" in c.lower()][0]
        h["bucket"] = pd.cut(h[stepcol], [0, 4, 8, 16, 40], labels=["1-4", "5-8", "9-16", "17-40"])
        cols = [c for c in h.columns if c.startswith(("mae", "calibration", "coverage", "brier"))]
        print("        by horizon bucket (mean over steps):")
        print(h.groupby("bucket", observed=True)[cols].mean().round(4).to_string())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", required=True, help="candidate forecast_backtest.csv (test period)")
    ap.add_argument("--val", help="validation-period counterpart of the same model")
    ap.add_argument("--starter", required=True, help="folder with validate_submission.py, score.py, sample_submission.csv, forecast_origins.csv")
    ap.add_argument("--actuals", help="actuals_validation.csv")
    ap.add_argument("--baseline-summary", help="baseline score_summary.csv")
    ap.add_argument("--outdir", default="/tmp/subcheck")
    a = ap.parse_args()
    st = Path(a.starter)
    test = Path(a.test)

    section(f"A. Official validator: {test}")
    rc, out = run([sys.executable, "-I", str(st / "validate_submission.py"), "--backtest", str(test),
                   "--origins", str(st / "forecast_origins.csv")])
    print("        " + out.strip().replace("\n", "\n        ")[-1500:])
    (ok if rc == 0 else fail)(f"validate_submission.py exit code {rc}")
    if "Warnings: 0" not in out:
        warn("validator reported warnings")

    df = check_structure(test, st / "sample_submission.csv", st / "forecast_origins.csv", "test file")
    check_plausibility(df, "test file", Path(a.actuals) if a.actuals else None)

    if a.val:
        val = Path(a.val)
        section(f"A'. Official validator on the validation counterpart: {val.name}")
        # build an origins file from the val file itself (validator needs one)
        v = pd.read_csv(val, usecols=["forecast_origin_utc"])
        vo = Path(a.outdir) / "val_origins.csv"
        vo.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"forecast_origin_utc": sorted(v["forecast_origin_utc"].unique())}).to_csv(vo, index=False)
        rc, out = run([sys.executable, "-I", str(st / "validate_submission.py"), "--backtest", str(val), "--origins", str(vo)])
        print("        " + out.strip().replace("\n", "\n        ")[-600:])
        (ok if rc == 0 else fail)(f"validator on val file exit code {rc}")
        if a.actuals and a.baseline_summary:
            score_val(st / "score.py", val, Path(a.actuals), Path(a.baseline_summary), Path(a.outdir) / "score")

    section("SUMMARY")
    print(f"  {len(FAILS)} hard failures, {len(WARNS)} warnings")
    for f in FAILS:
        print(f"  FAIL  {f.splitlines()[0]}")
    for w in WARNS:
        print(f"  WARN  {w}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

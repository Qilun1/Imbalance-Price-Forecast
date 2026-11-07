"""NOT ADOPTED (negative result, kept for the record). Long-history up-regulation price-tail heads.

Result (validation, 7 Nov 2026): against heads trained on June onward only, the long-history heads
predict the up-price tails much better (Brier of P(up & up price > 200) 0.0457 vs 0.0529, constant
0.0517; up-price q90 pinball 36.1 vs 45.1). But inside the mixture model they add nothing: hmix_v4b
(mix_v4b + these columns) scores 41.77 / 11.552 / 0.0915 / 0.3986 vs 41.71 / 11.505 / 0.0913 / 0.3952.
The mixture's own up-price head, which also sees spot, weather and market state, already beats the
history head on validation up rows (spread q90 pinball 31.2 vs 34.9, q50 28.2 vs 35.7), and blending
the two does not help. Availability check: PASS (20 origins).

Original purpose: out-of-sample tail heads as extra features for the mixture model.

Why: the organiser's training window (June - early September 2026) is unusually calm. Only 2.3 % of
up-regulated quarter-hours had an mFRR up price above 200 EUR/MWh, against 7-13 % in every earlier
period since March 2025 and 15.5 % in validation. The up-regulation price tails, which dominate the
remaining MAE, are therefore almost absent from the 4-month training data. The public Fingrid history
since the 15-min mFRR market (20 Mar 2025) has them. The organisers allow pre-June aFRR/mFRR prices and
volumes; the pre-June imbalance price is never used (not as target, not as feature).

Heads (LightGBM, features from the history series only, no spot):
- hist_p_tail200: P(up-regulated AND mFRR up price > 200 EUR/MWh) for the delivery quarter-hour;
- hist_up_px_q50 / hist_up_px_q90: quantiles of the mFRR up price given up-regulation.

Availability: every history value gets first_usable_origin_utc = end of its quarter-hour + 60 min,
rounded up to the next full hour, and is read only through features.Store.get / latest_index.
No fitting leakage: predictions for each period come from heads trained only on targets realised before
the period starts (expanding window; same segments as tools/training/hist_heads.py; the test period
uses targets up to the training cutoff only).

Steps (each fits in a short call):
    uv run python -m tools.training.hist_tails build          # feature cache
    uv run python -m tools.training.hist_tails fit --seg K     # K = 0..5, predictions per segment
    uv run python -m tools.training.hist_tails merge          # -> static_data/processed/hist_tails.parquet
    uv run python -m tools.training.hist_tails check          # availability re-check on random origins
"""
from __future__ import annotations

import argparse

import lightgbm as lgb
import numpy as np
import pandas as pd

from imbalance.features import Store, lag_window
from imbalance.paths import RAW_DIR, REPO_ROOT

from tools.training.hist_heads import HIST_START, HORIZON, LAG, LAST_ORIGIN, SEGMENTS, TRAIN_END_TARGET
from tools.training.hist_heads import features as dir_features

SRC = RAW_DIR / "fingrid_history"
PROC = REPO_ROOT / "static_data" / "processed"
CACHE = PROC / "hist_tails_feats.parquet"
OUT = PROC / "hist_tails.parquet"
SERIES = ["fi_mfrr_direction", "fi_mfrr_up_activated", "fi_mfrr_down_activated", "fi_mfrr_up_price",
          "fi_mfrr_down_price", "fi_afrr_up_volume", "fi_afrr_down_volume", "fi_wind_production",
          "fi_afrr_up_price"]
TAIL = 200.0
OUT_COLS = ["hist_p_tail200", "hist_up_px_q50", "hist_up_px_q90"]
PARAMS = dict(n_estimators=200, learning_rate=0.05, num_leaves=31, min_child_samples=200,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)


def history_long(visible_before: pd.Timestamp | None = None) -> pd.DataFrame:
    rows = []
    for sid in SERIES:
        d = pd.read_parquet(next(SRC.glob(f"*_{sid}.parquet")))
        d = d[d["timestamp_utc"] >= HIST_START - pd.Timedelta(days=8)]
        fu = (d["end_utc"] + LAG).dt.ceil("h")
        rows.append(pd.DataFrame({"series_id": sid, "timestamp_utc": d["timestamp_utc"], "value": d["value"],
                                  "first_usable_origin_utc": fu}))
    long = pd.concat(rows, ignore_index=True)
    if visible_before is not None:
        long = long[long["first_usable_origin_utc"] <= visible_before]
    return long


def features(st: Store, origins: pd.DatetimeIndex) -> pd.DataFrame:
    """Direction features of hist_heads plus the recent mFRR/aFRR price levels, and the targets."""
    df = dir_features(st, origins)
    o = pd.DatetimeIndex(origins).as_unit("ns")
    o_ns = o.asi8
    li = st.latest_index("fi_mfrr_up_price", o_ns)
    up = lag_window(st, "fi_mfrr_up_price", li, o_ns, 96)            # last 24 h
    dn = lag_window(st, "fi_mfrr_down_price", st.latest_index("fi_mfrr_down_price", o_ns), o_ns, 16)
    F = {"h_uppx_last": up[:, 0], "h_uppx_mean4": np.nanmean(up[:, :4], 1), "h_uppx_max16": np.nanmax(up[:, :16], 1),
         "h_uppx_mean96": np.nanmean(up, 1), "h_uppx_q90_96": np.nanquantile(up, 0.9, axis=1),
         "h_uppx_gt200_96": np.nanmean(up > TAIL, 1), "h_dnpx_mean16": np.nanmean(dn, 1)}
    af = lag_window(st, "fi_afrr_up_price", st.latest_index("fi_afrr_up_price", o_ns), o_ns, 16)
    F["h_afrr_uppx_max16"] = np.nanmax(np.where(np.isnan(af), -np.inf, af), 1)
    F["h_afrr_uppx_max16"] = np.where(np.isinf(F["h_afrr_uppx_max16"]), np.nan, F["h_afrr_uppx_max16"])
    rep = np.repeat(np.arange(len(o)), HORIZON)
    for k, v in F.items():
        df[k] = v[rep]
    d_idx = st.index_of(df["delivery_start_utc"])
    inside = (d_idx >= 0) & (d_idx < len(st.grid))
    px = np.where(inside, st.truth("fi_mfrr_up_price", np.clip(d_idx, 0, len(st.grid) - 1)), np.nan)
    df["y_uppx"] = px
    df["y_tail"] = np.where(df["y_up"].isna() | np.isnan(px), np.nan, ((df["y_up"] == 1) & (px > TAIL)).astype(float))
    return df


def cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("h_")]


def build() -> None:
    st = Store(history_long())
    all_o = pd.date_range(HIST_START + pd.Timedelta(days=8), LAST_ORIGIN, freq="h")
    df = features(st, all_o)
    # pre-June training rows: every second origin hour is enough (speed, disk); June on: all hourly origins
    keep = (df["forecast_origin_utc"] >= SEGMENTS[0]) | (df["forecast_origin_utc"].dt.hour % 2 == 0)
    df = df[keep].reset_index(drop=True)
    for c in cols(df) + ["y_up", "y_uppx", "y_tail"]:
        df[c] = df[c].astype("float32")
    PROC.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE, index=False)
    print(f"cache {CACHE}: {len(df):,} rows, {len(cols(df))} features")


def fit_segment(k: int, compare_short: bool) -> None:
    df = pd.read_parquet(CACHE)
    X = cols(df)
    bounds = SEGMENTS + [LAST_ORIGIN + pd.Timedelta(hours=1)]
    s, e = bounds[k], bounds[k + 1]
    cutoff = min(s - pd.Timedelta(minutes=75), TRAIN_END_TARGET)       # targets realised before s
    tr = df[(df["delivery_start_utc"] <= cutoff) & df["y_tail"].notna() & (df["step"] % 2 == 0)]
    seg = df[(df["forecast_origin_utc"] >= s) & (df["forecast_origin_utc"] < e)]
    heads = fit_heads(tr, X)
    out = predict(heads, seg, X)
    out.to_parquet(PROC / f"hist_tails_seg{k}.parquet", index=False)
    print(f"segment {k} {s:%Y-%m-%d} .. {e:%Y-%m-%d}: trained on {len(tr):,} rows to {cutoff:%Y-%m-%d %H:%M}, "
          f"predicted {len(out):,}")
    if compare_short:                   # diagnostic: long history vs the organiser window only
        ev = seg[(seg["delivery_start_utc"] <= TRAIN_END_TARGET) & seg["y_tail"].notna()]
        short = tr[tr["delivery_start_utc"] >= SEGMENTS[0]]
        ps = predict(fit_heads(short, X), ev, X)
        pl = out.loc[ev.index]
        y = ev["y_tail"].to_numpy()
        up = (ev["y_up"] == 1).to_numpy()

        def pin(q, t):
            e_ = ev["y_uppx"].to_numpy()[up] - q[up]
            return float(np.mean(np.maximum(t * e_, (t - 1) * e_)))
        print(f"  tail rate in evaluation segment {y.mean():.3f}; train long {tr['y_tail'].mean():.3f}, short {short['y_tail'].mean():.3f}")
        print(f"  Brier P(up & up price > {TAIL:.0f}): long {np.mean((pl['hist_p_tail200'].to_numpy() - y) ** 2):.4f}"
              f" | June+ only {np.mean((ps['hist_p_tail200'].to_numpy() - y) ** 2):.4f}"
              f" | constant {np.mean((short['y_tail'].mean() - y) ** 2):.4f}")
        print(f"  pinball q90 of up price on up rows: long {pin(pl['hist_up_px_q90'].to_numpy(), .9):.2f}"
              f" | June+ only {pin(ps['hist_up_px_q90'].to_numpy(), .9):.2f};"
              f"  q50: long {pin(pl['hist_up_px_q50'].to_numpy(), .5):.2f} | June+ only {pin(ps['hist_up_px_q50'].to_numpy(), .5):.2f}")


def fit_heads(tr: pd.DataFrame, X: list[str]) -> dict:
    up = tr[(tr["y_up"] == 1) & tr["y_uppx"].notna()]
    return {"tail": lgb.LGBMClassifier(**PARAMS).fit(tr[X], tr["y_tail"].astype(int)),
            "q50": lgb.LGBMRegressor(objective="quantile", alpha=0.5, **PARAMS).fit(up[X], up["y_uppx"]),
            "q90": lgb.LGBMRegressor(objective="quantile", alpha=0.9, **PARAMS).fit(up[X], up["y_uppx"])}


def predict(heads: dict, seg: pd.DataFrame, X: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"forecast_origin_utc": seg["forecast_origin_utc"].to_numpy(), "step": seg["step"].to_numpy(),
                         "hist_p_tail200": heads["tail"].predict_proba(seg[X])[:, 1],
                         "hist_up_px_q50": heads["q50"].predict(seg[X]),
                         "hist_up_px_q90": heads["q90"].predict(seg[X])}, index=seg.index)


def merge() -> None:
    parts = [pd.read_parquet(PROC / f"hist_tails_seg{k}.parquet") for k in range(len(SEGMENTS))]
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(OUT, index=False)
    print(f"wrote {OUT}: {len(out):,} rows, origins {out.forecast_origin_utc.min()} .. {out.forecast_origin_utc.max()}")


def check(n: int) -> None:
    df = pd.read_parquet(CACHE)
    X = cols(df)
    rng = np.random.default_rng(0)
    pool = df.loc[df["forecast_origin_utc"] >= SEGMENTS[0], "forecast_origin_utc"].unique()
    bad = 0
    for o in pd.DatetimeIndex(rng.choice(pool, n, replace=False)):
        ref = features(Store(history_long(visible_before=o)), pd.DatetimeIndex([o]))
        used = df[df["forecast_origin_utc"] == o].sort_values("step")
        ok = np.isclose(ref[X].to_numpy(np.float32), used[X].to_numpy(np.float32), equal_nan=True, rtol=1e-5, atol=1e-3).all()
        bad += not ok
    print(f"hist-tails availability check: {n} origins -> {'PASS' if bad == 0 else f'FAIL ({bad})'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "fit", "merge", "check"])
    ap.add_argument("--seg", type=int)
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    elif a.cmd == "fit":
        fit_segment(a.seg, compare_short=(a.seg == 4))
    elif a.cmd == "merge":
        merge()
    else:
        check(a.n)


if __name__ == "__main__":
    main()

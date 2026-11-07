"""D-lite: a long-history direction head whose out-of-sample P(up) becomes a feature (v5 / v5m).

Why: direction is defined only by mFRR activations, unchanged by the 1 June 2026 price-rule change,
so the full public history since the 15-min mFRR market (20 Mar 2025) is a consistent target, about
4x the organiser's training window. Only measured Fingrid series are used (no forecasts, no spot).

Availability: every history value gets first_usable_origin_utc = end of its quarter-hour + 60 min,
rounded up to the next full hour (the organiser's rule for these series), and is read only through
features.Store.get / latest_index, so the availability rule applies exactly as in the main model.

No fitting leakage: predictions for each period come from a head trained only on targets that were
realised before that period started (expanding window): June, July, August, early September, the
validation period (from 6 Sep 21:00 UTC) and the test period (trained on targets up to 4 Oct only).

    uv run python -m tools.training.hist_heads            # writes static_data/processed/hist_heads.parquet
    uv run python -m tools.training.hist_heads --check    # + availability re-check on random origins
"""
from __future__ import annotations

import argparse

import lightgbm as lgb
import numpy as np
import pandas as pd

from imbalance.features import Store, lag_window
from imbalance.paths import RAW_DIR, REPO_ROOT

SRC = RAW_DIR / "fingrid_history"
OUT = REPO_ROOT / "static_data" / "processed" / "hist_heads.parquet"
SERIES = ["fi_mfrr_direction", "fi_mfrr_up_activated", "fi_mfrr_down_activated", "fi_mfrr_up_price",
          "fi_mfrr_down_price", "fi_afrr_up_volume", "fi_afrr_down_volume", "fi_wind_production"]
HIST_START = pd.Timestamp("2025-03-20T00:00:00Z")     # mFRR 15-min energy market from 19 Mar 2025
LAG = pd.Timedelta(minutes=60)
TRAIN_END_TARGET = pd.Timestamp("2026-10-04T20:45:00Z")
SEGMENTS = [pd.Timestamp(t) for t in ["2026-05-31T21:00:00Z", "2026-06-30T21:00:00Z", "2026-07-31T21:00:00Z",
                                      "2026-08-31T21:00:00Z", "2026-09-06T21:00:00Z", "2026-10-04T21:00:00Z"]]
HORIZON = 40
LAST_ORIGIN = pd.Timestamp("2026-11-01T21:00:00Z")      # last organiser test origin
PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=31, min_child_samples=200,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)


def history_long(visible_before: pd.Timestamp | None = None) -> pd.DataFrame:
    rows = []
    for sid in SERIES:
        f = next(SRC.glob(f"*_{sid}.parquet"))
        d = pd.read_parquet(f)
        d = d[d["timestamp_utc"] >= HIST_START - pd.Timedelta(days=2)]
        fu = (d["end_utc"] + LAG).dt.ceil("h")
        rows.append(pd.DataFrame({"series_id": sid, "timestamp_utc": d["timestamp_utc"], "value": d["value"],
                                  "first_usable_origin_utc": fu}))
    long = pd.concat(rows, ignore_index=True)
    if visible_before is not None:                      # physically drop rows not yet usable (check)
        long = long[long["first_usable_origin_utc"] <= visible_before]
    return long


def features(st: Store, origins: pd.DatetimeIndex) -> pd.DataFrame:
    o = pd.DatetimeIndex(origins).as_unit("ns")
    o_ns = o.asi8
    F: dict[str, np.ndarray] = {}
    li = st.latest_index("fi_mfrr_direction", o_ns)
    d = lag_window(st, "fi_mfrr_direction", li, o_ns, 16)
    F["h_dir_last"] = d[:, 0]
    F["h_dir_mean4"] = np.nanmean(d[:, :4], axis=1)
    F["h_dir_mean16"] = np.nanmean(d, axis=1)
    same = d == d[:, [0]]
    F["h_dir_run_len"] = np.argmin(np.c_[same, np.zeros(len(d), bool)], axis=1).astype(float)
    for sid, name in [("fi_mfrr_up_activated", "h_up_mw"), ("fi_mfrr_down_activated", "h_dn_mw"),
                      ("fi_afrr_up_volume", "h_afrr_up"), ("fi_afrr_down_volume", "h_afrr_dn")]:
        w = lag_window(st, sid, st.latest_index(sid, o_ns), o_ns, 4)
        F[f"{name}_last"] = w[:, 0]
        F[f"{name}_mean4"] = np.nanmean(w, axis=1)
    F["h_afrr_net_mean4"] = F["h_afrr_up_mean4"] - F["h_afrr_dn_mean4"]
    pu = lag_window(st, "fi_mfrr_up_price", st.latest_index("fi_mfrr_up_price", o_ns), o_ns, 4)
    pdn = lag_window(st, "fi_mfrr_down_price", st.latest_index("fi_mfrr_down_price", o_ns), o_ns, 4)
    F["h_px_gap_last"] = pu[:, 0] - pdn[:, 0]
    F["h_px_gap_mean4"] = np.nanmean(pu - pdn, axis=1)
    wl = st.latest_index("fi_wind_production", o_ns)
    w = lag_window(st, "fi_wind_production", wl, o_ns, 13)
    F["h_wind_last"] = w[:, 0]
    F["h_wind_chg_1h"] = w[:, 0] - w[:, 4]
    F["h_wind_chg_3h"] = w[:, 0] - w[:, 12]
    o_idx = st.index_of(o)
    F["h_data_age_min"] = (o_idx - li) * 15.0
    odf = pd.DataFrame(F)
    n = len(o)
    steps = np.tile(np.arange(1, HORIZON + 1), n)
    rep = np.repeat(np.arange(n), HORIZON)
    d_idx = o_idx[rep] + steps - 1
    df = odf.iloc[rep].reset_index(drop=True)
    df.insert(0, "forecast_origin_utc", o[rep])
    df.insert(1, "step", steps)
    df["h_lead_min"] = (d_idx - li[rep]) * 15.0
    df["h_dir_same_qh_yday"] = st.get("fi_mfrr_direction", d_idx - 96, o_ns[rep])
    deliv = pd.DatetimeIndex(o[rep]) + pd.to_timedelta((steps - 1) * 15, unit="min")
    loc = deliv.tz_convert("Europe/Helsinki")
    df["h_hour"] = loc.hour.to_numpy(float)
    df["h_weekday"] = loc.day_of_week.to_numpy(float)
    df["h_quarter"] = (loc.minute // 15).to_numpy(float)
    df["delivery_start_utc"] = deliv
    inside = (d_idx >= 0) & (d_idx < len(st.grid))
    y = np.where(inside, st.truth("fi_mfrr_direction", np.clip(d_idx, 0, len(st.grid) - 1)), np.nan)
    df["y_up"] = np.where(np.isnan(y), np.nan, (y == 1).astype(float))
    return df


def cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("h_")]


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--origin-step-h", type=int, default=1, help="origin spacing for training rows (speed)")
    a = ap.parse_args()
    st = Store(history_long())
    end = max(st.grid[-1].floor("h") - pd.Timedelta(hours=10), LAST_ORIGIN)   # predict to the last test origin
    all_o = pd.date_range(HIST_START + pd.Timedelta(days=2), end, freq="h")
    df = features(st, all_o)
    X = cols(df)
    print(f"history rows {len(df):,}, origins {len(all_o):,}, features {len(X)}")
    keep = ((df["forecast_origin_utc"].dt.hour + df["step"]) % 2 == 0) & \
           (df["forecast_origin_utc"].dt.hour % a.origin_step_h == 0)
    preds = []
    bounds = SEGMENTS + [all_o[-1] + pd.Timedelta(hours=1)]
    for s, e in zip(bounds[:-1], bounds[1:]):
        cutoff = min(s - pd.Timedelta(minutes=75), TRAIN_END_TARGET)     # target realised before s
        tr = df[keep & (df["delivery_start_utc"] <= cutoff) & df["y_up"].notna()]
        m = lgb.LGBMClassifier(**PARAMS).fit(tr[X], tr["y_up"])
        seg = df[(df["forecast_origin_utc"] >= s) & (df["forecast_origin_utc"] < e)]
        p = m.predict_proba(seg[X])[:, 1]
        preds.append(pd.DataFrame({"forecast_origin_utc": seg["forecast_origin_utc"], "step": seg["step"],
                                   "hist_p_up": p}))
        ev = seg["y_up"].notna() & (seg["delivery_start_utc"] <= TRAIN_END_TARGET)
        msg = f"segment {s:%Y-%m-%d %H:%M} .. {e:%Y-%m-%d %H:%M}: trained on {len(tr):,} rows to {cutoff:%Y-%m-%d %H:%M}"
        if ev.any():
            msg += f"; Brier {brier(p[ev.to_numpy()], seg['y_up'][ev]):.4f}"
        print(msg)
        if s == SEGMENTS[4]:          # validation: does the long history help vs the organiser window only?
            short = tr[tr["delivery_start_utc"] >= SEGMENTS[0]]
            ms = lgb.LGBMClassifier(**PARAMS).fit(short[X], short["y_up"])
            ps = ms.predict_proba(seg[X])[:, 1]
            clim = np.full(ev.sum(), short["y_up"].mean())
            print(f"  validation Brier (binary P(up)): long history {brier(p[ev.to_numpy()], seg['y_up'][ev]):.4f}"
                  f" | June+ only {brier(ps[ev.to_numpy()], seg['y_up'][ev]):.4f}"
                  f" | climatology {brier(clim, seg['y_up'][ev]):.4f}")
    out = pd.concat(preds, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"wrote {OUT} ({len(out):,} rows, origins {out.forecast_origin_utc.min()} .. {out.forecast_origin_utc.max()})")
    if a.check:
        rng = np.random.default_rng(0)
        sample = pd.DatetimeIndex(rng.choice(out["forecast_origin_utc"].unique(), 30, replace=False))
        bad = 0
        for o in sample:
            ref = features(Store(history_long(visible_before=o)), pd.DatetimeIndex([o]))
            used = df[df["forecast_origin_utc"] == o].sort_values("step")
            ok = np.isclose(ref[X].to_numpy(float), used[X].to_numpy(float), equal_nan=True, rtol=0, atol=1e-9).all()
            bad += not ok
        print(f"history-head availability check: {len(sample)} origins -> {'PASS' if bad == 0 else f'FAIL ({bad})'}")


if __name__ == "__main__":
    main()

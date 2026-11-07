"""Diagnostic (not part of the submission pipeline): can a learned wind-power corrector beat Fingrid's
day-ahead wind forecast, and does it predict the wind *surprise* (actual - Fingrid DA forecast)?

Every input goes through the availability rule: observations via features.Store.get / latest_index,
NWP via per-site nwp.RunTable (newest run with first_usable_origin_utc <= origin). The target
(actual wind generation, Fingrid 75) is read with Store.truth only as the label.

Split: train on origins whose whole 10 h horizon ends before the first validation origin; validate on
validation origins (7 Sep - 4 Oct local), deliveries up to the training end. Test period untouched.

    uv run python -m tools.eval.wind_corrector
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import lightgbm as lgb

from imbalance import store as db
from imbalance.features import load_store
from imbalance.nwp import RunTable, power_curve
from imbalance.paths import REPO_ROOT

VAL_FIRST_ORIGIN = pd.Timestamp("2026-09-06T21:00:00Z")
TRAIN_END_TARGET = pd.Timestamp("2026-10-04T20:45:00Z")
MODELS = ["ecmwf_ifs", "metno_nordic"]
OUT = REPO_ROOT / "static_data" / "work" / "diagnostics"
Q = pd.Timedelta(minutes=15)


def site_tables(model: str) -> tuple[dict[str, RunTable], pd.Series]:
    runs = db.load_forecast_runs([f"om_{model}_wind_speed_100m"])
    cap = db.locations("wind")
    runs = runs[runs["location_id"].isin(cap.index)]
    return {loc: RunTable(g, "value") for loc, g in runs.groupby("location_id")}, cap


def build(st, origins: pd.DatetimeIndex) -> pd.DataFrame:
    o = np.repeat(pd.DatetimeIndex(origins).as_unit("ns").asi8, 40)
    s = np.tile(np.arange(1, 41), len(origins))
    d = o + (s - 1) * Q.value
    di = st.index_of(pd.to_datetime(d, unit="ns", utc=True))
    df = pd.DataFrame({"origin": pd.to_datetime(o, unit="ns", utc=True), "step": s, "lead_h": (s - 1) / 4})
    df["hour"] = st.get("cal_hour_local", di, o)
    df["fc_da"] = st.get("fi_wind_fc_da", di, o)
    li = st.latest_index("fi_wind_production", o)
    df["act_last"] = np.where(li >= 0, st.get("fi_wind_production", li, o), np.nan)
    df["err_last"] = df["act_last"] - np.where(li >= 0, st.get("fi_wind_fc_da", li, o), np.nan)
    df["obs_age_h"] = np.where(li >= 0, (o - st.ns[np.clip(li, 0, None)]) / 3.6e12, np.nan)
    # error trend over the last hour of observations
    li4 = li - 4
    prev_err = st.get("fi_wind_production", li4, o) - st.get("fi_wind_fc_da", li4, o)
    df["err_trend_1h"] = df["err_last"] - prev_err
    for m in MODELS:
        tabs, cap = site_tables(m)
        mw = np.zeros(len(df)); capsum = np.zeros(len(df))
        age = None
        for loc, t in tabs.items():
            r = t.latest(o)
            ws = t.at(r, o, d)
            df[f"{m}_ws_{loc}"] = ws
            ok = ~np.isnan(ws)
            mw += np.where(ok, power_curve(np.nan_to_num(ws)) * cap[loc], 0)
            capsum += np.where(ok, cap[loc], 0)
            if age is None:
                age = t.run_age_hours(r, o)
        df[f"{m}_proxy_mw"] = np.where(capsum >= 0.8 * cap.sum(), mw * cap.sum() / np.maximum(capsum, 1), np.nan)
        df[f"{m}_run_age_h"] = age
        df[f"{m}_minus_fc"] = df[f"{m}_proxy_mw"] - df["fc_da"]
    df["y"] = st.truth("fi_wind_production", di)
    df["delivery"] = pd.to_datetime(d, unit="ns", utc=True)
    return df


def fit_predict(tr, va, cols):
    p = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=100,
             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
    m = lgb.LGBMRegressor(objective="l1", **p).fit(tr[cols], tr["y"] - tr["fc_da"])
    return va["fc_da"].to_numpy() + m.predict(va[cols])


def main() -> None:
    st = load_store()
    origins = pd.date_range("2026-06-02T00:00Z", TRAIN_END_TARGET - pd.Timedelta(hours=9, minutes=45), freq="h")
    df = build(st, origins)
    df = df.dropna(subset=["y", "fc_da"])
    tr = df[(df["delivery"] < VAL_FIRST_ORIGIN)]
    va = df[(df["origin"] >= VAL_FIRST_ORIGIN) & (df["delivery"] <= TRAIN_END_TARGET)].copy()
    base = ["lead_h", "hour", "fc_da"]
    obs = ["act_last", "err_last", "obs_age_h", "err_trend_1h"]
    nwp = {m: [c for c in df.columns if c.startswith(m + "_")] for m in MODELS}
    sets = {
        "persistence-ML (fc + last obs)": base + obs,
        "ECMWF sites": base + nwp["ecmwf_ifs"],
        "MET Nordic sites": base + nwp["metno_nordic"],
        "both NWP": base + nwp["ecmwf_ifs"] + nwp["metno_nordic"],
        "both NWP + last obs": base + nwp["ecmwf_ifs"] + nwp["metno_nordic"] + obs,
    }
    va["pred_Fingrid DA forecast"] = va["fc_da"]
    va["pred_raw ECMWF proxy"] = va["ecmwf_ifs_proxy_mw"]
    va["pred_naive persistence of error"] = va["fc_da"] + va["err_last"]
    for name, cols in sets.items():
        va[f"pred_{name}"] = fit_predict(tr, va, cols)
    bucket = pd.cut(va["lead_h"], [-0.1, 1.75, 3.75, 6.75, 9.75], labels=["0-2h", "2-4h", "4-7h", "7-10h"])
    surprise = va["y"] - va["fc_da"]
    rows = []
    for c in [c for c in va.columns if c.startswith("pred_")]:
        e = (va["y"] - va[c]).abs()
        r = {"model": c[5:], "MAE all": e.mean()}
        for b in bucket.cat.categories:
            r[f"MAE {b}"] = e[bucket == b].mean()
        ps = va[c] - va["fc_da"]
        r["surprise corr"] = np.corrcoef(ps.fillna(0), surprise)[0, 1] if ps.std() > 0 else np.nan
        rows.append(r)
    res = pd.DataFrame(rows).set_index("model").round(3)
    OUT.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT / "wind_corrector.csv")
    print(f"train rows {len(tr):,}  val rows {len(va):,}  val origins {va['origin'].nunique()}")
    print("MAE in MW of national wind generation (validation); surprise corr = corr(pred - DA fc, actual - DA fc)")
    print(res.to_string())


if __name__ == "__main__":
    main()

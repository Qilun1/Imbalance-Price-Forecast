"""Leakage-safe feature table (feature set "v1") for the Turku Energia imbalance price challenge.

Every value is read through `Store.get()`, which returns NaN unless the row's
first_usable_origin_utc <= forecast origin. That is the data availability rule,
enforced at the lowest level so no feature can bypass it.

Rows are (forecast origin, step). Targets are attached only for training/eval and
are never used as features.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import store as db
from .contract import HORIZON_STEPS as HORIZON, SPIKE_MARGIN, STEP  # noqa: F401

FEATURE_SET = "v1"                 # default feature set
FEATURE_SETS = ("v1", "v2", "v2p", "v3", "v4", "v4m", "v5", "v5m")   # v2+ = v1 + vintaged NWP proxies; model per set in nwp.NWP_SPECS
WIND_OBS_SETS = {"v4", "v4m", "v5", "v5m"}     # + observed wind error vs Fingrid day-ahead forecast (Fingrid 75 vs 246)
HIST_SETS = {"v5", "v5m"}         # + out-of-sample long-history direction head (tools/training/hist_heads.py)
WIND_ERR_TAUS_H = (1, 3, 6)       # decay time constants (h) of the observed error with lead time

LAG_SERIES = [
    "fi_imbalance_price", "fi_mfrr_direction", "fi_mfrr_up_price", "fi_mfrr_down_price",
    "fi_mfrr_up_activated", "fi_mfrr_down_activated", "fi_afrr_up_price", "fi_afrr_down_price",
    "fi_consumption", "fi_production", "fi_se1_flow", "fi_se3_flow", "fi_ee_flow", "fi_no4_flow",
    "se1_imbalance_price_long", "se3_imbalance_price_long", "ee_imbalance_price_long",
    "se1_load_fc_da", "se3_load_fc_da", "ee_load_fc_da",
]
AHEAD_SERIES = [
    "fi_spot_price", "fi_wind_fc_da", "fi_consumption_fc_da", "fi_solar_fc_da",
    "fi_ee_capacity_da", "ee_fi_capacity_da",
    "cal_hour_local", "cal_weekday_local", "cal_is_holiday_fi", "cal_is_dst",
]


class Store:
    """Values and availability times on a regular 15-min grid, one column per series."""

    def __init__(self, long: pd.DataFrame):
        self.t0 = long["timestamp_utc"].min()
        n = int((long["timestamp_utc"].max() - self.t0) / STEP) + 1
        self.grid = pd.DatetimeIndex(self.t0 + STEP * np.arange(n)).as_unit("ns")
        self.ns = self.grid.asi8
        self.val: dict[str, np.ndarray] = {}
        self.fu: dict[str, np.ndarray] = {}
        for sid, g in long.groupby("series_id"):
            idx = ((g["timestamp_utc"] - self.t0) / STEP).astype(int).to_numpy()
            v = np.full(n, np.nan)
            f = np.full(n, np.iinfo(np.int64).max, dtype=np.int64)   # missing row = never usable
            v[idx] = g["value"].to_numpy(dtype=float)
            f[idx] = g["first_usable_origin_utc"].dt.as_unit("ns").astype("int64").to_numpy()
            self.val[sid], self.fu[sid] = v, f

    def index_of(self, ts) -> np.ndarray:
        return ((pd.DatetimeIndex(ts) - self.t0) / STEP).astype(int).to_numpy()

    def get(self, sid: str, idx: np.ndarray, origin_ns: np.ndarray) -> np.ndarray:
        """Value at grid index idx, or NaN if outside the grid or not yet usable at the origin."""
        idx = np.asarray(idx)
        ok = (idx >= 0) & (idx < len(self.grid))
        safe = np.clip(idx, 0, len(self.grid) - 1)
        usable = ok & (self.fu[sid][safe] <= origin_ns)
        return np.where(usable, self.val[sid][safe], np.nan)

    def latest_index(self, sid: str, origin_ns: np.ndarray) -> np.ndarray:
        """Grid index of the latest row usable at each origin (-1 if none).

        Searches only rows that exist (missing source rows have no availability time), so gaps never
        make it pick an older row. Availability times of existing rows are monotonic in timestamp
        (asserted in load_store)."""
        f = self.fu[sid]
        present = np.flatnonzero(f != np.iinfo(np.int64).max)
        k = np.searchsorted(f[present], origin_ns, side="right") - 1
        return np.where(k >= 0, present[np.clip(k, 0, None)], -1)

    def truth(self, sid: str, idx: np.ndarray) -> np.ndarray:
        """Unmasked value: ONLY for targets, never for features."""
        return self.val[sid][np.clip(idx, 0, len(self.grid) - 1)]


def lag_window(store: Store, sid: str, last: np.ndarray, o: np.ndarray, k: int) -> np.ndarray:
    """Matrix (origins x k) of the k latest usable values, newest first."""
    return np.column_stack([store.get(sid, last - j, o) for j in range(k)])


def build(store: Store, origins: pd.DatetimeIndex, with_targets: bool, nwp: tuple | None = None,
          wind_obs: bool = False, hist: pd.DataFrame | None = None) -> pd.DataFrame:
    """Feature rows for (origin, step). nwp = (wind RunTable, temp RunTable) adds the v2 weather columns;
    wind_obs adds the observed wind-error columns (v4)."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # nanmean of all-NaN windows -> NaN is intended
        df = _build(store, origins, with_targets)
        if nwp is not None:
            df = add_nwp(df, *nwp)
        if wind_obs:
            df = add_wind_obs(df, store)
        if hist is not None:
            df = add_hist(df, hist)
        return df


def load_hist() -> pd.DataFrame:
    """Precomputed out-of-sample P(up) of the long-history head (see tools/training/hist_heads.py)."""
    from .paths import PROCESSED_DIR
    p = PROCESSED_DIR / "hist_heads.parquet"
    if not p.exists():
        raise RuntimeError("hist_heads.parquet missing: run `uv run python -m tools.training.hist_heads`")
    return pd.read_parquet(p)


def add_hist(df: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """v5: merge the long-history head's P(up) by (origin, step); origins it does not cover stay NaN."""
    h = hist.assign(forecast_origin_utc=pd.to_datetime(hist["forecast_origin_utc"], utc=True))
    key = df[["forecast_origin_utc", "step"]].assign(
        forecast_origin_utc=pd.to_datetime(df["forecast_origin_utc"], utc=True))
    m = key.merge(h[["forecast_origin_utc", "step", "hist_p_up"]], on=["forecast_origin_utc", "step"], how="left")
    out = df.copy()
    out["hist_p_up"] = m["hist_p_up"].to_numpy()
    return out


def add_wind_obs(df: pd.DataFrame, store: Store) -> pd.DataFrame:
    """v4: observed wind error = actual wind generation (Fingrid 75) minus Fingrid's day-ahead wind
    forecast for the same quarter-hours, from the latest rows usable at the origin, and its expected
    persistence at the delivery time (exponential decay with lead time). Both series are read with
    Store.get, so the availability rule applies."""
    out = df.copy()
    origins = pd.DatetimeIndex(df["forecast_origin_utc"].unique()).as_unit("ns")
    o_ns = origins.asi8
    li = store.latest_index("fi_wind_production", o_ns)
    act = lag_window(store, "fi_wind_production", li, o_ns, 4)
    fc = lag_window(store, "fi_wind_fc_da", li, o_ns, 4)
    err = act - fc
    per_origin = pd.DataFrame({
        "wind_err_last": err[:, 0],
        "wind_err_mean4": np.nanmean(err, axis=1),
        "wind_err_trend_1h": err[:, 0] - err[:, 3],
        "wind_act_last": act[:, 0],
        "wind_obs_idx": li.astype(float),
    }, index=origins)
    o_key = pd.DatetimeIndex(df["forecast_origin_utc"]).as_unit("ns")
    rows = per_origin.reindex(o_key)
    for c in ["wind_err_last", "wind_err_mean4", "wind_err_trend_1h", "wind_act_last"]:
        out[c] = rows[c].to_numpy()
    d_idx = store.index_of(df["delivery_start_utc"])
    lead_h = (d_idx - rows["wind_obs_idx"].to_numpy()) / 4.0
    out["wind_obs_lead_h"] = lead_h
    for tau in WIND_ERR_TAUS_H:
        out[f"wind_err_decay_{tau}h"] = out["wind_err_last"] * np.exp(-lead_h / tau)
    out["wind_fc_corrected"] = out["wind_fc"] + out["wind_err_decay_3h"]
    out["resid_load_corrected"] = out["resid_load_fc"] - out["wind_err_decay_3h"]
    # data_cutoff_utc must cover the newest realised quarter-hour now used
    wind_cut = store.grid[np.clip(li, 0, None)].asi8
    cut = np.maximum(df["data_cutoff_utc"].dt.as_unit("ns").astype("int64").to_numpy(),
                     pd.Series(wind_cut, index=origins).reindex(o_key).to_numpy())
    out["data_cutoff_utc"] = pd.to_datetime(np.minimum(cut, o_key.asi8), utc=True)
    return out


def add_nwp(df: pd.DataFrame, wind, temp) -> pd.DataFrame:
    """v2 weather features from the newest NWP run usable at each origin (and the run before it)."""
    o = df["forecast_origin_utc"].dt.as_unit("ns").astype("int64").to_numpy()
    d = df["delivery_start_utc"].dt.as_unit("ns").astype("int64").to_numpy()
    out = df.copy()
    if wind is not None:
        r = wind.latest(o)
        mw = wind.at(r, o, d)
        prev = wind.at(r - 1, o, d)
        out["nwp_wind_mw"] = mw
        out["nwp_wind_minus_fingrid_fc"] = mw - out["wind_fc"]
        out["nwp_wind_run_change"] = mw - prev
        out["nwp_wind_ramp_1h"] = mw - wind.at(r, o, d - 3_600_000_000_000)
        out["nwp_run_age_h"] = wind.run_age_hours(r, o)
    if temp is not None:
        r = temp.latest(o)
        t = temp.at(r, o, d)
        out["nwp_temp_c"] = t
        out["nwp_temp_change_vs_origin"] = t - temp.at(r, o, o)
    return out


def _build(store: Store, origins: pd.DatetimeIndex, with_targets: bool) -> pd.DataFrame:
    origins = pd.DatetimeIndex(origins).as_unit("ns")
    o_ns = origins.asi8
    o_idx = store.index_of(origins)
    feats: dict[str, np.ndarray] = {}

    # ---------- origin-level features (latest known state) ----------
    last_imb = store.latest_index("fi_imbalance_price", o_ns)
    imb = lag_window(store, "fi_imbalance_price", last_imb, o_ns, 16)
    spot_at_lag = lag_window(store, "fi_spot_price", last_imb, o_ns, 16)
    spr = imb - spot_at_lag
    feats["imb_last"] = imb[:, 0]
    feats["spread_last"] = spr[:, 0]
    feats["spread_mean4"] = np.nanmean(spr[:, :4], axis=1)
    feats["spread_mean16"] = np.nanmean(spr, axis=1)
    feats["spread_std16"] = np.nanstd(spr, axis=1)
    feats["spread_max16"] = np.nanmax(spr, axis=1)
    feats["spread_min16"] = np.nanmin(spr, axis=1)
    feats["data_age_min"] = (o_idx - last_imb) * 15.0

    d = lag_window(store, "fi_mfrr_direction", store.latest_index("fi_mfrr_direction", o_ns), o_ns, 16)
    feats["dir_last"] = d[:, 0]
    feats["dir_mean4"] = np.nanmean(d[:, :4], axis=1)
    feats["dir_mean16"] = np.nanmean(d, axis=1)
    same = (d == d[:, [0]])
    feats["dir_run_len"] = np.argmin(np.c_[same, np.zeros(len(d), bool)], axis=1).astype(float)

    for sid, name in [("fi_mfrr_up_activated", "mfrr_up_mw"), ("fi_mfrr_down_activated", "mfrr_dn_mw")]:
        w = lag_window(store, sid, store.latest_index(sid, o_ns), o_ns, 4)
        feats[f"{name}_last"] = w[:, 0]
        feats[f"{name}_mean4"] = np.nanmean(w, axis=1)
    for sid, name in [("fi_mfrr_up_price", "mfrr_up_px"), ("fi_mfrr_down_price", "mfrr_dn_px"),
                      ("fi_afrr_up_price", "afrr_up_px"), ("fi_afrr_down_price", "afrr_dn_px")]:
        li = store.latest_index("fi_imbalance_price", o_ns)   # same lag group; sparse aFRR -> NaN
        w = lag_window(store, sid, li, o_ns, 4)
        feats[f"{name}_vs_spot_last"] = w[:, 0] - spot_at_lag[:, 0]
        feats[f"{name}_vs_spot_mean4"] = np.nanmean(w - spot_at_lag[:, :4], axis=1)

    li = store.latest_index("fi_consumption", o_ns)
    cons = lag_window(store, "fi_consumption", li, o_ns, 4)
    prod = lag_window(store, "fi_production", li, o_ns, 4)
    cons_fc_then = lag_window(store, "fi_consumption_fc_da", li, o_ns, 4)
    feats["cons_last"] = cons[:, 0]
    feats["cons_err_mean4"] = np.nanmean(cons - cons_fc_then, axis=1)
    feats["net_pos_last"] = prod[:, 0] - cons[:, 0]
    wind_fc_then = lag_window(store, "fi_wind_fc_da", li, o_ns, 4)
    # production actual minus (cons forecast) is a proxy of unforecast supply incl. wind error
    feats["prod_minus_consfc_mean4"] = np.nanmean(prod - cons_fc_then, axis=1)
    feats["wind_fc_at_lag"] = wind_fc_then[:, 0]
    flows = 0.0
    for sid in ["fi_se1_flow", "fi_se3_flow", "fi_ee_flow", "fi_no4_flow"]:
        w = lag_window(store, sid, store.latest_index(sid, o_ns), o_ns, 4)
        feats[f"{sid[3:]}_last"] = w[:, 0]
        flows = flows + np.nan_to_num(w[:, 0])
    feats["net_export_last"] = flows

    for sid in ["se1_imbalance_price_long", "se3_imbalance_price_long", "ee_imbalance_price_long"]:
        w = lag_window(store, sid, store.latest_index(sid, o_ns), o_ns, 4)
        feats[f"{sid[:3]}_imb_mean4"] = np.nanmean(w, axis=1)
    feats["se3imb_vs_fispot"] = feats["se3_imb_mean4"] - np.nanmean(spot_at_lag[:, :4], axis=1)

    origin_df = pd.DataFrame(feats)

    # ---------- expand to (origin, step) ----------
    n_o = len(origins)
    steps = np.tile(np.arange(1, HORIZON + 1), n_o)
    rep = np.repeat(np.arange(n_o), HORIZON)
    d_idx = o_idx[rep] + steps - 1
    o_rep = o_ns[rep]
    df = origin_df.iloc[rep].reset_index(drop=True)
    df.insert(0, "forecast_origin_utc", origins[rep])
    df.insert(1, "delivery_start_utc", store.grid[d_idx])
    df.insert(2, "step", steps)
    df["lead_min"] = (d_idx - last_imb[rep]) * 15.0

    spot_d = store.get("fi_spot_price", d_idx, o_rep)
    if np.isnan(spot_d).any():
        raise RuntimeError("spot not usable for some delivery quarter-hours")
    df["spot"] = spot_d
    df["spot_prev"] = store.get("fi_spot_price", d_idx - 1, o_rep)
    df["spot_next"] = store.get("fi_spot_price", d_idx + 1, o_rep)
    df["spot_ramp"] = df["spot"] - df["spot_prev"]
    hz = np.column_stack([store.get("fi_spot_price", o_idx + j, o_ns) for j in range(HORIZON)])
    df["spot_vs_horizon_mean"] = df["spot"] - np.repeat(np.nanmean(hz, axis=1), HORIZON)
    df["spot_vs_last_known_spot"] = df["spot"] - spot_at_lag[rep, 0]

    for sid, name in [("fi_wind_fc_da", "wind_fc"), ("fi_consumption_fc_da", "cons_fc"),
                      ("fi_solar_fc_da", "solar_fc"), ("fi_ee_capacity_da", "cap_fi_ee"),
                      ("ee_fi_capacity_da", "cap_ee_fi")]:
        df[name] = store.get(sid, d_idx, o_rep)
    df["wind_fc_ramp"] = df["wind_fc"] - store.get("fi_wind_fc_da", d_idx - 4, o_rep)
    df["resid_load_fc"] = df["cons_fc"] - df["wind_fc"] - df["solar_fc"]
    df["wind_fc_change_vs_lag"] = df["wind_fc"] - origin_df["wind_fc_at_lag"].iloc[rep].to_numpy()
    df["cons_fc_vs_last_cons"] = df["cons_fc"] - origin_df["cons_last"].iloc[rep].to_numpy()

    df["hour_local"] = store.get("cal_hour_local", d_idx, o_rep)
    df["weekday"] = store.get("cal_weekday_local", d_idx, o_rep)
    df["holiday"] = store.get("cal_is_holiday_fi", d_idx, o_rep)
    df["quarter"] = (d_idx % 4).astype(float)

    if with_targets:
        imb_t = store.truth("fi_imbalance_price", d_idx)
        df["y_price"] = imb_t
        df["y_spread"] = imb_t - spot_d
        df["y_dir"] = store.truth("fi_mfrr_direction", d_idx)
        df["y_target_fu"] = pd.to_datetime(store.fu["fi_imbalance_price"][np.clip(d_idx, 0, len(store.grid) - 1)], utc=True)
    # data_cutoff_utc: start of the latest realised quarter-hour used by any lag feature (<= origin)
    lag_used = ["fi_imbalance_price", "fi_mfrr_direction", "fi_mfrr_up_activated", "fi_mfrr_down_activated",
                "fi_consumption", "fi_production", "fi_se1_flow", "fi_se3_flow", "fi_ee_flow", "fi_no4_flow",
                "se1_imbalance_price_long", "se3_imbalance_price_long", "ee_imbalance_price_long"]
    latest = np.max([store.latest_index(s_, o_ns) for s_ in lag_used], axis=0)
    cutoff_ns = np.minimum(store.grid[np.clip(latest, 0, None)].asi8, o_ns)
    df["data_cutoff_utc"] = pd.to_datetime(np.repeat(cutoff_ns, HORIZON), utc=True)
    return df


FEATURES_EXCLUDE = {"forecast_origin_utc", "delivery_start_utc", "y_price", "y_spread", "y_dir",
                    "y_target_fu", "data_cutoff_utc"}


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in FEATURES_EXCLUDE]


def load_store() -> Store:
    """Store over every observation series in static_data/static.duckdb."""
    long = db.load_observations()
    if long.empty:
        raise RuntimeError("static store is empty: run `uv run python -m tools.cli ingest starter --src ...`")
    st = Store(long)
    for sid, f in st.fu.items():
        present = f[f != np.iinfo(np.int64).max]
        assert np.all(np.diff(present) >= 0), f"availability not monotonic for {sid}"
    return st


def build_table(origins: pd.DatetimeIndex | None = None, with_targets: bool = True,
                feature_set: str = FEATURE_SET) -> pd.DataFrame:
    """Feature table for the given origins (default: every full hour with enough history)."""
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"unknown feature set {feature_set!r}; available {FEATURE_SETS}")
    st = load_store()
    nwp_tables = None
    if feature_set != "v1":
        from . import nwp
        nwp_tables = nwp.load_for(feature_set)
        if nwp_tables[0] is None or nwp_tables[1] is None:
            model, grp = nwp.NWP_SPECS[feature_set]
            raise RuntimeError(f"feature set {feature_set} needs {model} runs for wind and {grp} sites: run "
                               f"`uv run python -m tools.cli ingest openmeteo --models {model} --group ...`")
    if origins is None:
        first = (st.grid[0] + pd.Timedelta(hours=27)).ceil("h")
        last = (st.grid[-1] - pd.Timedelta(hours=9, minutes=45)).floor("h")
        origins = pd.date_range(first, last, freq="h")
    return build(st, pd.DatetimeIndex(origins), with_targets=with_targets, nwp=nwp_tables,
                 wind_obs=feature_set in WIND_OBS_SETS,
                 hist=load_hist() if feature_set in HIST_SETS else None)

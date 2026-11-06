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

FEATURE_SET = "v1"

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
        """Grid index of the latest row usable at each origin (-1 if none)."""
        f = self.fu[sid]
        # availability times are monotonic in timestamp for every series (checked in __main__)
        return np.searchsorted(f, origin_ns, side="right") - 1

    def truth(self, sid: str, idx: np.ndarray) -> np.ndarray:
        """Unmasked value: ONLY for targets, never for features."""
        return self.val[sid][np.clip(idx, 0, len(self.grid) - 1)]


def lag_window(store: Store, sid: str, last: np.ndarray, o: np.ndarray, k: int) -> np.ndarray:
    """Matrix (origins x k) of the k latest usable values, newest first."""
    return np.column_stack([store.get(sid, last - j, o) for j in range(k)])


def build(store: Store, origins: pd.DatetimeIndex, with_targets: bool) -> pd.DataFrame:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # nanmean of all-NaN windows -> NaN is intended
        return _build(store, origins, with_targets)


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
    df["data_cutoff_utc"] = pd.to_datetime(
        np.repeat(np.minimum(store.grid[np.clip(last_imb, 0, None)].asi8, o_ns), HORIZON), utc=True)
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


def build_table(origins: pd.DatetimeIndex | None = None, with_targets: bool = True) -> pd.DataFrame:
    """Feature table for the given origins (default: every full hour with enough history)."""
    st = load_store()
    if origins is None:
        first = (st.grid[0] + pd.Timedelta(hours=27)).ceil("h")
        last = (st.grid[-1] - pd.Timedelta(hours=9, minutes=45)).floor("h")
        origins = pd.date_range(first, last, freq="h")
    return build(st, pd.DatetimeIndex(origins), with_targets=with_targets)

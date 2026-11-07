"""Vintaged NWP -> national weather proxies, read with the availability rule.

From the `forecast_runs` table (one row per series, location, run, valid hour):
- wind: capacity-weighted national wind power proxy (MW) from 100 m wind speed through a generic
  turbine power curve;
- temperature: capacity-weighted mean 2 m temperature (a rough demand proxy).

`RunTable.at()` returns, for each (origin, delivery) pair, the value from the newest run whose
first_usable_origin_utc <= origin (and optionally the run before it), linearly interpolated from hourly
valid times to the quarter-hour. Runs not yet usable at the origin are never touched.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import store as db

WIND_SERIES = "om_ecmwf_ifs_wind_speed_100m"
TEMP_SERIES = "om_ecmwf_ifs_temperature_2m"
HOUR_NS = 3_600_000_000_000


def power_curve(v: np.ndarray, cut_in: float = 3.0, rated: float = 12.0, cut_out: float = 25.0) -> np.ndarray:
    """Generic normalised power curve (0..1): cubic between cut-in and rated, flat to cut-out."""
    p = (np.clip(v, cut_in, rated) ** 3 - cut_in ** 3) / (rated ** 3 - cut_in ** 3)
    return np.where(v >= cut_out, 0.0, p)


class RunTable:
    """National series per run on an hourly valid-time grid, sorted by availability time."""

    def __init__(self, runs: pd.DataFrame, value_col: str):
        runs = runs.sort_values(["first_usable_origin_utc", "run_init_utc", "valid_time_utc"])
        keys = runs[["run_init_utc", "first_usable_origin_utc"]].drop_duplicates().reset_index(drop=True)
        self.fu = keys["first_usable_origin_utc"].dt.as_unit("ns").astype("int64").to_numpy()
        self.init = keys["run_init_utc"].dt.as_unit("ns").astype("int64").to_numpy()
        assert np.all(np.diff(self.fu) >= 0)
        v_ns = runs["valid_time_utc"].dt.as_unit("ns").astype("int64").to_numpy()
        self.h0 = v_ns.min() // HOUR_NS
        n_h = int(v_ns.max() // HOUR_NS - self.h0) + 1
        self.grid = np.full((len(keys), n_h), np.nan)
        r_idx = pd.MultiIndex.from_frame(keys[["run_init_utc", "first_usable_origin_utc"]]).get_indexer(
            pd.MultiIndex.from_frame(runs[["run_init_utc", "first_usable_origin_utc"]]))
        self.grid[r_idx, v_ns // HOUR_NS - self.h0] = runs[value_col].to_numpy(float)

    def latest(self, origin_ns: np.ndarray) -> np.ndarray:
        """Index of the newest run usable at each origin (-1 if none)."""
        return np.searchsorted(self.fu, origin_ns, side="right") - 1

    def at(self, run_idx: np.ndarray, origin_ns: np.ndarray, delivery_ns: np.ndarray) -> np.ndarray:
        """Run value at delivery time, interpolated from hourly valid times; NaN if the run is not usable."""
        ok = (run_idx >= 0)
        r = np.clip(run_idx, 0, len(self.fu) - 1)
        ok &= self.fu[r] <= origin_ns                       # availability rule, enforced again here
        h = delivery_ns / HOUR_NS - self.h0
        h0 = np.floor(h).astype(int)
        frac = h - h0
        n = self.grid.shape[1]
        a = np.where((h0 >= 0) & (h0 < n), self.grid[r, np.clip(h0, 0, n - 1)], np.nan)
        b = np.where((h0 + 1 >= 0) & (h0 + 1 < n), self.grid[r, np.clip(h0 + 1, 0, n - 1)], np.nan)
        val = np.where(frac == 0, a, a + frac * (b - a))
        return np.where(ok, val, np.nan)

    def run_age_hours(self, run_idx: np.ndarray, origin_ns: np.ndarray) -> np.ndarray:
        r = np.clip(run_idx, 0, len(self.fu) - 1)
        return np.where(run_idx >= 0, (origin_ns - self.init[r]) / HOUR_NS, np.nan)


def national_runs(runs: pd.DataFrame, capacity: pd.Series,
                  temp_weights: pd.Series | None = None, model: str = "ecmwf_ifs") -> tuple[RunTable | None, RunTable | None]:
    """Aggregate per-location runs to national wind MW and weighted temperature (population weights if
    given, else wind-capacity weights)."""
    if runs.empty:
        return None, None
    all_runs = runs
    runs = runs[runs["location_id"].isin(capacity.index)].copy()
    runs["cap"] = runs["location_id"].map(capacity).astype(float)
    keys = ["run_init_utc", "first_usable_origin_utc", "valid_time_utc"]
    wind = temp = None
    wind_series, temp_series = series_ids(model)
    w = runs[runs["series_id"] == wind_series]
    if not w.empty:
        w = w.assign(mw=power_curve(w["value"].to_numpy(float)) * w["cap"])
        g = w.groupby(keys, as_index=False).agg(mw=("mw", "sum"), cap=("cap", "sum"))
        g = g[g["cap"] >= 0.8 * capacity.sum()]          # skip valid times with missing locations
        wind = RunTable(g, "mw")
    if temp_weights is not None and not temp_weights.empty:
        t = all_runs[(all_runs["series_id"] == temp_series) & all_runs["location_id"].isin(temp_weights.index)].copy()
        t["cap"] = t["location_id"].map(temp_weights).astype(float)
        full = temp_weights.sum()
    else:
        t = runs[runs["series_id"] == temp_series]
        full = capacity.sum()
    if not t.empty:
        t = t.assign(wt=t["value"] * t["cap"])
        g = t.groupby(keys, as_index=False).agg(wt=("wt", "sum"), cap=("cap", "sum"))
        g = g[g["cap"] >= 0.8 * full]
        g["temp"] = g["wt"] / g["cap"]
        temp = RunTable(g, "temp")
    return wind, temp


def series_ids(model: str) -> tuple[str, str]:
    return f"om_{model}_wind_speed_100m", f"om_{model}_temperature_2m"


# feature set -> (NWP model, temperature weighting). v2 is kept unchanged for reproducibility.
NWP_SPECS = {"v2": ("ecmwf_ifs", "wind"),
             "v2p": ("ecmwf_ifs", "pop"),       # ECMWF wind + population-weighted temperature
             "v3": ("metno_nordic", "pop"),     # MET Nordic (MEPS 2.5 km) wind + population-weighted temperature
             "v4": ("ecmwf_ifs", "wind"),       # v2 + observed wind error (features.WIND_OBS_SETS)
             "v4m": ("metno_nordic", "pop"),    # v3 + observed wind error
             "v5": ("ecmwf_ifs", "wind"),       # v4 + long-history direction head
             "v5m": ("metno_nordic", "pop"),    # v4m + long-history direction head
             "v6": ("ecmwf_ifs", "wind"),       # v4 + second NWP model and forecast disagreement
             "v6m": ("metno_nordic", "pop"),
             "v7": ("ecmwf_ifs", "wind"),       # v4 + system stress (nuclear, hydro, import-link saturation)
             "v7m": ("metno_nordic", "pop"),    # v4m + system stress
             "v8": ("ecmwf_ifs", "wind"),       # v4 + UMM outage messages (backend/imbalance/umm.py)
             "v8m": ("metno_nordic", "pop"),
             "v9": ("ecmwf_ifs", "wind"),       # v4 + fresh grid state (features.add_grid_state)
             "v9m": ("metno_nordic", "pop")}    # v4m + fresh grid state    # v4m + UMM outage messages    # v4m + second NWP model and forecast disagreement

# feature set -> the OTHER NWP model, used only for its wind (disagreement = weather uncertainty proxy)
NWP_SECOND = {"v6": "metno_nordic", "v6m": "ecmwf_ifs"}


def load(visible_before=None, temp_group: str = "wind",
         model: str = "ecmwf_ifs") -> tuple[RunTable | None, RunTable | None]:
    """Load national run tables from the store. `visible_before` (origin) drops later runs entirely
    (used by the leakage check)."""
    runs = db.load_forecast_runs(list(series_ids(model)))
    if visible_before is not None and not runs.empty:
        runs = runs[runs["first_usable_origin_utc"] <= visible_before]
    if runs.empty:
        return None, None
    capacity = db.locations("wind")
    if capacity.empty:
        raise RuntimeError("no NWP locations registered: run `uv run python -m tools.cli ingest locations`")
    temp_w = db.locations("pop") if temp_group == "pop" else None
    if temp_w is not None and temp_w.empty:
        raise RuntimeError("population locations not registered: run `uv run python -m tools.cli ingest locations`")
    return national_runs(runs, capacity, temp_w, model)


def load_for(feature_set: str, visible_before=None):
    model, temp_group = NWP_SPECS[feature_set]
    return load(visible_before=visible_before, temp_group=temp_group, model=model)


def load_second(feature_set: str, visible_before=None) -> RunTable | None:
    """Wind RunTable of the second NWP model for feature sets in NWP_SECOND (else None). Same
    availability rule: each run is usable from its own first_usable_origin_utc."""
    if feature_set not in NWP_SECOND:
        return None
    return load(visible_before=visible_before, temp_group="wind", model=NWP_SECOND[feature_set])[0]

"""UMM (Nord Pool REMIT urgent market messages) features, with every message VERSION used only from its
own publication time.

Source: static_data/raw/umm/umm_periods.parquet from tools/ingest/umm.py (one row per message version x
unit x time period). Availability (AGENTS.md rule 4): a version is usable from the first full hour at
or after publicationDate + 5 min (UMM publication time is the platform's own timestamp; 5 min margin
for API propagation). At origin t we take, per message, the latest version usable at t (never the
API's `isOutdated` flag, which is computed as of today and would leak later updates). Versions with
eventStatus != 1 (e.g. dismissed) at that point remove the message.

Per (origin, delivery quarter-hour) features, in MW unavailable at the delivery time:
- umm_unplanned_gen_mw   Finnish production/generation units, unplanned (unavailabilityType 1)
- umm_planned_gen_mw     same, planned (unavailabilityType 2)
- umm_nuclear_mw         Finnish nuclear units (fuelType 14), any type
- umm_import_loss_mw     interconnectors into Finland ("SE1 → FI", "SE3 → FI", "EE → FI", "NO4 → FI")
- umm_new_unplanned_mw   unplanned generation MW at the delivery time from messages first published in
                         the 3 h before the origin (fresh trips)
and per origin: umm_hours_since_trip, hours since the latest unplanned generation message >= 100 MW.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .paths import RAW_DIR

UMM_FILE = RAW_DIR / "umm" / "umm_periods.parquet"
PUBLICATION_MARGIN = pd.Timedelta(minutes=5)
GEN_KINDS = ("productionUnits", "generationUnits")
IMPORT_LINKS = ("SE1 → FI", "SE3 → FI", "EE → FI", "NO4 → FI")
FRESH_H = 3
TRIP_MW = 100.0
COLUMNS = ["umm_unplanned_gen_mw", "umm_planned_gen_mw", "umm_nuclear_mw", "umm_import_loss_mw",
           "umm_new_unplanned_mw", "umm_hours_since_trip"]


def load_periods(visible_before=None) -> pd.DataFrame:
    """Unit-period rows with their usable time. `visible_before` (origin) physically drops versions not
    yet usable (leakage check)."""
    if not UMM_FILE.exists():
        raise RuntimeError("UMM data missing: run `uv run python -m tools.ingest.umm` (needs internet)")
    u = pd.read_parquet(UMM_FILE)
    u = u[u["publication_utc"].notna()].copy()
    u["usable_utc"] = (u["publication_utc"] + PUBLICATION_MARGIN).dt.ceil("h")
    if visible_before is not None:
        u = u[u["usable_utc"] <= pd.Timestamp(visible_before)]
    gen = u["unit_kind"].isin(GEN_KINDS) & u["area"].eq("FI")
    u["cat_unplanned"] = gen & u["unavailability_type"].eq(1)
    u["cat_planned"] = gen & u["unavailability_type"].eq(2)
    u["cat_nuclear"] = gen & u["fuel"].eq(14)
    u["cat_import"] = u["unit_kind"].eq("transmissionUnits") & u["unit_name"].isin(IMPORT_LINKS)
    keep = u[["cat_unplanned", "cat_planned", "cat_nuclear", "cat_import"]].any(axis=1)
    cols = ["message_id", "version", "publication_utc", "usable_utc", "event_status", "start_utc", "stop_utc",
            "unavailable_mw", "cat_unplanned", "cat_planned", "cat_nuclear", "cat_import"]
    u = u.loc[keep, cols].dropna(subset=["start_utc", "stop_utc"])
    u["unavailable_mw"] = u["unavailable_mw"].fillna(0.0).astype(float)
    # first publication of each message (in our data) for "fresh trip" features
    first = u.groupby("message_id")["publication_utc"].transform("min")
    u["first_pub_utc"] = first
    return u.sort_values("usable_utc").reset_index(drop=True)


def add_umm(df: pd.DataFrame, periods: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    o_all = pd.DatetimeIndex(df["forecast_origin_utc"])
    res = np.full((len(df), len(COLUMNS)), np.nan)
    usable = periods["usable_utc"].dt.as_unit("ns").astype("int64").to_numpy()      # sorted ascending
    for o, idx in pd.Series(np.arange(len(df))).groupby(o_all).groups.items():
        rows = np.asarray(idx)
        p = periods.iloc[: np.searchsorted(usable, pd.Timestamp(o).value, side="right")]   # usable at o only
        if p.empty:
            res[rows] = 0.0
            res[rows, -1] = np.nan
            continue
        latest = p.groupby("message_id")["version"].transform("max")
        p = p[(p["version"] == latest) & (p["event_status"] == 1)]
        d = pd.DatetimeIndex(df["delivery_start_utc"].iloc[rows])
        d_ns = d.asi8[:, None]
        s_ns, e_ns = p["start_utc"].dt.as_unit("ns").astype("int64").to_numpy(), p["stop_utc"].dt.as_unit("ns").astype("int64").to_numpy()
        cover = (s_ns[None, :] <= d_ns) & (d_ns < e_ns[None, :])
        mw = p["unavailable_mw"].to_numpy()
        for j, cat in enumerate(("cat_unplanned", "cat_planned", "cat_nuclear", "cat_import")):
            res[rows, j] = cover @ (mw * p[cat].to_numpy())
        fresh = (p["cat_unplanned"] & (p["first_pub_utc"] > o - pd.Timedelta(hours=FRESH_H))).to_numpy()
        res[rows, 4] = cover @ (mw * fresh)
        trips = p[p["cat_unplanned"] & (p["unavailable_mw"] >= TRIP_MW)]
        res[rows, 5] = (o - trips["first_pub_utc"].max()).total_seconds() / 3600 if len(trips) else np.nan
    for j, c in enumerate(COLUMNS):
        out[c] = res[:, j]
    return out

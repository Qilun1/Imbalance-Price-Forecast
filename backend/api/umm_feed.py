"""UMM alert feed for the dashboard: Nord Pool urgent market messages that matter for the next hours.

Turku Energia's traders check UMM first when something happens. This feed shows, at a viewing time
`as_of`, the messages known by then (each version usable from the first full hour after its
publication + 5 min, the same rule as the v8 features in imbalance/umm.py; the latest usable version
per message, never later updates), that affect Finland's supply or import capacity during the next
`hours` hours, with a link to the message on umm.nordpoolgroup.com.

Ordering: unplanned before planned, then newest publication first. "fresh" marks messages first
published in the last 3 hours (the trips that move the balancing price).
"""
from __future__ import annotations

import pandas as pd

from imbalance.umm import IMPORT_LINKS, PUBLICATION_MARGIN, UMM_FILE

LINK = "https://umm.nordpoolgroup.com/#/messages/{message_id}/{version}"
FUELS = {14: "nuclear", 19: "wind", 1: "biomass", 4: "fossil gas", 5: "hard coal", 6: "oil", 8: "peat",
         17: "solar"}
KINDS = {"productionUnits": "generation", "generationUnits": "generation", "consumptionUnits": "consumption",
         "transmissionUnits": "transmission"}


def available() -> bool:
    return UMM_FILE.exists()


def umm_feed(as_of: pd.Timestamp, hours: float = 10.0, min_mw: float = 50.0, fresh_hours: float = 3.0) -> list[dict]:
    if not available():
        return []
    u = pd.read_parquet(UMM_FILE)
    u = u[u["publication_utc"].notna()].copy()
    u["usable_utc"] = (u["publication_utc"] + PUBLICATION_MARGIN).dt.ceil("h")
    u = u[u["usable_utc"] <= as_of]
    if u.empty:
        return []
    u = u[u["version"] == u.groupby("message_id")["version"].transform("max")]
    first_pub = pd.read_parquet(UMM_FILE, columns=["message_id", "publication_utc"]).groupby("message_id")["publication_utc"].min()
    relevant = ((u["unit_kind"].isin(["productionUnits", "generationUnits"]) & u["area"].eq("FI"))
                | (u["unit_kind"].eq("transmissionUnits") & u["unit_name"].isin(IMPORT_LINKS)))
    end = as_of + pd.Timedelta(hours=hours)
    u = u[relevant & u["event_status"].eq(1) & (u["start_utc"] < end) & (u["stop_utc"] > as_of)
          & (u["unavailable_mw"].fillna(0) >= min_mw)]
    out = []
    for (mid, ver), g in u.groupby(["message_id", "version"]):
        r = g.iloc[0]
        fp = first_pub.get(mid, r["publication_utc"])
        out.append({
            "message_id": mid, "version": int(ver),
            "kind": KINDS.get(r["unit_kind"], str(r["unit_kind"])),
            "unplanned": bool(r["unavailability_type"] == 1),
            "units": sorted({str(x).strip() for x in g["unit_name"].dropna()}),
            "fuel": FUELS.get(int(r["fuel"])) if pd.notna(r["fuel"]) else None,
            "unavailable_mw": float(g["unavailable_mw"].max()),
            "event_start_utc": g["start_utc"].min().to_pydatetime(),
            "event_stop_utc": g["stop_utc"].max().to_pydatetime(),
            "publication_utc": r["publication_utc"].to_pydatetime(),
            "fresh": bool(fp > as_of - pd.Timedelta(hours=fresh_hours)),
            "reason": None if pd.isna(r["reason"]) else str(r["reason"]),
            "url": LINK.format(message_id=mid, version=int(ver)),
        })
    out.sort(key=lambda m: (not m["unplanned"], -m["publication_utc"].timestamp()))
    return out

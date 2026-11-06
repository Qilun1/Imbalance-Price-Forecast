"""Wind sites from OpenStreetMap (Overpass API), clustered into ~10 km sites with capacity.

Writes tools/ingest/reference/wind_sites_osm.csv (same columns as wind_sites_v0.csv). Positions are
(c) OpenStreetMap contributors, ODbL. Turbines without a rated output tag get the median of tagged
turbines. Total capacity is scaled to the Renewables Finland total so the national weights match.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from tools.ingest.http import Client

OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = """
[out:json][timeout:180];
area["ISO3166-1"="FI"][admin_level=2]->.fi;
(
  node["generator:source"="wind"](area.fi);
  way["generator:source"="wind"](area.fi);
);
out center tags;
"""
REF_DIR = Path(__file__).parent / "reference"
NATIONAL_MW = 9535.0          # Renewables Finland, 30 Jun 2026
CELL_DEG = (0.09, 0.2)        # ~10 km x ~10 km at 63 N (lat, lon)


def _mw(tag: str | None) -> float:
    if not tag:
        return np.nan
    m = re.search(r"([\d.,]+)\s*(kW|MW|W)?", tag)
    if not m:
        return np.nan
    v = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "MW").upper()
    return v / 1000 if unit == "KW" else v / 1e6 if unit == "W" else v


def run() -> Path:
    data = Client(min_interval_s=1.0, timeout_s=240).get_json(OVERPASS, params={"data": QUERY})
    rows = []
    for el in data.get("elements", []):
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None or lon is None:
            continue
        rows.append({"lat": lat, "lon": lon, "mw": _mw(el.get("tags", {}).get("generator:output:electricity"))})
    t = pd.DataFrame(rows)
    if t.empty:
        raise RuntimeError("Overpass returned no wind turbines")
    t["mw"] = t["mw"].where(t["mw"].between(0.1, 15)).fillna(t["mw"].median() if t["mw"].notna().any() else 4.0)
    t["cell"] = (np.floor(t["lat"] / CELL_DEG[0]).astype(int).astype(str) + "_" +
                 np.floor(t["lon"] / CELL_DEG[1]).astype(int).astype(str))
    g = t.groupby("cell").agg(lat=("lat", "mean"), lon=("lon", "mean"), capacity_mw=("mw", "sum"),
                              turbines=("mw", "size")).reset_index()
    g["capacity_mw"] *= NATIONAL_MW / g["capacity_mw"].sum()
    g["site_id"] = "osm_" + g["cell"]
    g["region"], g["place"] = "osm", g["turbines"].astype(str) + " turbines"
    out = REF_DIR / "wind_sites_osm.csv"
    g[["site_id", "region", "place", "lat", "lon", "capacity_mw"]].round(4).to_csv(out, index=False)
    print(f"{len(t)} turbines -> {len(g)} sites -> {out}")
    return out


def load_sites() -> pd.DataFrame:
    """OSM sites if built, else the coarse v0 list."""
    osm = REF_DIR / "wind_sites_osm.csv"
    return pd.read_csv(osm if osm.exists() else REF_DIR / "wind_sites_v0.csv")

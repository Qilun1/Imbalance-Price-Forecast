"""Wind sites used to sample NWP forecasts for a capacity-weighted national wind proxy.

v0 (in code, below): regional capacities from Renewables Finland (Suomen Uusiutuvat ry), wind
statistics 30 Jun 2026, total 9,535 MW
(https://suomenuusiutuvat.fi/media/tuulivoima_vuositilastot-6_2026.pdf). Region labels of the chart
were matched to its pie-chart shares; "Other" is the remainder. Each region's capacity is split
evenly over a few municipalities with large wind clusters; coordinates are approximate municipality
centres (about +-10 km). Good for a 9 km grid and a national aggregate, not for farm-level work.

OSM refinement (`ingest windsites`): turbine positions from OpenStreetMap via Overpass, clustered into
~10 km sites, written to static_data/raw/windsites/wind_sites_osm.csv (not committed: AGENTS.md
rule 0). Data (c) OpenStreetMap contributors, ODbL. Turbines without a rated output tag get the median
of tagged turbines; the total is scaled to the Renewables Finland total.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from imbalance.paths import RAW_DIR
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
OSM_SITES = RAW_DIR / "windsites" / "wind_sites_osm.csv"

# region: (capacity MW, [(place, lat, lon), ...])
V0_REGIONS = {
    "Pohjois-Pohjanmaa": (3397.0, [("Kalajoki", 64.26, 23.95), ("Pyhajoki", 64.47, 24.26), ("Raahe", 64.68, 24.48),
                                   ("Siikajoki", 64.82, 24.76), ("Ii", 65.32, 25.37), ("Merijarvi", 64.30, 24.45),
                                   ("Haapavesi", 64.14, 25.37), ("Pyhajarvi", 63.68, 25.98)]),
    "Pohjanmaa": (1663.0, [("Kristiinankaupunki", 62.27, 21.38), ("Narpio", 62.47, 21.34), ("Korsnas", 62.79, 21.19),
                           ("Uusikaarlepyy", 63.52, 22.53), ("Voyri", 63.13, 22.25)]),
    "Etela-Pohjanmaa": (1155.0, [("Teuva", 62.49, 21.74), ("Isojoki", 62.11, 21.96), ("Kurikka", 62.62, 22.40),
                                 ("Lapua", 62.97, 23.01), ("Kauhava", 63.10, 23.07)]),
    "Keski-Pohjanmaa": (983.0, [("Kokkola", 63.84, 23.13), ("Kannus", 63.90, 23.90), ("Toholampi", 63.77, 24.25),
                                ("Halsua", 63.46, 24.17)]),
    "Lappi": (765.0, [("Tornio", 65.85, 24.15), ("Simo", 65.66, 25.06), ("Kemi", 65.74, 24.56), ("Tervola", 66.08, 24.81)]),
    "Satakunta": (492.0, [("Pori", 61.63, 21.45), ("Merikarvia", 61.86, 21.50), ("Pomarkku", 61.69, 22.01)]),
    "Keski-Suomi": (350.0, [("Kinnula", 63.37, 24.97), ("Pihtipudas", 63.37, 25.57), ("Viitasaari", 63.07, 25.86)]),
    "Kainuu": (272.0, [("Kajaani", 64.23, 27.73), ("Paltamo", 64.41, 27.83)]),
    "Other": (458.0, [("Kihnio", 62.21, 23.18), ("Iisalmi", 63.56, 27.19), ("Uusikaupunki", 60.80, 21.41)]),
}


def v0_sites() -> pd.DataFrame:
    rows = []
    for region, (mw, places) in V0_REGIONS.items():
        for place, lat, lon in places:
            rows.append({"site_id": f"v0_{place.lower()}", "region": region, "place": place, "lat": lat, "lon": lon,
                         "capacity_mw": mw / len(places)})
    return pd.DataFrame(rows)
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
    out = OSM_SITES
    out.parent.mkdir(parents=True, exist_ok=True)
    g[["site_id", "region", "place", "lat", "lon", "capacity_mw"]].round(4).to_csv(out, index=False)
    print(f"{len(t)} turbines -> {len(g)} sites -> {out}")
    return out


def coarsen(sites: pd.DataFrame, cell_km: float = 100.0, min_mw: float = 150.0) -> pd.DataFrame:
    """Merge sites onto a ~cell_km grid (capacity-weighted position), then fold sites below min_mw into
    their nearest larger site. Keeps the national total. Default (100 km, 150 MW) gives about 10 regional
    points: Open-Meteo counts every location as one API call (free tier 10,000 a day)."""
    lat_deg = cell_km / 111.0
    lon_deg = cell_km / (111.0 * np.cos(np.radians(64.0)))
    s = sites.copy()
    s["cell"] = (np.floor(s["lat"] / lat_deg).astype(int).astype(str) + "_" +
                 np.floor(s["lon"] / lon_deg).astype(int).astype(str))
    s["wlat"], s["wlon"] = s["lat"] * s["capacity_mw"], s["lon"] * s["capacity_mw"]
    g = s.groupby("cell").agg(capacity_mw=("capacity_mw", "sum"), wlat=("wlat", "sum"), wlon=("wlon", "sum")).reset_index()
    g["lat"], g["lon"] = g["wlat"] / g["capacity_mw"], g["wlon"] / g["capacity_mw"]
    big, small = g[g["capacity_mw"] >= min_mw].copy(), g[g["capacity_mw"] < min_mw]
    if big.empty:
        big, small = g.copy(), g.iloc[0:0]
    for _, r in small.iterrows():
        i = ((big["lat"] - r["lat"]) ** 2 + ((big["lon"] - r["lon"]) * 0.44) ** 2).idxmin()
        big.loc[i, "capacity_mw"] += r["capacity_mw"]
    big["site_id"] = "c" + big["cell"]
    big["region"], big["place"] = "coarsened", ""
    return big[["site_id", "region", "place", "lat", "lon", "capacity_mw"]].round(4).reset_index(drop=True)


def load_sites() -> pd.DataFrame:
    """OSM sites coarsened to about 10 regional points if built, else the v0 list (coarsened the same way)."""
    return coarsen(pd.read_csv(OSM_SITES) if OSM_SITES.exists() else v0_sites())

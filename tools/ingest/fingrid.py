"""Fingrid Open Data API ingest (needs FINGRID_API_KEY in the environment or a .env file).

Two uses:
- New series not in the starter package (e.g. 75 wind generation), with a conservative
  publication-delay rule, under new series_ids.
- Extending package series past the package end for the live mode. Existing (organiser) rows are
  never overwritten: the store inserts with ON CONFLICT DO NOTHING.

first_usable_origin_utc follows the organiser's rules (availability.csv) where the dataset is in the
package, else the conservative default below.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from imbalance import store
from imbalance.paths import RAW_DIR, REPO_ROOT
from tools.ingest.http import Client

URL = "https://data.fingrid.fi/api/datasets/{id}/data"

# dataset_id: (series_id, unit, availability rule)
# rule ("lag", minutes after period end) or ("daily", day offset, "HH:MM" Europe/Helsinki)
DATASETS = {
    # in the starter package (same series_id, same organiser rules)
    319: ("fi_imbalance_price", "EUR/MWh", ("lag", 60)),
    244: ("fi_mfrr_up_price", "EUR/MWh", ("lag", 60)),
    106: ("fi_mfrr_down_price", "EUR/MWh", ("lag", 60)),
    375: ("fi_mfrr_up_activated", "MW", ("lag", 60)),
    376: ("fi_mfrr_down_activated", "MW", ("lag", 60)),
    369: ("fi_mfrr_direction", "-1/0/1", ("lag", 60)),
    124: ("fi_consumption", "MWh/h", ("lag", 30)),
    74: ("fi_production", "MWh/h", ("lag", 30)),
    165: ("fi_consumption_fc_da", "MW", ("daily", -1, "13:00")),
    246: ("fi_wind_fc_da", "MWh/h", ("daily", -1, "13:00")),
    247: ("fi_solar_fc_da", "MWh/h", ("daily", -1, "13:00")),
    # new series (not in the package): conservative 60 min lag after period end
    75: ("fi_wind_production", "MWh/h", ("lag", 60)),
    188: ("fi_nuclear_production_rt", "MW", ("lag", 60)),
    198: ("fi_surplus_deficit_rt", "MW", ("lag", 60)),
}


def api_key() -> str:
    key = os.environ.get("FINGRID_API_KEY")
    env = REPO_ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("FINGRID_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        raise RuntimeError("set FINGRID_API_KEY (environment variable or .env in the repo root)")
    return key


def first_usable(ts: pd.Series, rule: tuple, period: pd.Timedelta) -> pd.Series:
    if rule[0] == "lag":
        return (ts + period + pd.Timedelta(minutes=rule[1])).dt.ceil("h")
    _, day_offset, hhmm = rule
    local_day = ts.dt.tz_convert("Europe/Helsinki").dt.normalize()
    pub = (local_day + pd.Timedelta(days=day_offset) + pd.Timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[3:])))
    return pub.dt.tz_convert("UTC").dt.ceil("h")


def run(datasets: list[int], start: str, end: str) -> None:
    client = Client(min_interval_s=2.1, headers={"x-api-key": api_key()})   # Fingrid: 1 call per 2 s
    for ds in datasets:
        if ds not in DATASETS:
            raise ValueError(f"dataset {ds} not configured in tools/ingest/fingrid.py DATASETS")
        sid, unit, rule = DATASETS[ds]
        rows, page = [], 1
        while True:
            params = {"startTime": pd.Timestamp(start, tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "endTime": pd.Timestamp(end, tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "format": "json", "pageSize": 20000, "page": page, "sortOrder": "asc"}
            cache = RAW_DIR / "fingrid" / str(ds) / f"{start}_{end}_p{page}.json".replace(":", "")
            data = client.get_json(URL.format(id=ds), params=params, cache=cache)
            rows += data.get("data", [])
            pag = data.get("pagination") or {}
            if not pag.get("nextPage"):
                break
            page = pag["nextPage"]
        if not rows:
            print(f"{ds} {sid}: no rows")
            continue
        df = pd.DataFrame(rows)
        df["timestamp_utc"] = pd.to_datetime(df["startTime"], utc=True)
        period = (pd.to_datetime(df["endTime"], utc=True) - df["timestamp_utc"]).median()
        out = pd.DataFrame({
            "series_id": sid, "source": "fingrid", "dataset_id": str(ds), "timestamp_utc": df["timestamp_utc"],
            "value": pd.to_numeric(df["value"], errors="coerce"), "unit": unit,
        }).drop_duplicates(["series_id", "timestamp_utc"])
        out["first_usable_origin_utc"] = first_usable(out["timestamp_utc"], rule, period)
        n = store.insert_observations(out, batch=f"fingrid:{ds}")
        print(f"{ds} {sid}: {len(out)} rows fetched, {n} new (existing rows kept unchanged)")
        if ds not in (319, 244, 106, 375, 376, 369, 124, 74, 165, 246, 247):
            store.upsert_catalog(pd.DataFrame([{
                "series_id": sid, "source": "fingrid", "dataset_id": str(ds), "unit": unit, "kind": "observation",
                "availability_rule": f"{rule} (conservative, ours)", "licence": "CC BY 4.0 (Fingrid Open Data)",
                "description": "Fingrid Open Data API"}]))

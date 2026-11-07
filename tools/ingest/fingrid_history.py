"""Pre-June Fingrid history for pre-training, kept OUTSIDE the static store.

Writes one parquet per dataset to static_data/raw/fingrid_history/ (gitignored). It never touches
static.duckdb, so the feature tables, the training window and the leakage check are unaffected.
Measured / realised datasets only (no forecasts: the API keeps only their latest version).

    uv run python -m tools.ingest.fingrid_history --start 2025-03-01 --end 2026-11-02
"""
from __future__ import annotations

import argparse

import pandas as pd

from imbalance.paths import RAW_DIR
from tools.ingest.fingrid import URL, api_key
from tools.ingest.http import Budget, Client

DATASETS = {
    319: "fi_imbalance_price",        # for checking the rebuild only, never a pre-June target
    244: "fi_mfrr_up_price", 106: "fi_mfrr_down_price",
    375: "fi_mfrr_up_activated", 376: "fi_mfrr_down_activated",   # MW, max power of the quarter-hour
    369: "fi_mfrr_direction",
    347: "fi_afrr_up_price", 348: "fi_afrr_down_price",           # aFRR VWA prices
    349: "fi_afrr_up_volume", 350: "fi_afrr_down_volume",         # aFRR activation volume with marginal price
    342: "fi_mfrr_activated_net",
    75: "fi_wind_production",
}
OUT = RAW_DIR / "fingrid_history"


def fetch(client: Client, ds: int, start: str, end: str) -> pd.DataFrame:
    rows, page = [], 1
    while True:
        params = {"startTime": pd.Timestamp(start, tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "endTime": pd.Timestamp(end, tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "format": "json", "pageSize": 20000, "page": page, "sortOrder": "asc"}
        cache = OUT / "cache" / str(ds) / f"{start}_{end}_p{page}.json"
        data = client.get_json(URL.format(id=ds), params=params, cache=cache)
        got = data.get("data", [])
        rows += got
        pag = data.get("pagination") or {}
        if page == 1:
            last_page = pag.get("lastPage") or 1
        if page >= last_page or len(got) < params["pageSize"]:
            break
        page += 1
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["timestamp_utc"] = pd.to_datetime(df["startTime"], utc=True)
    df["end_utc"] = pd.to_datetime(df["endTime"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[["timestamp_utc", "end_utc", "value"]].dropna().drop_duplicates("timestamp_utc").sort_values("timestamp_utc")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-03-01")
    ap.add_argument("--end", default="2026-11-02")
    ap.add_argument("--datasets", type=int, nargs="*", default=list(DATASETS))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    client = Client(min_interval_s=6.5, headers={"x-api-key": api_key()},
                    budget=Budget(per_minute=9, per_hour=500, per_day=9000))
    for ds in a.datasets:
        df = fetch(client, ds, a.start, a.end)
        name = DATASETS.get(ds, str(ds))
        if df.empty:
            print(f"{ds} {name}: no rows"); continue
        step = (df["end_utc"] - df["timestamp_utc"]).median()
        df.to_parquet(OUT / f"{ds}_{name}.parquet", index=False)
        print(f"{ds} {name}: {len(df):,} rows {df.timestamp_utc.min():%Y-%m-%d} .. {df.timestamp_utc.max():%Y-%m-%d}, step {step}")


if __name__ == "__main__":
    main()

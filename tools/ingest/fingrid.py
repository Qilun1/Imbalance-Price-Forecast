"""Fingrid Open Data API ingest (needs FINGRID_API_KEY in the environment or the gitignored .env).

Only MEASURED / realised datasets are allowed here. Forecast datasets (e.g. 165, 245, 246, 247) are
refused: the API keeps only the latest version of a revised forecast, which the rules forbid for
backtesting (AGENTS.md rule 4). Their vintaged versions come from the starter package.

Two uses:
- New series not in the starter package (e.g. 75 actual wind generation), under new series_ids, with
  a documented conservative availability rule.
- Extending package series past the package end for the live mode. Existing (organiser) rows are
  never overwritten: the store inserts with ON CONFLICT DO NOTHING.

Quarter-hour format (AGENTS.md rule 3): data finer than 15 min (3-min real-time series) is averaged
into quarter-hours, keeping only complete quarter-hours (missing stays missing); first usable origin
counts from the END of the quarter-hour. Hourly data is repeated for its four quarter-hours, counted
from the end of the hour.
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
# rule ("lag", minutes after the END of the quarter-hour, then next full hour)
DATASETS = {
    # in the starter package (same series_id, the organiser's rules; only extended past the package end)
    319: ("fi_imbalance_price", "EUR/MWh", ("lag", 60)),
    244: ("fi_mfrr_up_price", "EUR/MWh", ("lag", 60)),
    106: ("fi_mfrr_down_price", "EUR/MWh", ("lag", 60)),
    375: ("fi_mfrr_up_activated", "MW", ("lag", 60)),
    376: ("fi_mfrr_down_activated", "MW", ("lag", 60)),
    369: ("fi_mfrr_direction", "-1/0/1", ("lag", 60)),
    124: ("fi_consumption", "MWh/h", ("lag", 30)),
    74: ("fi_production", "MWh/h", ("lag", 30)),
    # new measured series (not in the package): conservative 60 min after the quarter-hour ends
    75: ("fi_wind_production", "MWh/h", ("lag", 60)),          # wind power generation, 15 min
    188: ("fi_nuclear_production_rt", "MW", ("lag", 60)),     # nuclear real-time, 3 min -> 15 min mean
    191: ("fi_hydro_production_rt", "MW", ("lag", 60)),       # hydro real-time, 3 min -> 15 min mean
    # grid state at the origin (feature sets v9 / v9m). Real-time series, 15 min after the quarter-hour
    # ends: tools/eval/fingrid_delay.py measured 1.2-4.1 min publication delay (7 Nov 2026), so 15 min
    # is a >3x margin; with the full-hour rounding any lag <= 15 min gives the same first usable origin.
    198: ("fi_surplus_deficit_rt", "MW", ("lag", 15)),       # measured net import - confirmed program
    177: ("fi_frequency_rt", "Hz", ("lag", 15)),
    194: ("fi_net_import_rt", "MW", ("lag", 15)),
    371: ("fi_eboiler_rt", "MW", ("lag", 15)),               # 1 min -> 15 min mean
    398: ("fi_bess_discharge_rt", "MW", ("lag", 15)),
    399: ("fi_bess_charge_rt", "MW", ("lag", 15)),
    181: ("fi_wind_production_rt", "MW", ("lag", 15)),
    193: ("fi_consumption_rt", "MW", ("lag", 15)),
}
FORECAST_DATASETS = {165, 166, 245, 246, 247, 248, 241, 242}   # never via the API (latest version only)
PACKAGE_SERIES = {319, 244, 106, 375, 376, 369, 124, 74}


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


def first_usable(period_end: pd.Series, rule: tuple) -> pd.Series:
    """First full-hour origin at or after the source period's end plus the publication lag."""
    return (period_end + pd.Timedelta(minutes=rule[1])).dt.ceil("h")


def to_quarter_hours(df: pd.DataFrame) -> pd.DataFrame:
    """Source rows (timestamp_utc = period start, end, value) -> one row per quarter-hour with the end
    of the SOURCE period it came from (used for availability)."""
    period = (df["end"] - df["timestamp_utc"]).median()
    q = pd.Timedelta(minutes=15)
    if period == q:
        return pd.DataFrame({"timestamp_utc": df["timestamp_utc"], "value": df["value"], "period_end": df["end"]})
    if period < q:
        need = int(q / period)
        g = df.assign(qh=df["timestamp_utc"].dt.floor("15min")).groupby("qh")["value"].agg(["mean", "count"])
        g = g[g["count"] == need]                        # complete quarter-hours only; missing stays missing
        return pd.DataFrame({"timestamp_utc": g.index, "value": g["mean"].to_numpy(), "period_end": g.index + q})
    if period == pd.Timedelta(hours=1):                  # repeat for the four quarter-hours (AGENTS.md rule 3)
        parts = [pd.DataFrame({"timestamp_utc": df["timestamp_utc"] + k * q, "value": df["value"],
                               "period_end": df["end"]}) for k in range(4)]
        return pd.concat(parts).sort_values("timestamp_utc")
    raise ValueError(f"unsupported resolution {period}")


def run(datasets: list[int], start: str, end: str) -> None:
    bad = sorted(set(datasets) & FORECAST_DATASETS)
    if bad:
        raise ValueError(f"datasets {bad} are forecasts: the API keeps only their latest version, which the "
                         "rules forbid for backtesting (AGENTS.md rule 4)")
    client = Client(min_interval_s=2.1, headers={"x-api-key": api_key()})   # Fingrid: 1 call per 2 s
    for ds in datasets:
        if ds in FORECAST_DATASETS:
            raise ValueError(f"dataset {ds} is a forecast: the API keeps only its latest version, which the "
                             "rules forbid for backtesting (AGENTS.md rule 4)")
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
            got = data.get("data", [])
            rows += got
            pag = data.get("pagination") or {}
            if page == 1:
                last_page = pag.get("lastPage") or 1
            # Fingrid returns nextPage/lastPage only on page 1, so page by count, not by nextPage
            if page >= last_page or len(got) < params["pageSize"]:
                break
            page += 1
        if not rows:
            print(f"{ds} {sid}: no rows")
            continue
        df = pd.DataFrame(rows)
        df["timestamp_utc"] = pd.to_datetime(df["startTime"], utc=True)
        df["end"] = pd.to_datetime(df["endTime"], utc=True)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"]).drop_duplicates("timestamp_utc").sort_values("timestamp_utc")
        qh = to_quarter_hours(df)
        out = pd.DataFrame({"series_id": sid, "source": "fingrid", "dataset_id": str(ds),
                            "timestamp_utc": pd.to_datetime(qh["timestamp_utc"], utc=True).to_numpy(),
                            "value": qh["value"].to_numpy(), "unit": unit})
        out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"], utc=True)
        out["first_usable_origin_utc"] = first_usable(pd.to_datetime(qh["period_end"], utc=True).reset_index(drop=True), rule).to_numpy()
        n = store.insert_observations(out, batch=f"fingrid:{ds}")
        print(f"{ds} {sid}: {len(out)} rows fetched, {n} new (existing rows kept unchanged)")
        if ds not in PACKAGE_SERIES:
            store.upsert_catalog(pd.DataFrame([{
                "series_id": sid, "source": "fingrid", "dataset_id": str(ds), "unit": unit, "kind": "observation",
                "availability_rule": f"{rule} (conservative, ours)", "licence": "CC BY 4.0 (Fingrid Open Data)",
                "description": "Fingrid Open Data API"}]))

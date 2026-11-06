"""Vintaged NWP from the Open-Meteo Single Runs API into the `forecast_runs` table.

Only the Single Runs API is used (organiser's rule): every run is stored with its init time, and
first_usable_origin_utc = next full hour at or after run_init + publication delay. The delays are
conservative (Open-Meteo docs: global models 4-6 h after init, regional 1-3 h).

Each run is fetched once for all wind sites (comma-separated coordinates) and cached as raw JSON in
static_data/raw/openmeteo/<model>/<run>.json, so an interrupted pull resumes where it stopped.
"""
from __future__ import annotations

import pandas as pd

from imbalance import store
from imbalance.paths import RAW_DIR
from tools.ingest.http import Client
from tools.ingest.windsites import load_sites

URL = "https://single-runs-api.open-meteo.com/v1/forecast"
MODELS = {
    # model id: (publication delay, run hours UTC)
    "ecmwf_ifs": (pd.Timedelta(hours=7), (0, 6, 12, 18)),
    "metno_nordic": (pd.Timedelta(hours=3), (0, 6, 12, 18)),
}
VARIABLES = ["wind_speed_10m", "wind_speed_100m", "wind_direction_100m", "temperature_2m"]
UNITS = {"wind_speed_10m": "m/s", "wind_speed_100m": "m/s", "wind_direction_100m": "deg", "temperature_2m": "degC"}
FORECAST_HOURS = 36           # covers origin + 10 h for any run up to ~24 h old


def first_usable(run_init: pd.Timestamp, delay: pd.Timedelta) -> pd.Timestamp:
    return (run_init + delay).ceil("h")


def fetch_run(client: Client, model: str, run: pd.Timestamp, sites: pd.DataFrame) -> pd.DataFrame:
    params = {
        "latitude": ",".join(f"{v:.4f}" for v in sites["lat"]),
        "longitude": ",".join(f"{v:.4f}" for v in sites["lon"]),
        "hourly": ",".join(VARIABLES),
        "models": model,
        "run": run.strftime("%Y-%m-%dT%H:%M"),
        "forecast_hours": FORECAST_HOURS,
        "wind_speed_unit": "ms",
        "timezone": "GMT",
        "timeformat": "unixtime",
    }
    cache = RAW_DIR / "openmeteo" / model / f"{run:%Y%m%dT%H%M}.json"
    data = client.get_json(URL, params=params, cache=cache)
    locs = data if isinstance(data, list) else [data]
    if len(locs) != len(sites):
        raise RuntimeError(f"{model} {run}: {len(locs)} locations returned for {len(sites)} sites")
    delay = MODELS[model][0]
    frames = []
    for site_id, loc in zip(sites["site_id"], locs):
        h = loc.get("hourly", {})
        if "time" not in h:
            continue
        valid = pd.to_datetime(h["time"], unit="s", utc=True)
        for var in VARIABLES:
            vals = h.get(var) or h.get(f"{var}_{model}")
            if vals is None:
                continue
            frames.append(pd.DataFrame({
                "series_id": f"om_{model}_{var}", "source": "open-meteo", "location_id": site_id,
                "run_init_utc": run, "valid_time_utc": valid, "member": 0,
                "value": pd.to_numeric(pd.Series(vals), errors="coerce").to_numpy(), "unit": UNITS[var],
                "first_usable_origin_utc": first_usable(run, delay),
            }))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run(start: str, end: str, models: list[str] | None = None) -> None:
    sites = load_sites()
    client = Client(min_interval_s=0.6)
    for model in models or list(MODELS):
        delay, hours = MODELS[model]
        runs = [t for t in pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), freq="h")
                if t.hour in hours]
        ok = fail = inserted = 0
        for i, r in enumerate(runs, 1):
            try:
                df = fetch_run(client, model, r, sites)
                if not df.empty:
                    inserted += store.insert_forecast_runs(df, batch=f"openmeteo:{model}")
                ok += 1
            except RuntimeError as e:
                fail += 1
                print(f"  {model} {r:%Y-%m-%d %H}Z skipped: {str(e)[:120]}")
            if i % 40 == 0:
                print(f"  {model}: {i}/{len(runs)} runs, {inserted} rows")
        print(f"{model}: {ok} runs ok, {fail} skipped, {inserted} rows inserted (delay {delay})")
    _catalog(models or list(MODELS))


def _catalog(models: list[str]) -> None:
    rows = [{"series_id": f"om_{m}_{v}", "source": "open-meteo", "dataset_id": m, "unit": UNITS[v],
             "kind": "forecast_run",
             "availability_rule": f"run init + {MODELS[m][0]}, next full hour (Single Runs API)",
             "licence": "CC BY 4.0 (Open-Meteo, underlying model data per provider)",
             "description": f"{v} at wind sites (tools/ingest/windsites.py)"} for m in models for v in VARIABLES]
    store.upsert_catalog(pd.DataFrame(rows))

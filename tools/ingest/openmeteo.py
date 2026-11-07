"""Vintaged NWP from the Open-Meteo Single Runs API into the `forecast_runs` table.

Only the Single Runs API is used (organiser's rule): every run is stored with its init time, and
first_usable_origin_utc = next full hour at or after run_init + publication delay. The delays are
conservative (Open-Meteo docs: global models 4-6 h after init, regional 1-3 h).

Each run is fetched once for all wind sites (comma-separated coordinates) and cached as raw JSON in
static_data/raw/openmeteo/<model>/<run>.json, so an interrupted pull resumes where it stopped.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from imbalance import store
from imbalance.paths import RAW_DIR
from tools.ingest.http import Budget, Client, DailyLimit
from tools.ingest.windsites import load_sites

URL = "https://single-runs-api.open-meteo.com/v1/forecast"
# Publication delay per model = run init -> first moment the run may be used, BEFORE rounding up to
# the next full hour. Must be conservative (AGENTS.md rule 4).
# ecmwf_ifs: measured 7 Nov 2026 from Open-Meteo's metadata endpoint
#   (https://api.open-meteo.com/data/ecmwf_ifs/static/meta.json): last_run_availability_time -
#   last_run_initialisation_time = 24,491 s = 6 h 48 min; Open-Meteo advises waiting a further 10 min.
#   -> 6 h 58 min. We use 8 h (about 1 h margin). Re-check with `tools.cli nwp-delay`.
# metno_nordic: NOT measured; do not use until `tools.cli nwp-delay --model metno_nordic` is checked.
MODELS = {
    # model id: (publication delay, run hours UTC)
    "ecmwf_ifs": (pd.Timedelta(hours=8), (0, 6, 12, 18)),
    "metno_nordic": (pd.Timedelta(hours=4), (0, 6, 12, 18)),
}
META_URL = "https://api.open-meteo.com/data/{model}/static/meta.json"


def measure_delay(model: str = "ecmwf_ifs") -> pd.Timedelta:
    """Delay of the latest run as reported by Open-Meteo (availability - initialisation)."""
    m = Client(min_interval_s=1.0).get_json(META_URL.format(model=model))
    return pd.Timedelta(seconds=m["last_run_availability_time"] - m["last_run_initialisation_time"])
DEFAULT_MODELS = ["ecmwf_ifs"]   # free tier: ~10 sites x 620 runs = ~6,200 calls, inside 10,000/day
# Open-Meteo free tier: 600/min, 5,000/h, 10,000/day; every location counts as one call. Stay below.
FREE_BUDGET = dict(per_minute=500, per_hour=4500, per_day=9500)
VARIABLES = ["wind_speed_100m", "temperature_2m"]          # hub-height wind proxy + heating demand
UNITS = {"wind_speed_10m": "m/s", "wind_speed_100m": "m/s", "wind_direction_100m": "deg", "temperature_2m": "degC"}
FORECAST_HOURS = 27           # newest usable run is <= ~13 h old; + 10 h horizon + margin


KEEP_CACHE = True             # set False (--no-cache) to keep only the DuckDB rows


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
    key = hashlib.sha1((params["latitude"] + params["longitude"] + params["hourly"]).encode()).hexdigest()[:8]
    cache = None if not KEEP_CACHE else RAW_DIR / "openmeteo" / f"{model}_{key}" / f"{run:%Y%m%dT%H%M}.json"
    data = client.get_json(URL, params=params, cache=cache, weight=len(sites))
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


GROUP_VARIABLES = {"wind": ["wind_speed_100m", "temperature_2m"], "pop": ["temperature_2m"]}


def run(start: str, end: str, models: list[str] | None = None, keep_cache: bool = True, group: str = "wind") -> None:
    """group 'wind': ~10 capacity-weighted wind sites; group 'pop': 7 population centres (temperature)."""
    global KEEP_CACHE, VARIABLES
    KEEP_CACHE = keep_cache
    VARIABLES = GROUP_VARIABLES[group]
    if group == "pop":
        from tools.ingest.popsites import load_pop_sites
        sites = load_pop_sites()
    else:
        sites = load_sites()
    store.set_locations(sites, group=group)
    models = models or DEFAULT_MODELS
    print(f"group {group}: {len(sites)} sites, variables {VARIABLES}, {FORECAST_HOURS} h per run")
    client = Client(min_interval_s=0.6, budget=Budget(**FREE_BUDGET))
    for model in models:
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
            except DailyLimit:
                print(f"{model}: daily API limit reached after {ok} runs ({inserted} rows). Cached runs are kept; "
                      "rerun the same command tomorrow to continue.")
                _catalog(models)
                return
            except RuntimeError as e:
                fail += 1
                print(f"  {model} {r:%Y-%m-%d %H}Z skipped: {str(e)[:120]}")
            if i % 40 == 0:
                print(f"  {model}: {i}/{len(runs)} runs, {inserted} rows")
        print(f"{model}: {ok} runs ok, {fail} skipped, {inserted} rows inserted (delay {delay})")
    _catalog(models)


def _catalog(models: list[str]) -> None:
    rows = [{"series_id": f"om_{m}_{v}", "source": "open-meteo", "dataset_id": m, "unit": UNITS[v],
             "kind": "forecast_run",
             "availability_rule": f"run init + {MODELS[m][0]}, next full hour (Single Runs API)",
             "licence": "CC BY 4.0 (Open-Meteo, underlying model data per provider)",
             "description": f"{v} at wind sites (tools/ingest/windsites.py)"} for m in models for v in VARIABLES]
    store.upsert_catalog(pd.DataFrame(rows))

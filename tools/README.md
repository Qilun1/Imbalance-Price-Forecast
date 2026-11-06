# tools

Every step runs through one CLI from the repo root: `uv run python -m tools.cli <command>`.
Run `uv run python -m tools.cli --help` for all options.

| Folder | Content |
|---|---|
| `ingest/` | Fetch and normalise data into `static_data/static.duckdb` (`starter`, `windsites`, `openmeteo`, `fingrid`) |
| `training/` | `train.py`, cached feature tables, configs in `training/configs/*.yaml` |
| `eval/` | Organiser's scripts runner, verbatim baseline port, leakage check |
| `starter_package/` | Organiser's package, unchanged. Do not edit (see AGENTS.md). |

## First run (Windows PowerShell, macOS, Linux)

```powershell
uv sync
# 1. Load the starter data (path to the unzipped starter_package_v1 or its data folder)
uv run python -m tools.cli ingest starter --src C:\path\to\starter_package_v1
# 2. Whole v1 pipeline: features, train (val + final), score vs baseline, test export, leakage check
uv run python -m tools.cli pipeline --config tools/training/configs/lgbm_v1.yaml
```

Outputs: models in `backend/artifacts/`, forecasts in `backend/infer_data/forecasts.duckdb`, the
validated submission in `static_data/work/submissions/lgbm_v1_test.csv`, scores in
`static_data/work/scores/`.

## Individual steps

```powershell
uv run python -m tools.cli status                                   # what is in the stores
uv run python -m tools.cli features --set v1
uv run python -m tools.cli train --config tools/training/configs/lgbm_v1.yaml --mode val
uv run python -m tools.cli infer --model lgbm_v1-val --period val
uv run python -m tools.cli score --model lgbm_v1-val                # organiser score.py vs baseline
uv run python -m tools.cli export --model lgbm_v1 --period test --out forecast_backtest.csv
uv run python -m tools.cli single-run --model lgbm_v1 --origin 2026-10-20T08:00Z
uv run python -m tools.cli leakage --n 60
uv run python -m tools.cli compare --models baseline-val lgbm_v1-val lgbm_v2-val   # ablation by lead hour
uv run pytest
```

## External data (run on your own machine; needs internet)

```powershell
uv run python -m tools.cli ingest windsites                         # OSM turbines -> static_data/raw/windsites/
uv run python -m tools.cli ingest openmeteo --start 2026-05-30 --end 2026-11-02T06:00
$env:FINGRID_API_KEY="..."   # or put FINGRID_API_KEY=... in .env at the repo root (gitignored)
uv run python -m tools.cli ingest fingrid --datasets 75 --start 2026-05-31 --end 2026-11-02T07:00
```

- Open-Meteo: Single Runs API only, ECMWF IFS 9 km by default (`--models ecmwf_ifs,metno_nordic` for
  more), 4 runs a day, wind speed at 100 m and 2 m temperature, 27 h per run. Sites: OSM turbines
  merged into about 10 regional points (capacity-weighted). The free tier counts every location as one
  call (600/min, 5,000/h, 10,000/day): about 6,200 calls in total, paced automatically (~70 min). If the
  daily limit is hit, the command stops cleanly; rerun it the next day and it resumes from the cache.
- Fingrid: new series get new `series_id`s and a conservative availability rule; package series are
  only extended past the package end, never overwritten.

## Weather features (feature set v2)

After `ingest openmeteo` (which also registers the NWP sites with `ingest locations`):

```powershell
uv run python -m tools.cli pipeline --config tools/training/configs/lgbm_v2.yaml --set v2
uv run python -m tools.cli compare --models baseline-val lgbm_v1-val lgbm_v2-val
```

v2 adds, from the newest ECMWF run usable at each origin: national wind power proxy (MW, power curve
on 100 m wind at capacity-weighted sites), its difference from Fingrid's day-ahead wind forecast, the
change versus the previous run, the 1 h ramp, run age, and capacity-weighted 2 m temperature.

## Model versions

- `<name>-val`: trained on targets published before 7 Sep 2026; use it for validation scores.
- `<name>`: trained up to 4 Oct 2026 (training cutoff); use it for the test submission and dashboard.
  Its forecasts for the validation period are in-sample.

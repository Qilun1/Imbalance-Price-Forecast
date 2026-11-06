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
uv run pytest
```

## External data (run on your own machine; needs internet)

```powershell
uv run python -m tools.cli ingest windsites                         # OSM turbines -> static_data/raw/windsites/
uv run python -m tools.cli ingest openmeteo --start 2026-05-30 --end 2026-11-02T06:00
$env:FINGRID_API_KEY="..."   # or put FINGRID_API_KEY=... in .env at the repo root (gitignored)
uv run python -m tools.cli ingest fingrid --datasets 75 --start 2026-05-31 --end 2026-11-02T07:00
```

- Open-Meteo: Single Runs API only, 4 runs a day per model, about 620 requests per model for the
  whole period. Raw responses are cached in `static_data/raw/openmeteo/`, so a rerun resumes.
- Fingrid: new series get new `series_id`s and a conservative availability rule; package series are
  only extended past the package end, never overwritten.

## Model versions

- `<name>-val`: trained on targets published before 7 Sep 2026; use it for validation scores.
- `<name>`: trained up to 4 Oct 2026 (training cutoff); use it for the test submission and dashboard.
  Its forecasts for the validation period are in-sample.

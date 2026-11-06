# Imbalance Price Forecast (Since AI 2026, Turku Energia challenge)

WeatherSensAI team: forecast the Finnish imbalance price for the next 10 hours in 15-minute steps
(P10/P50/P90, regulation direction, spike probabilities), and a situational dashboard for energy
experts.

## Repository layout

| Folder | Purpose |
|---|---|
| `backend/` | Python service that does the heavy lifting: feature building, model inference, alerts, API |
| `backend/imbalance/` | Installable core package shared by the backend and the tools (features, store, model) |
| `backend/api/` | FastAPI app and routes for the dashboard |
| `backend/artifacts/` | Trained model versions (gitignored) |
| `backend/infer_data/` | Inferred 10 h forecast sets, one row per model version, origin and step (gitignored) |
| `frontend/` | React (Vite + TypeScript) dashboard |
| `static_data/` | Source data: raw pulls and the DuckDB store (gitignored, see its README) |
| `tools/ingest/` | Fetch and normalise data into `static_data/` |
| `tools/training/` | Model training and configs |
| `tools/eval/` | Scoring, submission export, single runs, leakage checks, debugging |
| `tools/starter_package/` | The organiser's starter package, **unchanged** (no data files) |
| `docs/` | Evaluation report, data sources and licences, slides |

## Ground rules

- `tools/starter_package/` is the organiser's locked package. Never edit it. The submission format,
  validator (`validate_submission.py`) and scorer (`score.py`) there are the source of truth.
- Data availability rule: at forecast origin `t`, use a row only if `first_usable_origin_utc <= t`.
  Every source we add gets the same column.
- Nord Pool spot data is licensed to Turku Energia for the hackathon only. Never commit anything
  under `static_data/`, `backend/infer_data/` or `backend/artifacts/`, and delete the data after the event.

## Setup (Windows, macOS, Linux)

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Put the starter package data files (`inputs.parquet`, `inputs.csv`, `spot_nordpool.csv`,
`actuals_validation.csv`, `quality_report.*`) into `static_data/raw/starter/`.

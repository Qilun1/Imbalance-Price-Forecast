# Imbalance Price Forecast (Since AI 2026, Turku Energia challenge)

WeatherSensAI team: forecast the Finnish imbalance price for the next 10 hours in 15-minute steps
(P10/P50/P90, regulation direction, spike probabilities), and a situational dashboard for energy
experts.

## Run the dashboard

On Windows, from this folder:

```powershell
.\start-dashboard.cmd          # invented mock data, needs no licensed files
.\start-dashboard.cmd real     # the pipeline's forecasts, see tools/README.md
```

Other systems and details: `frontend/README.md`.

## Repository layout

| Folder | Purpose |
|---|---|
| `backend/` | Python service that does the heavy lifting: feature building, model inference, alerts, API |
| `backend/imbalance/` | Installable core package shared by the backend and the tools (features, store, model) |
| `backend/api/` | FastAPI app and routes for the dashboard |
| `backend/artifacts/` | Trained model versions (gitignored) |
| `backend/infer_data/` | Inferred 10 h forecast sets, one row per model version, origin and step (gitignored) |
| `frontend/` | Next.js dashboard, see `frontend/README.md` |
| `mockup/` | Plain HTML/JS mockup of the notification chat on the event classifiers, served at `/mockup` (separate from `frontend/`) |
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
- **Never commit data** (AGENTS.md rule 0). Only code, configs, docs and our own trained models.
- Nord Pool spot data is licensed to Turku Energia for the hackathon only. Never commit anything
  under `static_data/` or `backend/infer_data/` (in `backend/artifacts/` only our own models), and
  delete the data after the event.

## Setup (Windows, macOS, Linux)

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
git config core.hooksPath .githooks     # once per clone: blocks commits that contain data
cp .env.example .env                    # then fill in FINGRID_API_KEY
```

API keys live only in `.env` (gitignored) or in environment variables of the same name; see
`.env.example` for which sources need a key and where to get one. `ENTSOE_API_TOKEN` is not needed:
the ENTSO-E data comes ready-made in the starter package.

The starter package data files (`inputs.parquet`, `inputs.csv`, `spot_nordpool.csv`,
`actuals_validation.csv`, `quality_report.*`) go to `static_data/raw/starter/`: `ingest starter --src`
copies them there (see below).

### Agent skills (local only, not in git)

The coding-agent skills in `.claude/skills/` (Claude Code) and `.agents/skills/` (other agents) are
third-party, so they are gitignored. They used to be committed twice (610 of the repo's 721 files).
`skills-lock.json` records each skill's source and content hash.

**Heads-up when pulling:** the commit that untracked them (`e5be3de`) deletes your local copies on the
next pull or merge, because git removes files that stop being tracked. Back them up first if you
use them:

```powershell
Copy-Item -Recurse .claude\skills $env:TEMP\claude-skills-backup   # before pulling
Copy-Item -Recurse $env:TEMP\claude-skills-backup .claude\skills   # after pulling
```

Or reinstall from the sources in `skills-lock.json` (the CLI asks which skills and agents):

```bash
npx skills add vercel-labs/agent-skills                 # deploy-to-vercel, vercel-*, web-design-guidelines, writing-guidelines
npx skills add vercel-labs/agent-browser                # agent-browser
npx skills add vercel-labs/skills                       # find-skills
npx skills add jakubkrehel/make-interfaces-feel-better  # make-interfaces-feel-better
```

## Reproduce the submission

Needs `FINGRID_API_KEY` in `.env` and internet access (Fingrid, Open-Meteo, OpenStreetMap). The
Open-Meteo pulls use the free tier and resume from their cache if a daily limit is hit.

```bash
# 1. Data: organiser package, wind sites, NWP locations, Fingrid measured wind, NWP runs
uv run python -m tools.cli ingest starter --src <path to starter_package_v1 or its data folder>
uv run python -m tools.cli ingest windsites
uv run python -m tools.cli ingest locations
uv run python -m tools.cli ingest fingrid --datasets 75 --start 2026-05-31 --end 2026-11-02T07:00
uv run python -m tools.cli ingest openmeteo --models ecmwf_ifs --group wind
uv run python -m tools.cli ingest openmeteo --models metno_nordic --group wind
uv run python -m tools.cli ingest openmeteo --models metno_nordic --group pop
# 2. Feature tables, then the two structural mixture members (train val + final, score, test export)
uv run python -m tools.cli features --set v4
uv run python -m tools.cli features --set v4m
uv run python -m tools.training.mixture_pipeline --config tools/training/configs/mix_v4b.yaml
uv run python -m tools.training.mixture_pipeline --config tools/training/configs/mix_v4mb.yaml
# 3. Average them, then apply the validation-fitted spike shift and band widths
uv run python -m tools.eval.ensemble --name ens_mix --members mix_v4b mix_v4mb --period val
uv run python -m tools.eval.ensemble --name ens_mix --members mix_v4b mix_v4mb --period test
uv run python -m tools.eval.spike_shift --model ens_mix --apply
uv run python -m tools.eval.band_width --model ens_mix_spk --apply
```

The submission is `static_data/work/submissions/ens_mix_spk_bw_test.csv` (submit it as
`forecast_backtest.csv`); every step runs the organiser's validator or scorer. More commands:
`tools/README.md`. Dashboard: `backend/api/README.md` (API, runs on mock data without licensed files)
and `frontend/README.md`. Data sources and licences: `docs/SOURCES_AND_LICENCES.md`.

## About the challenge (organiser's notes)

The files listed below are the organiser's downloads; they are not in this repository.

### Since AI Hackathon 2026 - Turku Energia challenge

Imbalance price forecast, 10 hours ahead

### Contents

| File | Description |
|---|---|
| `1_Turku_Energia_Challenge_Brief_EN.pdf` | Challenge brief (English translation) |
| `starter_package_v1.zip` | Data, validation and scoring scripts, baseline |
| `SHA256SUMS.txt` | Checksums for the starter package |

### Start here

1. Read the challenge brief.
2. Unzip `starter_package_v1.zip` and read `starter_package_v1/README.md`.
   It defines the data rule (`first_usable_origin_utc`), the submission
   format and the scoring.
3. Check your submission with `validate_submission.py` before submitting.
   Submissions are made via the Since AI platform.

### Data terms

The Nord Pool spot price data (`data/spot_nordpool.csv`) is licensed by
Turku Energia for use during the hackathon only: no redistribution and
no publication in public repositories. Delete the data after the event.
Do not commit the data files to a public repository.

Note: `starter_package_v1.zip` is the locked package of 3 Nov 2026.
Verify it with: `sha256sum -c SHA256SUMS.txt --ignore-missing`

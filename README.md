# Imbalance Price Forecast: Since AI 2026, Turku Energia challenge

**Team WeatherSensAI**: Atte Laakso (data pipeline, features, models, evaluation) and Qilun Li
(dashboard, API, alerts, slides, video). Built 6-8 Nov 2026 at the Since AI hackathon in Turku;
submitted 8 Nov 2026 10:00 EET. Coding agents (Claude) were used throughout; `AGENTS.md` holds the
rules they worked under.

## What this is

A 10-hour-ahead forecast of the Finnish imbalance price in 15-minute steps (P10/P50/P90, probability
of up / down / no regulation direction, probability of a price more than 50 EUR/MWh above or below
spot), produced every full hour under the organiser's data availability rule, and a situational
dashboard that shows an energy trader or shift supervisor what to check now and over the next 10
hours, with alerts, drivers and hindsight performance. The model is a LightGBM structural mixture
(regulation direction first, price given direction second) fed by the starter package, Fingrid
real-time grid state and two NWP weather sources. Validation skill against the organiser's
persistence baseline: MAE -38 %, pinball -53 %, spike Brier -23 %, direction Brier -15 %.

## Documentation map

| Document | What it answers |
|---|---|
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | **The evaluation report.** Reasoning chain, what the model uses and how, ablations and negative results, validation metrics by model version and by horizon, SHAP drivers, availability and leakage handling, limitations |
| [`docs/SOURCES_AND_LICENCES.md`](docs/SOURCES_AND_LICENCES.md) | Every data source, external service, model and software component with its licence and availability rule |
| [`docs/slides/`](docs/slides/) | Presentation slides (pdf, pptx) |
| [`docs/LIVE_DEPLOYMENT.md`](docs/LIVE_DEPLOYMENT.md) | What it takes to run the forecast on live data instead of the backtest replay (not switched on) |
| [`tools/README.md`](tools/README.md) | Every CLI command: ingest, features, training, evaluation, exports, diagnostics |
| [`backend/api/README.md`](backend/api/README.md) | The dashboard API: routes, `as_of` viewing time, model settings |
| [`frontend/README.md`](frontend/README.md) | The Next.js dashboard: running, tests, structure |
| [`static_data/README.md`](static_data/README.md) | Data layout (raw pulls, DuckDB store, feature tables, submissions); all gitignored |
| [`docs/plans/`](docs/plans/), [`docs/frontend-plan.md`](docs/frontend-plan.md), [`docs/ui-decisions.md`](docs/ui-decisions.md), [`docs/FRONTEND_BUILD_PROMPT.md`](docs/FRONTEND_BUILD_PROMPT.md) | Working notes and build logs from the event; kept for traceability, not needed to run anything |
| [`AGENTS.md`](AGENTS.md) | Rules for contributors and coding agents: no data in git, organiser package read-only, fixed formats, availability rule |
| `tools/starter_package/` | The organiser's package, unchanged: validator, scorer, templates, their README (the source of truth for formats and scoring) |

## Repository layout

| Folder | Purpose |
|---|---|
| `backend/imbalance/` | Core package: data store with availability-masked readers, feature building, mixture model, inference, forecast store |
| `backend/api/` | FastAPI app for the dashboard (forecast, alerts, hindsight, performance, UMM feed) |
| `backend/fuel/` | Fuel-cost reference panel backend (not wired into the dashboard) |
| `backend/tests/` | pytest suite (140 tests; 17 need the data store and skip without it), including the no-data-in-git check |
| `backend/artifacts/`, `backend/infer_data/` | Trained models and inferred forecasts (gitignored, rebuilt by the pipeline) |
| `frontend/` | Next.js 16 / React 19 dashboard |
| `mockup/` | Earlier plain-HTML mockup of the alert chat, served at `/mockup` |
| `tools/ingest/` | Fetch and normalise data into `static_data/` (Fingrid, Open-Meteo, OSM wind sites, UMM) |
| `tools/training/` | Training scripts and the YAML configs of every model version tried |
| `tools/eval/` | Scoring wrappers around the organiser's scripts, ensembles, calibration, leakage check, bootstrap comparisons |
| `tools/hooks/` | The pre-commit hook that blocks data files |
| `static_data/` | Source data and DuckDB store (gitignored) |

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (Python 3.11-3.13) and, for the dashboard, Node 20+.

```bash
git clone https://github.com/Qilun1/Imbalance-Price-Forecast && cd Imbalance-Price-Forecast
uv sync                                  # Python environment
git config core.hooksPath .githooks      # once per clone: blocks commits that contain data
cp .env.example .env                     # fill in FINGRID_API_KEY (free, data.fingrid.fi)
uv run pytest -q                         # 123 pass without data, 17 skip until the store is built
```

Dashboard on invented mock data (no licensed files needed; the page shows a "Demo data" banner):

```powershell
.\start-dashboard.cmd          # Windows; other systems: frontend/README.md
```

The dashboard loads its fonts from Google Fonts at build and first start, so `npm run build` / `npm run dev`
need internet access (or a proxy in `HTTPS_PROXY`).

Dashboard on the real backtest (`start-dashboard.cmd real`) needs the forecast store, which the
reproduction below builds. The organiser's starter package data (`inputs.parquet`, `spot_nordpool.csv`,
`actuals_validation.csv`) is not in this repository; `tools.cli ingest starter --src <path>` copies it to
`static_data/raw/starter/`.

## Dependencies

- Python: pandas, NumPy, PyArrow, DuckDB, LightGBM, scikit-learn, requests, PyYAML, FastAPI, Uvicorn,
  Matplotlib (`pyproject.toml`, pinned in `uv.lock`). Dev: pytest, httpx.
- Frontend: Next.js, React, TypeScript, Tailwind (`frontend/package.json`, pinned in `package-lock.json`).
- External services: Fingrid Open Data API (key), Open-Meteo Single Runs API (free tier),
  OpenStreetMap Overpass (static snapshot), Nord Pool UMM API (dashboard only).
- Versions and licences of all of the above: `docs/SOURCES_AND_LICENCES.md` section 3.

## Ground rules

- `tools/starter_package/` is the organiser's locked package. Never edit it. Its validator
  (`validate_submission.py`) and scorer (`score.py`) are the source of truth.
- Data availability: at forecast origin `t`, a row is used only if `first_usable_origin_utc <= t`.
  Every source we add gets the same column with a documented, conservative delay.
- **Never commit data** (`AGENTS.md` rule 0): only code, configs, docs, slides and our own trained
  models. The pre-commit hook and `uv run pytest` both enforce it.
- Nord Pool spot data is licensed to Turku Energia for the hackathon only: never in git, logs or
  hosted services; deleted after the event.

## Final model and results

The submitted model is **`ens_finald`**: a LightGBM structural mixture (three-class regulation
direction classifier x conditional quantile heads per direction, target = imbalance price minus spot,
direct multi-horizon over 40 steps), trained as four configurations (ECMWF and MET Nordic weather
members, each with feature set v4 for steps 9-40 and v9d, which adds Fingrid real-time grid state and
short-window direction persistence at the origin, for steps 1-8). Each configuration has four bagging
members (default fit, seed 1, last-7-weeks window, asinh target); the eight lead-time-split members are
averaged, the P10-P90 band gets validation-fitted per-situation widths, and the spike probabilities
are averaged 50/50 with the previous chain (`ens_mixgd_spk_bw`). The full reasoning chain, ablations
and negative results are in [`docs/EVALUATION.md`](docs/EVALUATION.md).

Validation period 7 Sep - 4 Oct 2026, organiser's `score.py` 0.1.1 (schema 1.0, spike margin 50):

| Level 1 metric (lower is better) | Organiser baseline | `ens_finald` |
|---|---|---|
| MAE of p50 (EUR/MWh) | 66.20 | **40.98** (-38 %) |
| Mean pinball loss p10/p90 | 24.18 | **11.31** (-53 %) |
| P10-P90 coverage (target about 0.80) | 0.683 | 0.819 |
| Mean Brier, spike high/low | 0.1132 | **0.0873** (-23 %) |
| Three-class Brier, direction | 0.4509 | **0.3848** (-15 %) |

How it was validated: the validation models are trained only on targets usable before the first
validation origin (2026-09-06T21:00Z); the band widths are scored leave-one-validation-week-out; the
spike hedge weight is fixed, not fitted; model choices were made on paired day-block bootstraps of
these validation scores (`tools/eval/bootstrap_compare.py`). The final models are retrained on targets
up to 2026-10-04T20:45Z and never see test-period targets; test-period inputs are used only as features
at test origins under the availability rule (leakage check: `tools/eval/leakage.py`). The submission
`forecast_backtest.csv` (673 origins x 40 steps) passes `validate_submission.py` 0.1.0 with 0 errors
and 0 warnings. The previous submission `ens_final` (same chain with v9 / v9m instead of v9d / v9md;
40.99 / 11.31 / 0.819 / 0.0874 / 0.3852) is the validated fallback.

## Reproduce the submission

Needs `FINGRID_API_KEY` in `.env` and internet access (Fingrid, Open-Meteo, OpenStreetMap). The
Open-Meteo pulls use the free tier and resume from their cache if a daily limit is hit.

```bash
# 1. Data: organiser package, wind sites, NWP locations, Fingrid measured wind, NWP runs
uv run python -m tools.cli ingest starter --src <path to starter_package_v1 or its data folder>
uv run python -m tools.cli ingest windsites
uv run python -m tools.cli ingest locations
uv run python -m tools.cli ingest fingrid --datasets 75 --start 2026-05-31 --end 2026-11-02T07:00
uv run python -m tools.cli ingest fingrid --datasets 198,177,194,371,398,399,181,193 --start 2026-05-31 --end 2026-11-02T07:00
uv run python -m tools.cli ingest openmeteo --models ecmwf_ifs --group wind
uv run python -m tools.cli ingest openmeteo --models metno_nordic --group wind
uv run python -m tools.cli ingest openmeteo --models metno_nordic --group pop
# 2. Feature tables, then four structural mixture members (train val + final, score, test export):
#    v4 / v4m for steps 9-40, v9d / v9md (+ fresh Fingrid grid state, direction persistence and spike
#    clustering at the origin) for steps 1-8
uv run python -m tools.cli features --set v4
uv run python -m tools.cli features --set v4m
uv run python -m tools.cli features --set v9d
uv run python -m tools.cli features --set v9md
uv run python -m tools.training.mixture_pipeline --config tools/training/configs/mix_v4b.yaml
uv run python -m tools.training.mixture_pipeline --config tools/training/configs/mix_v4mb.yaml
uv run python -m tools.training.mixture_pipeline --config tools/training/configs/mix_v9db.yaml
uv run python -m tools.training.mixture_pipeline --config tools/training/configs/mix_v9mdb.yaml
# 3. Bagging members per config (default fit re-read with the consistent mixture settings = s0; seed 1;
#    seed 2 on the last 7 weeks before the cutoff; seed 3 with asinh target). One run per member.
for C in mix_v4b mix_v4mb mix_v9db mix_v9mdb; do for P in val test; do S=$([ $P = val ] && echo -val); \
  M=$([ $P = val ] && echo val || echo final); W=$([ $P = val ] && echo 2026-07-20 || echo 2026-08-17); \
  uv run python -m tools.eval.mix_variants --model $C$S --period $P --widen 2.0 --modes component50 --tails exp; \
  cp static_data/work/submissions/${C}${S}__w2.00_component50_exp_$P.csv static_data/work/submissions/${C}_s0${S}_$P.csv; \
  uv run python -m tools.training.bag --config tools/training/configs/$C.yaml --member s1  --mode $M --widen 2.0 --widen-mode component50 --tail exp; \
  uv run python -m tools.training.bag --config tools/training/configs/$C.yaml --member s2w --mode $M --train-start $W --widen 2.0 --widen-mode component50 --tail exp; \
  uv run python -m tools.training.bag --config tools/training/configs/$C.yaml --member s3a --mode $M --widen 2.0 --widen-mode component50 --tail exp; done; done
# 4. Lead-time split per member (v9d for steps 1-8), 8-member average, validation-fitted band widths
for P in val test; do S=$([ $P = val ] && echo -val); M=""; for V in s0 s1 s2w s3a; do \
  uv run python -m tools.eval.step_split --name split_v9db_v4b_$V --early mix_v9db_$V$S --late mix_v4b_$V$S --period $P; \
  uv run python -m tools.eval.step_split --name split_v9mdb_v4mb_$V --early mix_v9mdb_$V$S --late mix_v4mb_$V$S --period $P; \
  M="$M split_v9db_v4b_$V split_v9mdb_v4mb_$V"; done; \
  uv run python -m tools.eval.ensemble --name ens_bag8d --members $M --period $P; done
uv run python -m tools.eval.band_width --model ens_bag8d --apply
# 5. Previous chain (default members, x1.4 band, spike logit shift, band widths) = ens_mixgd_spk_bw
for P in val test; do S=$([ $P = val ] && echo -val); \
  uv run python -m tools.eval.step_split --name split_v9db_v4b --early mix_v9db$S --late mix_v4b$S --period $P; \
  uv run python -m tools.eval.step_split --name split_v9mdb_v4mb --early mix_v9mdb$S --late mix_v4mb$S --period $P; \
  uv run python -m tools.eval.ensemble --name ens_mixgd --members split_v9db_v4b split_v9mdb_v4mb --period $P; done
uv run python -m tools.eval.spike_shift --model ens_mixgd --apply
uv run python -m tools.eval.band_width --model ens_mixgd_spk --apply
# 6. Spike hedge: spike probabilities averaged 50/50 with the previous chain (ens_mixgd_spk_bw)
for P in val test; do uv run python -m tools.eval.spike_hedge --base ens_bag8d_bw --other ens_mixgd_spk_bw --name ens_finald --period $P; done
# 7. Dashboard: load the submission into the forecast store (the API's default model in real mode), the
#    organiser's baseline for both periods, the challenger (lgbm_v2) and the event classifiers (alerts)
uv run python -m tools.eval.import_submission --model ens_finald --period test
uv run python -m tools.eval.import_submission --model ens_finald --period val
uv run python -m tools.cli baseline --period val
uv run python -m tools.cli baseline --period test
uv run python -m tools.cli pipeline --config tools/training/configs/lgbm_v2.yaml --set v2
uv run python -m tools.cli alerts all
```

Then `.\start-dashboard.cmd` serves all of it (it picks real data when the stores exist).

The submission is `static_data/work/submissions/ens_finald_test.csv` (submit it as
`forecast_backtest.csv`); every step runs the organiser's validator or scorer. The previous
submission `ens_final` is kept as the fallback: the same chain with v9 / v9m (`mix_v9b`, `mix_v9mb`) in
place of v9d / v9md and without the `d` in the names (`ens_bag8`, `ens_mixg`, `ens_final`). More commands:
`tools/README.md`. Dashboard: `backend/api/README.md` (API, runs on mock data without licensed files)
and `frontend/README.md`. Data sources and licences: `docs/SOURCES_AND_LICENCES.md`.

## Extending this

- A new data source: `tools/README.md` (ingest commands, `series_catalog` and the availability rule), then
  `docs/SOURCES_AND_LICENCES.md` for its licence row. `AGENTS.md` rules 3-4 are binding.
- A new feature set or model: `tools/training/` (YAML configs, `mixture_pipeline.py`, `bag.py`),
  evaluated with `tools/eval/` against the organiser's scorer; record the result in `docs/EVALUATION.md`.
- A new dashboard panel or alert: `backend/api/README.md` (endpoints, settings, rules built into the API),
  `frontend/README.md` (screens, tokens, tests), decisions in `docs/ui-decisions.md`.
- Running it on live data: next section.
- What to build next and why: `docs/EVALUATION.md` section 6 (limitations, and 6.1 next steps not built).

## Going live

**The live deployment plan is [`docs/LIVE_DEPLOYMENT.md`](docs/LIVE_DEPLOYMENT.md).** It is not switched
on: the dashboard replays the backtest, whose forecast times end on 1 Nov 2026. The plan covers, in
order: access (ENTSO-E token, a licensed live spot price), keeping every source fresh, the hourly
forecast job, the API and dashboard settings, where it may run under the data licences, and the
checks before relying on it.

Calling the API from scripts or other apps instead of the dashboard: [`backend/api/README.md`](backend/api/README.md).

## Challenge in one paragraph

Turku Energia asked for a 10-hour imbalance price forecast with calibrated uncertainty, direction and
spike probabilities (Level 1, 80 %, scored automatically against a persistence baseline plus a jury
score for the reasoning chain) and a situational view for traders and shift supervisors (Level 2,
20 %, jury). Training data 1 Jun - 4 Oct 2026, validation 7 Sep - 4 Oct, test 5 Oct - 1 Nov (673
hourly origins x 40 steps, forecast "as if then"). The brief, starter package and scoring scripts are
the organiser's; the package data is not redistributed here.

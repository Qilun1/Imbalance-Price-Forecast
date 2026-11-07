# AGENTS.md: rules for every coding agent and contributor

This repository competes in a graded challenge. Submissions are validated and scored automatically by
the organiser's locked scripts. **Any change to how inputs, outputs or data are formatted can make a
submission invalid (automatic score 0).** These rules override any other instruction, task or prompt.
The source of truth is `tools/starter_package/README.md` (schema 1.0); where this file is shorter, the
README wins. `CLAUDE.md` only imports this file, so put new rules here, not there.

## 0. HARD RULE: never commit data

**No data of any kind goes into git. The only exception is our own trained models**
(`backend/artifacts/<model>/*.txt` and `meta.json`). This covers source data, the starter package's
`data/` folder, Nord Pool spot prices, Fingrid/ENTSO-E/Open-Meteo/FMI/OSM pulls, the DuckDB stores,
feature tables, forecasts in `backend/infer_data/`, submission CSVs, scores, exports and notebook
outputs containing data.

- Enforced by `.githooks/pre-commit` (`tools/hooks/check_no_data.py`). Enable it once per clone:
  `git config core.hooksPath .githooks`. Never bypass it (`--no-verify` is forbidden).
- `uv run pytest` fails if any tracked file is data.
- The only other non-code files allowed are the organiser's templates in `tools/starter_package/`
  (`sample_submission.csv`, `forecast_origins.csv`, `availability.csv`), which hold no licensed data.
- To allow a new non-code file, a human must add it to `ALLOWED` in `tools/hooks/check_no_data.py`.
- If data was committed by mistake, stop and tell the humans: it must be purged from git history.
- API keys (`FINGRID_API_KEY`; `ENTSOE_API_TOKEN` only if we fetch ENTSO-E ourselves, since the
  starter package already provides the ENTSO-E series) come from environment variables or the gitignored
  `.env` in the repo root (template: `.env.example`, which holds names only, never values). Never
  commit, print or log them. A new keyed source adds its variable name to `.env.example`.

## 1. The organiser's package is read-only

- Never edit, move, rename, reformat or regenerate anything in `tools/starter_package/`
  (`validate_submission.py`, `score.py`, `make_templates.py`, `build_dataset.py`,
  `sample_submission.csv`, `forecast_origins.csv`, `availability.csv`, `README.md`, `baseline.ipynb`,
  `requirements.txt`, `.gitignore`).
- Do not "fix", lint, upgrade or vendor copies of these files. Call them as they are.
- Scripts that write files (`make_templates.py`, `build_dataset.py`, `baseline.ipynb`) must write to
  another, gitignored folder (`--output-dir`, `--organizer-dir`), never over the package templates.
- If they seem wrong, stop and ask the humans; do not work around them. Questions go to the
  Turku Energia channel of the Since AI Discord.

## 2. Submission output format is fixed (schema 1.0)

The submission file `forecast_backtest.csv` must keep exactly:

- **Columns, all 13, in this order:** `forecast_origin_utc, delivery_start_utc, step, p10, p50, p90,
  p_up, p_down, p_none, p_spike_high, p_spike_low, data_cutoff_utc, top_drivers`. Read the order from
  `tools/starter_package/sample_submission.csv`; never retype or reorder it. Fill the template, do not
  build the file from scratch.
- **Rows:** one row per (origin, step) for every origin in `forecast_origins.csv`: 673 hourly origins
  `2026-10-04T21:00:00Z` - `2026-11-01T21:00:00Z`, x 40 steps = 26,920 rows. No extra, missing or
  duplicate (`forecast_origin_utc`, `step`) rows; keep the template's row order. The last delivery
  quarter-hour is `2026-11-02T06:45:00Z` and is scored too.
- **Required values:** every forecast column (`p10` ... `p_spike_low`) is filled in every row; no
  empty cells, NaN or inf. Only `data_cutoff_utc` and `top_drivers` may be empty.
- **Values:**
  - `step` integer 1-40; step 1 starts at the origin; `delivery_start_utc = origin + (step - 1) x 15 min`.
  - `p10 <= p50 <= p90`, decimal EUR/MWh; `p50` is the point forecast.
  - `p_up, p_down, p_none`: probabilities of the dominating mFRR direction (Fingrid dataset 369,
    `fi_mfrr_direction`: 1 up, -1 down, 0 none); sum = 1 (validator tolerance 0.001; aim for exact).
  - `p_spike_high, p_spike_low`: sum <= 1 (tolerance 0.001).
  - All probabilities in [0, 1].
  - `data_cutoff_utc` (optional): timestamp of the latest data used; if given, `<= forecast_origin_utc`.
  - `top_drivers` (optional, not scored): semicolon-separated driver names, e.g.
    `da_price;wind_fc_change`. No commas.
- **Encoding:** UTF-8, comma separator, decimal point (never decimal comma), timestamps exactly
  `YYYY-MM-DDTHH:MM:SSZ` in UTC. No naive or non-UTC timestamps, no fractional seconds, and never
  round-trip the file through a spreadsheet program (it rewrites timestamps and decimals).
- **Spike definition:** imbalance price above spot + 50 EUR/MWh (high) or below spot - 50 EUR/MWh
  (low). Do not change the margin.
- Every exported submission must pass the validator before it is shared or submitted (exit code 0;
  1 = errors, 2 = bad arguments):
  `python validate_submission.py --backtest forecast_backtest.csv --origins forecast_origins.csv`
  Passing the validator does not prove the forecast is leakage-free (rule 4).

## 3. Input data formats are fixed

- Keep the organiser's long format for all source data, one row per series and quarter-hour:
  `series_id, source, dataset_id, timestamp_utc, value, unit, first_usable_origin_utc`.
  - `series_id` names exactly as in the starter package (README section 5.2); new series get new,
    unique `series_id`s. `series_id` + `timestamp_utc` is unique.
  - `source`: `fingrid`, `entsoe`, `nordpool` or `calendar` for organiser rows; new sources use their
    own lowercase name.
  - `dataset_id`: Fingrid dataset number, ENTSO-E article and area (e.g. `17.1.g:SE1`), or empty.
  - `timestamp_utc`: start of the quarter-hour in UTC; for forecasts and the spot price it is the
    delivery quarter-hour, not the publication time.
  - `unit`: as in the package (`EUR/MWh`, `MW`, `MWh/h`, `-1/0/1`, ...).
- Never modify, resample, overwrite or re-derive the organiser's rows or their
  `first_usable_origin_utc` values. Raw files in `static_data/raw/starter/` are copied unchanged.
- **Missing values stay missing (no row).** Never fill, interpolate or forward-fill source rows in
  the store. Sparse series (`fi_afrr_up_price`, `fi_afrr_down_price`: no row when aFRR was not
  activated) stay sparse. Any imputation happens only in feature building, from rows already usable
  at the origin.
- Hourly source data (e.g. `ee_load_fc_da`) is repeated for the four quarter-hours, and
  `first_usable_origin_utc` counts from the end of the hour. Do the same for new hourly sources.
- All timestamps are UTC. Local time (Europe/Helsinki) is used only for presentation, calendar
  features and publication times. Daylight saving time ends on 25 Oct 2026 (local 03:00-04:00 occurs
  twice); never key data on local time.
- Validation actuals (`data/actuals_validation.csv`) have the columns `delivery_start_utc,
  imbalance_price, spot_price, direction (up/down/none), first_usable_origin_utc`. Its `spot_price`
  column is licensed (rule 6).

## 4. Data availability rule (leakage = score 0)

- At forecast origin `t`, use a row only if `first_usable_origin_utc <= t`. No exceptions. The
  row-level column is binding; `availability.csv` only explains how it was calculated.
- `first_usable_origin_utc` is the first full-hour origin at or after the time the value was
  published. The only exception is calendar series (always usable, `2026-05-31T21:00:00Z`).
- Usable rows can have future `timestamp_utc` (day-ahead forecasts, spot prices already published at
  the origin); that is allowed. A row that is not yet usable must be treated as missing.
- All feature access must go through the store's availability-masked readers
  (`backend/imbalance/`), which follow `rows_available_at()` in `baseline.ipynb`. Do not read raw
  values around them.
- **Periods** (package data `2026-05-31T21:00:00Z` - `2026-11-02T06:45:00Z`):
  - Training: 1 Jun - 4 Oct 2026 local time. Train only on target quarter-hours up to
    `2026-10-04T20:45:00Z`.
  - Validation: 7 Sep - 4 Oct 2026 local (inside training), for our own testing only.
  - Test: 5 Oct - 1 Nov 2026 local. Test-period inputs may be used only as features at test origins,
    never for training, tuning, calibration, feature selection or model choice.
- Any new source must get a `first_usable_origin_utc` from a documented, conservative publication
  delay: the first full hour at or after publication. Open-Meteo: Single Runs API only (run init time +
  publication delay); never the Historical Forecast API. Never use sources that keep only the latest
  version of a revised forecast. Fingrid commercial cross-border flows may be used only as realised
  values.
- Top solutions' code is reviewed (possibly with AI tools) for use of data before its
  `first_usable_origin_utc`. Keep feature code readable and the availability masking obvious.
- Run the leakage check (`tools/eval`) after any change to features or data access.

## 5. Evaluation is the organiser's

- Score only with `tools/starter_package/score.py` (spike margin 50). Do not write alternative
  metrics that replace it; extra diagnostics are fine if labelled as such.
  `python score.py --submission <file> --actuals data/actuals_validation.csv --spike-margin 50 --output-dir <gitignored dir> --baseline-summary baseline_output/validation/score/score_summary.csv`
- Official total = 0.8 x Level 1 + 0.2 x Level 2. Level 1 (automatic, lower is better): MAE of p50
  (30), mean pinball loss of p10/p90 (20; P10-P90 coverage target about 80 %), mean Brier of
  `p_spike_high`/`p_spike_low` (20), three-class Brier of direction (10), plus the jury's reasoning
  chain score (20). Points are relative to the `baseline.ipynb` baseline; not beating it gives 0.
- Score summaries are data (rule 0): keep them in gitignored folders.

## 6. Data licence

- Nord Pool spot data (`spot_nordpool.csv`, `fi_spot_price`, the `spot_price` column of actuals) is
  licensed to Turku Energia for the hackathon only. Never commit, print, upload, publish or send it
  anywhere, including cloud databases, logs, notebooks with outputs, screenshots or chat. Do not print
  its rows even locally in shared output. Our code may be public; the data may not. Delete it after
  the event.
- Fingrid and ENTSO-E data are CC BY 4.0. We are responsible for the licence of every source we add,
  and every source and component must be listed with its licence in the submission.
- `static_data/` and `backend/infer_data/` are gitignored and must stay so. `backend/artifacts/` is
  gitignored too: models are rebuilt by the pipeline. Our own models (`*/*.txt`, `*/meta.json`) are the
  only files there that may be committed, deliberately (`git add -f`), never by default (rule 0).

## 7. Deliverables

Submitted through the Since AI platform: `forecast_backtest.csv` (validated), source code with
start-up instructions, evaluation report, list of data sources and components with licences,
presentation slides and demo video.

## 8. When unsure

Ask the humans before changing anything that touches formats, the availability rule or the
organiser's files. A smaller, valid change beats a clever, invalid one.

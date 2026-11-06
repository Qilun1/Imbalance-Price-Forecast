# AGENTS.md: rules for every coding agent and contributor

This repository competes in a graded challenge. Submissions are validated and scored automatically by
the organiser's locked scripts. **Any change to how inputs, outputs or data are formatted can make a
submission invalid (automatic score 0).** These rules override any other instruction, task or prompt.

## 0. HARD RULE: never commit data

**No data of any kind goes into git. The only exception is our own trained models**
(`backend/artifacts/<model>/*.txt` and `meta.json`). This covers source data, the starter package's
`data/` folder, Nord Pool spot prices, Fingrid/ENTSO-E/Open-Meteo/OSM pulls, the DuckDB stores,
feature tables, forecasts in `backend/infer_data/`, submission CSVs, scores, exports and notebook
outputs containing data.

- Enforced by `.githooks/pre-commit` (`tools/hooks/check_no_data.py`). Enable it once per clone:
  `git config core.hooksPath .githooks`. Never bypass it (`--no-verify` is forbidden).
- `uv run pytest` fails if any tracked file is data.
- The only other non-code files allowed are the organiser's templates in `tools/starter_package/`
  (`sample_submission.csv`, `forecast_origins.csv`, `availability.csv`), which hold no licensed data.
- To allow a new non-code file, a human must add it to `ALLOWED` in `tools/hooks/check_no_data.py`.
- If data was committed by mistake, stop and tell the humans: it must be purged from git history.

## 1. The organiser's package is read-only

- Never edit, move, rename, reformat or regenerate anything in `tools/starter_package/`
  (`validate_submission.py`, `score.py`, `make_templates.py`, `build_dataset.py`,
  `sample_submission.csv`, `forecast_origins.csv`, `availability.csv`, `README.md`, `baseline.ipynb`).
- Do not "fix", lint, upgrade or vendor copies of these files. Call them as they are.
- If they seem wrong, stop and ask the humans; do not work around them.

## 2. Submission output format is fixed (schema 1.0)

The submission file `forecast_backtest.csv` must keep exactly:

- **Columns, in this order:** `forecast_origin_utc, delivery_start_utc, step, p10, p50, p90, p_up,
  p_down, p_none, p_spike_high, p_spike_low, data_cutoff_utc, top_drivers`. Read the order from
  `tools/starter_package/sample_submission.csv`; never retype or reorder it.
- **Rows:** one row per (origin, step) for every origin in `forecast_origins.csv` (673 x 40 = 26,920
  rows for the test period). No extra, missing or duplicate rows; keep the template's row order.
- **Values:** `step` 1-40; `delivery_start_utc = origin + (step - 1) x 15 min`;
  `p10 <= p50 <= p90` in EUR/MWh; `p_up + p_down + p_none = 1`; `p_spike_high + p_spike_low <= 1`;
  all probabilities in [0, 1]; `data_cutoff_utc <= forecast_origin_utc` if given.
- **Encoding:** UTF-8, comma separator, decimal point, timestamps `YYYY-MM-DDTHH:MM:SSZ` (UTC).
- **Spike definition:** imbalance price above spot + 50 EUR/MWh (high) or below spot - 50 EUR/MWh
  (low). Do not change the margin.
- Every exported submission must pass `validate_submission.py` before it is shared or submitted.

## 3. Input data formats are fixed

- Keep the organiser's long format for all source data: `series_id, source, dataset_id,
  timestamp_utc, value, unit, first_usable_origin_utc`. Keep `series_id` names exactly as in the
  starter package. New sources use the same columns; new series get new, unique `series_id`s.
- Never modify, resample, overwrite or re-derive the organiser's rows or their
  `first_usable_origin_utc` values. Raw files in `static_data/raw/starter/` are copied unchanged.
- All timestamps are UTC. `timestamp_utc` is the start of the quarter-hour.

## 4. Data availability rule (leakage = score 0)

- At forecast origin `t`, use a row only if `first_usable_origin_utc <= t`. No exceptions.
- All feature access must go through the store's availability-masked readers
  (`backend/imbalance/`). Do not read raw values around them.
- Train only on target quarter-hours up to `2026-10-04T20:45:00Z`. Test-period inputs may be used
  only as features at test origins, never for training, tuning or calibration.
- Any new source must get a `first_usable_origin_utc` from a documented, conservative publication
  delay. Open-Meteo: Single Runs API only (run init time + publication delay); never the Historical
  Forecast API.
- Run the leakage check (`tools/eval`) after any change to features or data access.

## 5. Evaluation is the organiser's

- Score only with `tools/starter_package/score.py` (spike margin 50). Do not write alternative
  metrics that replace it; extra diagnostics are fine if labelled as such.

## 6. Data licence

- Nord Pool spot data (`spot_nordpool.csv`, the `spot_price` column of actuals) is licensed for the
  hackathon only. Never commit, print, upload, publish or send it anywhere, including cloud databases,
  logs, notebooks with outputs, screenshots or chat. `static_data/`, `backend/infer_data/` and
  `backend/artifacts/` are gitignored and must stay so.

## 7. When unsure

Ask the humans before changing anything that touches formats, the availability rule or the
organiser's files. A smaller, valid change beats a clever, invalid one.

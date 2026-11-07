# Live deployment plan (not switched on)

Everything needed to turn the backtest into real-time forecasts, in one place: data access, the
hourly job, API and dashboard settings, where it may run, and the checks before anyone relies on it.

**Status.** The dashboard replays the backtest: every forecast uses only data usable at its own
forecast time, but the forecast times end on 1 Nov 2026 and the store ends at the starter package end
(2 Nov 2026 06:45 UTC). Nothing below is switched on yet. Steps 1 and 2 wait for access, steps 3–5
are about a day of code and setup. The code is built for this: the availability rule, the store and
the models work for any forecast time.

## Checklist

1. [ ] ENTSO-E token and a licensed live spot price (step 1)
2. [ ] Every source ingested up to now, and kept fresh (step 2)
3. [ ] Hourly forecast job writing to `backend/infer_data/` (step 3)
4. [ ] API started with the live settings (step 4)
5. [ ] Dashboard built and pointed at the API (step 5)
6. [ ] Runs only where the licences allow (step 6)
7. [ ] Leakage check, delay probe, a week of watching (step 7)

## 1. Access (takes days, so start first)

| What | How | Goes in |
|---|---|---|
| `FINGRID_API_KEY` | Free key at <https://data.fingrid.fi> | `.env` (already used) |
| `ENTSOE_API_TOKEN` | Register at <https://transparency.entsoe.eu>, then email transparency@entsoe.eu with the subject "Restful API access" and your account e-mail. Several working days. | `.env` |
| A live spot price we may use | The Nord Pool file is licensed for the hackathon only. Use the ENTSO-E day-ahead price for Finland (document type A44, area `10YFI-1--------U`), or ask Turku Energia. | List it in `docs/SOURCES_AND_LICENCES.md` |
| Open-Meteo | No key. The free tier is non-commercial only; commercial use needs a paid plan. | — |

Keys live only in `.env` (gitignored) or environment variables of the same name; names in
`.env.example`. Never commit, print or log them.

## 2. Keep the data fresh

`<last>` is the newest timestamp already in the store (`uv run python -m tools.cli status`), `<now>`
the current UTC time. Ingests insert only; they never overwrite a stored row.

| Data | State | How |
|---|---|---|
| Fingrid measured series | Works now | `uv run python -m tools.cli ingest fingrid --datasets 319,244,106,375,376,369,124,74,75,188,191,198,177,194,371,398,399,181,193 --start <last> --end <now>`. First add the flows (55, 57, 60, 61) and aFRR prices (347, 348) to `DATASETS` in `tools/ingest/fingrid.py`, with the rules in `series_catalog`. |
| Open-Meteo weather | Works now | `uv run python -m tools.cli ingest openmeteo --start <last> --end <now>` with the same `--models` / `--group` as in "Reproduce the submission" (root `README.md`) |
| UMM outage messages | Works now | `uv run python -m tools.ingest.umm --start <last> --end <now>` |
| Fingrid day-ahead forecasts (165 consumption, 246 wind, 247 solar) | To write | The Fingrid API keeps only the latest version, so never backfill. Once a day after 13:00 Helsinki, fetch tomorrow's values and insert them with `first_usable_origin_utc` = the next full hour after the fetch. That matches the D-1 13:00 version the models were trained on. Start a day before going live. |
| ENTSO-E series (`ee_` / `se1_` / `se3_` load forecasts and imbalance prices, EE–FI capacity) | To write | With the token: same `series_id`s, the package's availability rules (`series_catalog`). |
| Spot price | To write | The source from step 1 under a new `series_id` (AGENTS.md rule 3). The feature code reads `fi_spot_price` (`backend/imbalance/features.py`); for forecast times after 2 Nov, read the new series there instead. |
| Calendar (`cal_*`) | To write | Generate rows past 2 Nov with the package's definitions (always usable). |

## 3. Hourly forecast job (to write: a `live` command in `tools/cli.py`)

At about 5 past each hour, for the new forecast time (the full hour just passed):

1. Run the ingests in step 2.
2. Build the feature rows for that forecast time (feature sets v4, v4m, v9d, v9md).
3. Forecast with every trained member of the submission and combine them exactly as the submission
   does. The recipe is "Reproduce the submission" in the root `README.md`; follow it, since it is the
   source of truth. Today (`ens_finald`) it is: the bagged mixture members (`mix_v4b`, `mix_v4mb`,
   `mix_v9db`, `mix_v9mdb`, each `s0`/`s1`/`s2w`/`s3a`; `infer()` in
   `tools/training/mixture_pipeline.py`), the lead-time split per member (v9d for steps 1–8,
   `tools/eval/step_split.py`), the 8-member average (`tools/eval/ensemble.py`), the band widths
   (`tools/eval/band_width.py`), and the spike hedge with the previous chain `ens_mixgd_spk_bw`
   (`tools/eval/spike_hedge.py`). These run on whole exported CSVs today; call them on one forecast
   time instead. Use the fitted values as they are: never refit them on live data.
4. Write the result with `imbalance.forecasts.write()` under one model name, e.g. `ens_finald_live`
   (`tools/eval/import_submission.py` does the same for a whole CSV).
5. Restart the API (step 4): it reads forecasts once at start-up. Or add a reload.

Run it from Windows Task Scheduler or cron. Log progress, never values (the spot price must not reach
logs).

## 4. API settings

Start without `--reload`, in real mode, with the live model:

```powershell
$env:IMBALANCE_DATA_MODE="real"
$env:IMBALANCE_MODEL_TEST="ens_finald_live"        # the model name the hourly job writes (step 3)
.venv\Scripts\python.exe -m uvicorn backend.api.main:app --port 8000
```

| Variable | Live value | Why |
|---|---|---|
| `IMBALANCE_DATA_MODE` | `real` | `mock` (default) serves invented data |
| `IMBALANCE_MODEL_TEST` | the live model name | The test period has no end, so its newest forecast is "now" |
| `IMBALANCE_MODEL_VAL` | the `-val` model, or leave it | Only for browsing validation dates |
| `IMBALANCE_CHALLENGER_TEST` | a second model on different inputs, or `none` | Feeds the conflicting-signals alert; it needs its own live forecasts, so `none` until the job writes them |
| `IMBALANCE_NOTES_TEST` | `alerts`, or `none` | The event classifiers behind `/api/notes`; they need the live feature rows too |
| `IMBALANCE_CORS_ORIGINS` | empty, unless a browser app on another address calls the API | See below |
| `--host` (uvicorn) | leave the default `127.0.0.1` | `0.0.0.0` exposes it to the network; not with the spot price in it (step 6) |

Full reference of the settings: `backend/api/settings.py`. Endpoints, what each returns, and how to
call the API from scripts, notebooks or other apps instead of the dashboard (curl, PowerShell,
Python, network access, CORS): **`backend/api/README.md`**, sections "The endpoints one by one" and
"Calling the API without the dashboard".

## 5. Dashboard settings

```powershell
cd frontend
npm install
npm run build                       # contrast check, type check, production build
$env:API_ORIGIN="http://127.0.0.1:8000"     # where the API runs; this is the default
npm start                           # http://localhost:3000
```

The dashboard calls the API through its own proxy (`frontend/next.config.ts`), so it needs no CORS.
Leave `NEXT_PUBLIC_API_FAULTS` unset in a live build. Details: `frontend/README.md`.

## 6. Where it may run

- **Nord Pool spot (the hackathon file):** our dashboard on our own machines only. Never a hosted
  service, cloud database, log or chat (AGENTS.md rule 6), and deleted after the event. While the
  spot price comes from that file, the API stays on `127.0.0.1`.
- **A licensed live spot source (step 1):** its own terms decide whether the API and dashboard may be
  hosted. Check them, list them in `docs/SOURCES_AND_LICENCES.md`, and ask the team before hosting.
- **Open-Meteo free tier:** non-commercial use only.
- **Fingrid, ENTSO-E:** CC BY 4.0; credit them on the dashboard and in the docs.
- **Git:** live data, forecasts and scores never go into git (AGENTS.md rule 0).

## 7. Before relying on it

- `uv run python -m tools.cli leakage`: features rebuilt from data limited to each forecast time
  must be identical.
- `tools/eval/fingrid_delay.py`: Fingrid's real-time publication delays still fit the 15 min margin
  in `tools/ingest/fingrid.py`.
- Watch a week of live forecasts against what happened (`/api/hindsight`, `/api/performance`) and
  compare with the validation scores. This is a diagnostic only: live results never retrain, tune
  or recalibrate the submitted models.

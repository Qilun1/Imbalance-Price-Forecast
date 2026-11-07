# api

FastAPI service behind the dashboard. It runs on invented mock data by default, so it needs no
licensed files.

**Deploying it on live data:** `docs/LIVE_DEPLOYMENT.md` is the plan (data, hourly job, the settings
below with their live values, where it may run). This file is the reference: settings, endpoints,
and calling the API from other programs.

On Windows, `start-dashboard.cmd` in the repo root starts this API and the dashboard together. By hand:

```powershell
uv run python -m uvicorn backend.api.main:app --reload --port 8000     # mock data, built on first start
$env:IMBALANCE_DATA_MODE="real"                                        # then start again for the pipeline's forecasts
uv run python -m backend.api.mock                                      # rebuild the mock data
```

If `uv` is not recognised in a terminal, restart the editor or use `.venv\Scripts\python.exe` in place of
`uv run python`.

## Settings

Environment variables, read at start-up (restart the API after changing one). Source:
`settings.py`.

| Variable | Default | Does |
|---|---|---|
| `IMBALANCE_DATA_MODE` | `mock` | `mock`: invented data, needs nothing else. `real`: the store and the forecasts in `backend/infer_data/` |
| `IMBALANCE_MODEL_VAL` | `lgbm_v1-val` | Model answering for validation dates. Use a `-val` model: the final one is in-sample there |
| `IMBALANCE_MODEL_TEST` | `lgbm_v1` | Model answering from the test period on, including any later (live) forecasts |
| `IMBALANCE_CHALLENGER_VAL` / `_TEST` | `lgbm_v2-val` / `lgbm_v2` | Second model on different inputs, for the conflicting-signals alert. `none` turns it off |
| `IMBALANCE_NOTES_VAL` / `_TEST` | `alerts-val` / `alerts` | Event classifiers behind `/api/notes`. `none` turns them off |
| `IMBALANCE_CORS_ORIGINS` | empty | Browser origins allowed to call the API directly, comma-separated. Empty: no CORS headers |

Uvicorn options: `--port` (8000; the dashboard expects it unless `API_ORIGIN` says otherwise),
`--host` (`127.0.0.1`, this machine only), `--reload` (development only). The API reads forecasts
once at start-up, so restart it after new forecasts are written.

Interactive docs: <http://127.0.0.1:8000/docs> (every endpoint with a "Try it out" button; the
machine-readable schema is at <http://127.0.0.1:8000/openapi.json>). Real mode needs the steps in
`tools/README.md` first.

| Endpoint | Returns |
|---|---|
| `GET /api/meta` | Data mode, models and the range of viewing times |
| `GET /api/forecast?as_of=` | The 40 steps with spot, drivers and data freshness |
| `GET /api/changes?as_of=` | How the forecast moved since the previous update |
| `GET /api/actuals?from=&to=&as_of=` | Realised price, direction and spot usable at `as_of` |
| `GET /api/alerts?as_of=` | The situations worth checking, with reasons |
| `GET /api/alerts/history?from=&to=&as_of=` | Situations per hour, and each past situation once with its outcome |
| `GET /api/performance?from=&to=&as_of=` | Official validation scores plus a chosen window |
| `GET /api/notes?persona=trader\|operator&as_of=&thresholds=&include_low_skill=` | Learned event probabilities for the next 0–2, 2–5 and 5–10 h, with interval, lift vs normal, confidence, drivers and what to check |
| `GET /api/hindsight?from=&to=&lead_hours=&as_of=` | Each quarter-hour as forecast `lead_hours` ahead, against what happened |
| `GET /api/umm?as_of=&hours=&min_mw=` | Nord Pool outage messages (UMM) for Finland in the next hours, with links |

Timestamps are UTC and must carry a time zone, for example `2026-10-20T08:00:00Z`. `as_of` is the
viewing time; if it is left out, the API uses the newest forecast.

## The endpoints one by one

All endpoints are read-only `GET`s that return JSON. Every response repeats `as_of_utc`, the viewing
time it answers for. Nothing in a response was unknown at that time (see "Rules built into the API").
Prices are EUR/MWh and probabilities are 0–1.

**`/api/meta`**: start here. Says whether the API serves `mock` or `real` data, which model answers
for each period (validation, test), the first and last forecast time you can ask for, the horizon
(40 steps of 15 min) and the spike margin (50 EUR/MWh). Use it to find valid `as_of` values.

**`/api/forecast`**: the main product. The forecast made at the newest hour at or before `as_of`:
40 quarter-hours from the forecast time. Each step has `p10`/`p50`/`p90` (price band, `p50` is the
point forecast), `p_up`/`p_down`/`p_none` (direction of mFRR regulation), `p_spike_high`/`p_spike_low`
(price above spot + 50 or below spot - 50), `spot` once it has been published, and `drivers` (inputs
that pushed this forecast most). `data_age_minutes` says how old the newest input was.

**`/api/changes`**: the same 40 quarter-hours compared with the forecast made one hour earlier,
`p50_change` per quarter-hour and `largest_p50_change`. Answers "what moved since last hour". Empty
for the first forecast, and across a model switch.

**`/api/actuals`**: what happened: realised imbalance price, regulation direction and spot per
quarter-hour, in `[from, to)` (default: the 24 h before `as_of`). Only values already published at
`as_of` are returned, so recent quarter-hours are missing until Fingrid publishes them.

**`/api/alerts`**: the situations worth a look right now (for example a likely spike, a wide band,
two independent models disagreeing), each with `severity` (`watch` or `review`), a time window, a
plain-language `message`, what to `check`, and the numbers behind it (`evidence`). Alerts suggest
what to check, never what to do.

**`/api/alerts/history`**: the alerts over time. `hours` counts alerts per forecast hour (for a
timeline), and `situations` lists each past situation once, with its `outcome` (`happened`,
`did_not_happen`, `pending`) judged only on prices known at `as_of`.

**`/api/notes`**: the event classifiers: the probability of specific events (`spike_high`,
`up_episode`, `direction_flip`, `deep_negative` and others in `backend/imbalance/events.py`) in the
next 0–2, 2–5 and 5–10 h, with an uncertainty interval, the normal rate, `lift` (how many times more
likely than normal), `confidence`, and whether it `fires` at the threshold. `persona=trader` or
`operator` (a CHP plant with electric boilers) picks the relevant events.
`thresholds=spike_high:0.3,up_episode:0.5` overrides the default thresholds; it changes only
`fires`. Events with little validation skill are hidden unless `include_low_skill=true`.

**`/api/performance`**: how good the model is. `official` is the organiser's `score.py` result on
the validation period (the number to quote), against the organiser's baseline. `diagnostic` is the
same metrics over `[from, to)` (default: the 7 days before `as_of`), labelled as a diagnostic.

**`/api/hindsight`**: forecast against reality: each quarter-hour in `[from, to)` as it was forecast
`lead_hours` (1–10) ahead, with the actual price and spot. Good for "how did the 3 h-ahead forecast
do last week" charts.

**`/api/umm`**: Nord Pool urgent market messages (unplanned and planned outages of Finnish
production and interconnectors) active in the next `hours` (default 10), at least `min_mw` MW
(default 50), each with a link to the message. `available: false` means UMM data was not ingested
(always in mock mode).

Errors: a time outside the data gives `404` with the valid range in `detail`. A timestamp without a
time zone, or a parameter out of range, gives `422`.

## Calling the API without the dashboard

The API is plain HTTP and JSON, so any program can call it: scripts, notebooks, Excel Power Query,
another web app. The dashboard is just one client. Start the API (see the top of this file), then:

```powershell
curl.exe "http://127.0.0.1:8000/api/meta"                                       # Windows: curl.exe, not curl
curl.exe "http://127.0.0.1:8000/api/forecast?as_of=2026-10-20T08:00:00Z"
Invoke-RestMethod "http://127.0.0.1:8000/api/alerts" | ConvertTo-Json -Depth 6   # PowerShell objects
```

```python
import requests, pandas as pd
r = requests.get("http://127.0.0.1:8000/api/forecast", params={"as_of": "2026-10-20T08:00:00Z"})
r.raise_for_status()
steps = pd.DataFrame(r.json()["steps"])          # one row per quarter-hour: p10, p50, p90, p_up, ...
```

Three switches, depending on where the caller is:

| Caller | What to do |
|---|---|
| A script, notebook or tool on the same machine | Nothing. Call `http://127.0.0.1:8000/api/...`. |
| Another machine on the same network | Start the API with `--host 0.0.0.0` (it listens only on this machine by default) and call `http://<this machine's IP>:8000/api/...`. Windows may ask to allow Python through the firewall. **Mock mode only** (licence, below). |
| A web page served from another address (another front end, a different port) | Browsers block cross-origin calls unless the API allows them: `$env:IMBALANCE_CORS_ORIGINS="http://localhost:5173"` (comma-separated, exact origins) before starting the API. Off by default. Not needed for the dashboard, which calls through its own proxy (`API_ORIGIN` in `frontend/next.config.ts`). |

**Licence, before you point anything at real mode:** in real mode `/forecast`, `/actuals` and
`/hindsight` return the Nord Pool spot price in their `spot` fields. That data may reach our
dashboard and nowhere else (AGENTS.md rule 6): a script must not save, log, print into shared output
or forward it, and the API must not be served from a hosted service or to other machines. Build and
test integrations against mock mode, which has invented prices and no licence limits. Real-mode
integration needs a licensed spot source first (`docs/LIVE_DEPLOYMENT.md`, steps 1 and 6).

## Rules built into the API

- **Availability:** price, direction and spot pass through the organiser's `rows_available_at()`, and
  forecasts are limited to origins at or before `as_of`. Spot for tomorrow appears at 14:00 Helsinki time.
- **Licence:** only `DISPLAY_SERIES` in `repository.py` is ever loaded. Spot may reach the dashboard and
  nowhere else (AGENTS.md rule 6): never log it, export it or serve this API from a hosted service. The
  dashboard derives spot + 50 and spot - 50 from `spike_margin_eur_mwh` in `/api/meta`.
- **Models:** validation dates use `lgbm_v1-val`, which is out of sample. `lgbm_v1` is in-sample there.
- **Scores:** `official` is the organiser's `score.py` output and the number to quote. `diagnostic`
  calls their `compute_metrics()` over a window and is labelled as a diagnostic. Test-period diagnostics
  are for display only (AGENTS.md rule 4).
- **Alerts:** they suggest what to check, never what to do. Thresholds in `alerts.py` were set on
  validation forecasts only; never tune them on test data.
- **Outcomes:** `outcomes.py` judges a past situation on prices usable at `as_of`. It is a diagnostic for
  display, so test-period outcomes must not guide model choice, tuning or thresholds (AGENTS.md rule 4).
- **Conflicting signals:** independent sources must disagree, not two outputs of one model. The main
  forecast is compared with a second model on different input data from the same origin
  (`lgbm_v2`, which adds ECMWF weather; `IMBALANCE_CHALLENGER_VAL` / `_TEST`, `none` turns it off).

- **Notes:** `/notes` serves the event classifiers (docs/plans/event_notes.md): `alerts-val` for
  validation dates (out of sample) and `alerts` for test dates (`IMBALANCE_NOTES_VAL` / `_TEST`,
  `none` turns them off). The operator view is a CHP plant with electric boilers. A note fires at the
  bundle's default threshold or at a user-set one (`thresholds=spike_high:0.3,...`); a threshold
  changes only `fires`, never the probabilities. Events with validation Brier skill below the
  bundle's bar are hidden unless `include_low_skill=true`. Notes say what to check, never what to do.

Mock data lives in `backend/infer_data/mock_forecasts.duckdb` (gitignored). `mock.py` is invented from
a seed, reads none of the organiser's files, and scripts one of each situation; see `SCENARIOS` there.
Its spot price is invented too. An older mock file without spot is rebuilt automatically on start-up.

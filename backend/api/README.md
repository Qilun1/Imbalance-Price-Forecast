# api

FastAPI service behind the dashboard. It runs on invented mock data by default, so it needs no
licensed files.

On Windows, `start-dashboard.cmd` in the repo root starts this API and the dashboard together. By hand:

```powershell
uv run python -m uvicorn backend.api.main:app --reload --port 8000     # mock data, built on first start
$env:IMBALANCE_DATA_MODE="real"                                        # then start again for the pipeline's forecasts
uv run python -m backend.api.mock                                      # rebuild the mock data
```

If `uv` is not recognised in a terminal, restart the editor or use `.venv\Scripts\python.exe` in place of
`uv run python`.

Interactive docs: <http://127.0.0.1:8000/docs>. Real mode needs the steps in `tools/README.md` first.

| Endpoint | Returns |
|---|---|
| `GET /api/meta` | Data mode, models and the range of viewing times |
| `GET /api/forecast?as_of=` | The 40 steps with spot, drivers and data freshness |
| `GET /api/changes?as_of=` | How the forecast moved since the previous update |
| `GET /api/actuals?from=&to=&as_of=` | Realised price, direction and spot usable at `as_of` |
| `GET /api/alerts?as_of=` | The situations worth checking, with reasons |
| `GET /api/alerts/history?from=&to=&as_of=` | Situations per hour, and each past situation once with its outcome |
| `GET /api/performance?from=&to=&as_of=` | Official validation scores plus a chosen window |
| `GET /api/hindsight?from=&to=&lead_hours=&as_of=` | Each quarter-hour as forecast `lead_hours` ahead, against what happened |

Timestamps are UTC and must carry a time zone, for example `2026-10-20T08:00:00Z`. `as_of` is the
viewing time; if it is left out, the API uses the newest forecast.

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

Mock data lives in `backend/infer_data/mock_forecasts.duckdb` (gitignored). `mock.py` is invented from
a seed, reads none of the organiser's files, and scripts one of each situation; see `SCENARIOS` there.
Its spot price is invented too. An older mock file without spot is rebuilt automatically on start-up.

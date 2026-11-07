# api

FastAPI service behind the dashboard. It runs on invented mock data by default, so it needs no
licensed files.

```powershell
uv run uvicorn backend.api.main:app --reload --port 8000     # mock data, built on first start
$env:IMBALANCE_DATA_MODE="real"                              # then start again for the pipeline's forecasts
uv run python -m backend.api.mock                            # rebuild the mock data
```

Interactive docs: <http://127.0.0.1:8000/docs>. Real mode needs the steps in `tools/README.md` first.

| Endpoint | Returns |
|---|---|
| `GET /api/meta` | Data mode, models and the range of viewing times |
| `GET /api/forecast?as_of=` | The 40 steps with drivers and data freshness |
| `GET /api/changes?as_of=` | How the forecast moved since the previous update |
| `GET /api/actuals?from=&to=&as_of=` | Realised price and direction usable at `as_of` |
| `GET /api/alerts?as_of=` | The situations worth checking, with reasons |
| `GET /api/performance?from=&to=&as_of=` | Official validation scores plus a chosen window |

Timestamps are UTC and must carry a time zone, for example `2026-10-20T08:00:00Z`. `as_of` is the
viewing time; if it is left out, the API uses the newest forecast.

## Rules built into the API

- **Availability:** actuals pass through the organiser's `rows_available_at()`, and forecasts are
  limited to origins at or before `as_of`.
- **Licence:** only `DISPLAY_SERIES` in `repository.py` is ever loaded, so the spot price never enters
  the process. Do not add a spot + 50 threshold either, because it gives the spot price away.
- **Models:** validation dates use `lgbm_v1-val`, which is out of sample. `lgbm_v1` is in-sample there.
- **Scores:** `official` is the organiser's `score.py` output and the number to quote. `diagnostic`
  calls their `compute_metrics()` over a window, leaves out spike scores (they need spot), and is
  labelled as a diagnostic. Test-period diagnostics are for display only (AGENTS.md rule 4).
- **Alerts:** they suggest what to check, never what to do. Thresholds in `alerts.py` were set on
  validation forecasts only; never tune them on test data.

Mock data lives in `backend/infer_data/mock_forecasts.duckdb` (gitignored). `mock.py` is invented from
a seed, reads none of the organiser's files, and scripts one of each situation; see `SCENARIOS` there.

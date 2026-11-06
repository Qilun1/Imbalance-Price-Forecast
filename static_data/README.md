# static_data

Source data for the pipeline. **Everything here is gitignored**: the Nord Pool spot price is licensed
to Turku Energia for the hackathon only (no sharing, no public repos, delete after the event).

| Path | Content |
|---|---|
| `raw/starter/` | Starter package data files, copied unchanged |
| `raw/<source>/` | Untouched pulls from other sources (Fingrid, Open-Meteo, ...) |
| `static.duckdb` | Normalised store: `observations`, `forecast_runs`, `series_catalog` |
| `processed/` | Feature tables, named by feature-set version |

Every row in the store carries `first_usable_origin_utc`, the first forecast origin at which it may
be used.

# Data sources, services and components

Team WeatherSensAI, Since AI 2026, Turku Energia challenge. Checked on 7 Nov 2026 against each
provider's terms (links below). The submitted forecast is `ens_mixg` with a spike shift and band widths: the mean of two
lead-time-split structural mixture models, ECMWF (`mix_v9b` for steps 1-8, `mix_v4b` after) and MET
Nordic (`mix_v9mb` for steps 1-8, `mix_v4mb` after), with one logit shift per spike class and one band
width per lead block and direction certainty, fitted on validation.

Every time-stamped input reaches the models only through the store's availability-masked reader
(`backend/imbalance/`). Each row is usable from its `first_usable_origin_utc`. For sources we added,
that value comes from the conservative publication delay in the "Availability rule" column, rounded
up to the next full hour (AGENTS.md rule 4).

## 1. Data used by the submitted model

| Source | What we use | Licence | Availability rule | Used by |
|---|---|---|---|---|
| Organiser package: Fingrid Open Data | Imbalance price (319), mFRR prices (244, 106), activated mFRR (375, 376), mFRR direction (369), aFRR prices (347, 348), consumption (124), production (74), day-ahead consumption / wind / solar forecasts (165, 246, 247), cross-border flows (61, 57, 60, 55) | CC BY 4.0 | Organiser's `first_usable_origin_utc`, unchanged | all members |
| Organiser package: ENTSO-E Transparency Platform | SE1 / SE3 / EE imbalance prices (17.1.g), SE1 / SE3 / EE day-ahead load forecasts (6.1.b), FI-EE day-ahead capacity (11.1) | CC BY 4.0 (free re-use list); organiser converted to UTC and 15 min | Organiser's `first_usable_origin_utc`, unchanged | all members |
| Organiser package: Nord Pool | Finnish day-ahead spot price | Licensed to Turku Energia for the hackathon only; see section 4 | Organiser's `first_usable_origin_utc`, unchanged | both members (target is defined as imbalance minus spot) |
| Fingrid Open Data API (we added) | Wind power generation, 15 min (dataset 75) | CC BY 4.0 | 60 min after the end of the quarter-hour | both members (observed wind error vs dataset 246) |
| Fingrid Open Data API, real-time grid state (we added) | Surplus/deficit (198), frequency (177), net import (194), electric boilers (371), battery discharging / charging (398 / 399), real-time wind (181) and consumption (193); 1-3 min values averaged to complete quarter-hours | CC BY 4.0 | 15 min after the end of the quarter-hour (measured publication delay 1.2-4.1 min, `tools/eval/fingrid_delay.py`, 7 Nov 2026) | `mix_v9b`, `mix_v9mb` (steps 1-8 only) |
| ECMWF IFS 9 km via the Open-Meteo Single Runs API | 100 m wind speed, 2 m temperature, every 00/06/12/18 UTC run, at about 10 wind-site points | ECMWF data: CC BY 4.0. Open-Meteo: CC BY 4.0 data; free API for non-commercial use only | Run init + 8 h (measured 6 h 48 min + 10 min Open-Meteo advice, 7 Nov 2026) | `mix_v4b` |
| MET Nordic (MET Norway, MEPS 2.5 km post-processed) via the Open-Meteo Single Runs API | 100 m wind speed, 2 m temperature, 00/06/12/18 UTC runs | MET Norway data: CC BY 4.0 / NLOD 2.0. Open-Meteo terms as above | Run init + 2 h (measured 34 min + 10 min advice, 7 Nov 2026) | `mix_v4mb` |
| OpenStreetMap via the Overpass API | Wind turbine positions and rated outputs in Finland, clustered to about 10 weighted points (`tools/ingest/windsites.py`) | ODbL 1.0, © OpenStreetMap contributors | Static metadata (snapshot 6 Nov 2026) | both members (NWP sampling points and weights) |
| Renewables Finland (Suomen Uusiutuvat ry), wind statistics 30 Jun 2026 | Total installed wind capacity (9,535 MW) to scale the OSM capacities; regional split for the fallback site list | No licence stated on the publication; used as cited factual figures. **Reuse terms to be confirmed** | Static | all members |
| Statistics Finland | Approximate regional populations (about 2024, rounded) to weight temperature by heating demand (`tools/ingest/popsites.py`) | CC BY 4.0 | Static | `mix_v4mb` |
| Calendar | Hour, weekday, holidays | Not applicable | Always usable (organiser rule) | all members |

Validation actuals (`actuals_validation.csv`, organiser) are used for scoring and to fit the spike
shift. They are never used for the test period.

## 2. Data ingested but not used by the submitted model

| Source | What | Licence | Where it is used |
|---|---|---|---|
| Fingrid Open Data API | Nuclear (188) and hydro (191) real-time production, 3 min averaged to 15 min, 60 min lag | CC BY 4.0 | Ingested only; no feature set in this repo uses them |
| Fingrid Open Data API, history since 20 Mar 2025 (`tools/ingest/fingrid_history.py`) | 319, 244, 106, 375, 376, 369, 347-350, 342, 75 | CC BY 4.0 | Imbalance price rebuild check (`tools/eval/rebuild_price.py`) and the long-history direction head (sets v5 / v5m, not submitted). Pre-June imbalance price is never a training target |
| Nord Pool REMIT UMM API (`tools/ingest/umm.py`) | Urgent market messages for Finland: production, consumption and transmission unavailability, every message version with its publication time | Public REMIT inside information; Nord Pool API terms apply (free API). **Reuse terms to be confirmed** | Feature sets v8 / v8m (not submitted: no gain) and dashboard alerts with a link to the message. Each version usable from the first full hour after publication + 5 min |
| Statistics Finland, Energy prices (PxWeb tables 13p7, 12gb; `backend/fuel/`) | Reference fuel prices for power and heat production (forest chips, milled peat, natural gas), monthly / quarterly, EUR/MWh | CC BY 4.0 | Operator fuel-cost panel only (not yet in the dashboard); never a model input |
| OilPriceAPI (optional, `OILPRICEAPI_KEY`; else a manual value) | EU ETS allowance (EUA) spot price | Commercial API, free tier; **reuse terms to be confirmed** | Operator fuel-cost panel only; never a model input |
| Fingrid package series extended past 2 Nov 2026 (319, 244, 106, 375, 376, 369, 124, 74) | Live dashboard only | CC BY 4.0 | Dashboard; never the backtest |

Fingrid forecast datasets (165, 166, 241, 242, 245-248) are never fetched from the API: it keeps only
the latest version of a revised forecast, which the rules forbid. Their vintaged versions come from the
organiser package.

## 3. Software components

Versions are the ones pinned in `uv.lock` and `frontend/package-lock.json`.

| Component | Version | Licence | Role |
|---|---|---|---|
| Python | 3.11-3.13 | PSF-2.0 | Runtime |
| uv | 0.13 | Apache-2.0 / MIT | Environment and runner |
| LightGBM | 4.7.0 | MIT | Gradient-boosted models |
| pandas | 3.1.1 | BSD-3-Clause | Data handling |
| NumPy | 2.5.4 | BSD-3-Clause (bundled parts 0BSD, MIT, Zlib, CC0-1.0) | Numerics |
| PyArrow | 26.0.1 | Apache-2.0 | Parquet |
| DuckDB | 2.0.0 | MIT | Local data store |
| scikit-learn | 1.9.1 | BSD-3-Clause | Calibration diagnostics; event classifiers (logistic regression, isotonic regression for Venn–Abers calibration) |
| SciPy | 1.18.1 | BSD-3-Clause | Dependency of scikit-learn |
| requests | 2.34.2 | Apache-2.0 | HTTP ingest |
| PyYAML | 6.0.3 | MIT | Model configs |
| tzdata | 2026.6 | Apache-2.0 | Time zones |
| FastAPI | 0.162.0 | MIT | Dashboard API |
| Starlette | 1.10.0 | BSD-3-Clause | Dependency of FastAPI |
| Pydantic | 2.14.3 | MIT | API schemas |
| Uvicorn | 0.54.0 | BSD-3-Clause | API server |
| Matplotlib | 3.11.2 | Matplotlib licence (PSF-based) | Diagnostic plots |
| httpx | 0.28.1 | BSD-3-Clause | API tests (dev) |
| pytest | 9.2.0 | MIT | Tests (dev) |
| React, React DOM | 19.3.1 | MIT | Dashboard UI |
| Vite | 8.3.6 | MIT | Frontend build |
| @vitejs/plugin-react | 6.2.1 | MIT | Frontend build |
| TypeScript | 5.9.3 | Apache-2.0 | Frontend language |
| openapi-typescript | 7.13.0 | MIT | Typed API client generation |
| @types/react, @types/react-dom | 19.3.0 | MIT | Type definitions |
| Organiser starter package (`score.py`, `validate_submission.py`, `build_dataset.py`, baseline) | 1.0 / scorer 0.1.1 | Provided by Turku Energia; used unchanged, read-only | Scoring, validation, baseline |

Services: Fingrid Open Data API (free registration, API key), Open-Meteo Single Runs API (free
non-commercial tier, within its 10,000 calls a day limit) and the Overpass API (public instance,
`overpass-api.de`). AI coding assistants (Claude) were used to write and review code; all outputs were
checked with the organiser's validator, scorer and our leakage check.

## 4. Obligations and open points

- **Nord Pool spot data.** Licensed to Turku Energia and shared only for the hackathon. It is never
  committed, printed, uploaded or sent anywhere. Our code may be public; the data may not. It will be
  deleted after the event. Team exception (7 Nov 2026): the dashboard, its screenshots and the demo
  video may show the spot price and the spot +/- 50 EUR/MWh thresholds (AGENTS.md rule 6).
- **Open-Meteo free tier is non-commercial only.** The hackathon backtest qualifies. Any live or
  commercial use of the dashboard (for example within our company) needs an Open-Meteo subscription
  or a self-hosted instance. The ECMWF and MET Norway data themselves allow commercial use with
  attribution.
- **OpenStreetMap.** The clustered wind-site file is a Derivative Database. It stays local
  (`static_data/`, gitignored) and is not published. The model and its forecasts are Produced Works:
  wherever they are shown publicly (dashboard, slides, video), we credit "© OpenStreetMap
  contributors, ODbL" with a link to openstreetmap.org/copyright.
- **Renewables Finland.** No reuse licence is stated. We use two published capacity figures with
  citation. To confirm with the association before any use beyond the hackathon.
- **Static metadata snapshot.** The OSM turbine list (6 Nov 2026) and the capacity total (30 Jun
  2026) are fixed for the whole backtest. Turbines commissioned after June are therefore included at
  June origins. This affects only the NWP sampling weights, not any time-stamped value. It is a known
  limitation, not an availability-rule breach of a time-stamped series.

## 5. Attribution text

Use this wherever the forecasts, dashboard or slides are shown:

> Source: Fingrid / data.fingrid.fi, licence CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
> ENTSO-E Transparency Platform, licence CC BY 4.0, via the organiser's package (converted to UTC and
> 15 min). Weather: ECMWF IFS forecast data, © ECMWF, licensed under CC BY 4.0, and MET Nordic data
> from MET Norway (CC BY 4.0), both accessed through Open-Meteo.com (CC BY 4.0); processed into wind
> and temperature indices. Wind turbine locations © OpenStreetMap contributors, ODbL
> (https://www.openstreetmap.org/copyright). Population weights: Statistics Finland (CC BY 4.0).
> Wind capacity: Renewables Finland (Suomen Uusiutuvat ry), wind statistics 30 Jun 2026. Spot price:
> Nord Pool, licensed to Turku Energia for the hackathon (not redistributed).

## Licence and terms pages

- Fingrid: https://data.fingrid.fi/en/about
- ENTSO-E and Nord Pool terms: organiser `README.md`, section 9
- Open-Meteo: https://open-meteo.com/en/terms
- ECMWF open data: https://www.ecmwf.int/en/forecasts/datasets/open-data
- MET Norway: https://www.met.no/en/free-meteorological-data/Licensing-and-crediting
- OpenStreetMap: https://www.openstreetmap.org/copyright and https://osmfoundation.org/wiki/Attribution
- Statistics Finland: https://stat.fi/en/about-us/get-to-know-statistics-finland/legislation/terms-of-use
- Renewables Finland source: https://suomenuusiutuvat.fi/media/tuulivoima_vuositilastot-6_2026.pdf

# backend/fuel: fuel context for the operator panel

Reference fuel and carbon prices plus simple marginal costs for Naantali (NA4 CHP and the electric boilers). Display only; this is not a model input.

## Run

```
uv run python -m backend.fuel --spot 45      # prints the panel JSON
uv run python -m backend.fuel --refresh      # force re-fetch
uv run pytest backend/tests/test_fuel.py     # offline tests
```

Not wired into the API or dashboard yet. When we decide to, add `fuel` to the router loop in
`backend/api/main.py` (`from backend.fuel import api as fuel`), which gives `GET /api/fuel/snapshot?spot=45`.

## Data

| Fuel | Source | Notes |
|---|---|---|
| Forest chips, milled peat, natural gas | Statistics Finland 13p7, monthly, EUR/MWh fuel, tax-free | About 4-5 months behind (June 2026 is the latest in Nov 2026) |
| Chips, peat (fallback) | Statistics Finland 12gb, quarterly | Peat excluding excise |
| Coal | none free (13p7 suppressed, 12he stops 2022M12) | `MANUAL_FUEL_PRICE_EUR_MWH["coal"]` |
| SRF, heavy fuel oil | none public | manual |
| EUA | OilPriceAPI if `OILPRICEAPI_KEY` is set, else `EUA_MANUAL_EUR_T` | |

Statistics Finland data: open, CC BY 4.0, no key. Results are cached for 24 h in `static_data/cache/fuel/fuel_prices.json` (git-ignored). If a fetch fails, the stale cache is served and `errors` says so.

## Outputs (`build_snapshot`)

- `fuels`: latest price, period, source, CO2 factor, price incl. CO2.
- `history`: monthly/quarterly series for a sparkline in the expanded view.
- `heat`: heat-only chip boiler vs e-boiler cost at the given spot, and the spot below which the e-boiler is cheaper.
- `chp.by_fuel`: NA4 power cost per fuel, gross (fuel+CO2 / eta_el) and after heat credit:
  `C_el = (c_fuel - eta_heat * h_alt) / eta_el`, with h_alt = cheapest alternative heat. Compare this with the forecast up-regulation price.
- `assumptions`: efficiencies and adders, all placeholders (`config.py`) until TSE confirms.

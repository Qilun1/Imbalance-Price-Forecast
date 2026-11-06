# Reference data (committed, no licence restrictions)

## wind_sites_v0.csv

Representative wind sites used to sample NWP forecasts and build a capacity-weighted national wind
proxy. Version 0 is coarse:

- Regional capacities: Renewables Finland (Suomen Uusiutuvat ry), wind statistics 30 Jun 2026,
  total 9,535 MW (https://suomenuusiutuvat.fi/media/tuulivoima_vuositilastot-6_2026.pdf). The region
  labels of the published chart were matched to its pie-chart shares; "Other" is the remainder.
- Each region's capacity is split evenly over a few municipalities with large wind clusters.
  Coordinates are approximate municipality centres (about +-10 km). Good enough for a 9 km grid and a
  national aggregate; not for farm-level work.

Replace with `wind_sites_osm.csv` by running `uv run python -m tools.cli ingest windsites` (OpenStreetMap
turbine positions via Overpass, clustered into sites; data (c) OpenStreetMap contributors, ODbL).

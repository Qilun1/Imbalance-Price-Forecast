"""Measure how fast Fingrid publishes measured data (diagnostic for a less conservative availability
rule). For each dataset, poll the latest value and record now - end of its quarter-hour / interval.

We currently use 60 min after the end of the quarter-hour for our own measured series (75, 188, 191).
A shorter, documented delay would give fresher system state at the origin (first 2 h of the
forecast). Organiser rows keep their own first_usable_origin_utc (never changed).

    uv run python -m tools.eval.fingrid_delay --rounds 6 --every 300     # 6 polls, 5 min apart
Writes static_data/work/diagnostics/fingrid_delay.csv.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import pandas as pd

from imbalance.paths import REPO_ROOT
from tools.ingest.fingrid import api_key
from tools.ingest.http import Client

DATASETS = {
    75: "wind generation, 15 min",
    181: "wind generation, real time 3 min",
    188: "nuclear, real time 3 min",
    191: "hydro, real time 3 min",
    192: "production, real time 3 min",
    193: "consumption, real time 3 min",
    177: "frequency, real time",
    124: "consumption, 15 min",
    74: "production, 15 min",
    319: "imbalance price",
    244: "mFRR up price",
    375: "mFRR up activated",
    369: "mFRR direction",
}
URL = "https://data.fingrid.fi/api/datasets/{id}/data/latest"
OUT = REPO_ROOT / "static_data" / "work" / "diagnostics" / "fingrid_delay.csv"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--every", type=int, default=300, help="seconds between rounds")
    a = ap.parse_args()
    c = Client(min_interval_s=2.1, headers={"x-api-key": api_key()})
    rows = []
    for r in range(a.rounds):
        for ds, name in DATASETS.items():
            now = datetime.now(timezone.utc)
            try:
                d = c.get_json(URL.format(id=ds), params={"format": "json"})
                d = d.get("data", d) if isinstance(d, dict) else d
                d = d[0] if isinstance(d, list) else d
                end = pd.Timestamp(d.get("endTime") or d.get("end_time"))
                lag = (pd.Timestamp(now) - end).total_seconds() / 60
                rows.append({"round": r, "dataset": ds, "name": name, "polled_utc": now, "end_utc": end,
                             "lag_min": round(lag, 1)})
                print(f"round {r} {ds:4d} {name:34s} latest interval ends {end:%H:%M} UTC, {lag:6.1f} min ago")
            except Exception as e:
                print(f"round {r} {ds:4d} {name:34s} ERROR {str(e)[:80]}")
        if r < a.rounds - 1:
            time.sleep(a.every)
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    if not df.empty:
        print("\nmax lag per dataset (min), the conservative figure for an availability rule:")
        print(df.groupby(["dataset", "name"])["lag_min"].agg(["min", "median", "max"]).round(1).to_string())
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()

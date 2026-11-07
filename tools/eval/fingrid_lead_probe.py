"""Measure WHEN Fingrid publishes the real-time mFRR prices relative to the quarter-hour they price.

Dataset 400 (scheduled activation price) is documented as published 7.5 min before its market time
unit; 401 / 402 (direct activation prices up / down) at the direct activation, before the MTU they
apply to. This probe polls the latest rows every --every seconds and records, for every new
quarter-hour value, the first time we saw it: lead_min = start of its quarter-hour - first seen
(positive = published before the quarter-hour starts). Our availability rule in
tools/ingest/fingrid.py assumes 400 is out by start - 2.5 min (lead >= 2.5) and never uses 401 / 402
for the quarter-hour at the origin. The first poll only records rows that already exist, so its
leads are not measured (they are dropped).

    uv run python -m tools.eval.fingrid_lead_probe --minutes 40 --every 30
Writes static_data/work/diagnostics/fingrid_lead_probe.csv.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import pandas as pd

from imbalance.paths import REPO_ROOT
from tools.ingest.fingrid import api_key
from tools.ingest.http import Client

DATASETS = {400: "mFRR scheduled activation price", 401: "mFRR direct activation price up",
            402: "mFRR direct activation price down"}
URL = "https://data.fingrid.fi/api/datasets/{id}/data"
OUT = REPO_ROOT / "static_data" / "work" / "diagnostics" / "fingrid_lead_probe.csv"


def poll(c: Client, ds: int) -> list[dict]:
    now = pd.Timestamp(datetime.now(timezone.utc))
    params = {"startTime": (now - pd.Timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "endTime": (now + pd.Timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "format": "json", "pageSize": 100, "sortOrder": "desc"}
    d = c.get_json(URL.format(id=ds), params=params)        # no cache: every poll must be fresh
    return d.get("data", []) if isinstance(d, dict) else d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--every", type=int, default=30, help="seconds between polls")
    a = ap.parse_args()
    c = Client(min_interval_s=2.5, headers={"x-api-key": api_key()})
    seen: dict[tuple[int, str], dict] = {}
    t_end = time.time() + a.minutes * 60
    first = True
    while time.time() < t_end:
        for ds, name in DATASETS.items():
            try:
                rows = poll(c, ds)
            except Exception as e:
                print(f"{ds} ERROR {str(e)[:80]}")
                continue
            now = pd.Timestamp(datetime.now(timezone.utc))
            for r in rows:
                key = (ds, r["startTime"])
                if key in seen:
                    continue
                start = pd.Timestamp(r["startTime"])
                lead = (start - now).total_seconds() / 60
                seen[key] = {"dataset": ds, "name": name, "start_utc": start, "first_seen_utc": now,
                             "value": r.get("value"), "lead_min": round(lead, 2), "measured": not first}
                if not first:
                    print(f"{ds} {name:34s} new value for {start:%H:%M} UTC first seen {now:%H:%M:%S}: "
                          f"lead {lead:+.1f} min (positive = before the quarter-hour starts)")
        first = False
        time.sleep(a.every)
    df = pd.DataFrame(seen.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    m = df[df["measured"]] if not df.empty else df
    if m.empty:
        print("no new values appeared during the probe")
    else:
        print("\nmeasured leads (min; positive = published before its quarter-hour starts):")
        print(m.groupby(["dataset", "name"])["lead_min"].agg(["count", "min", "median", "max"]).round(2).to_string())
        ok = m[m["dataset"] == 400]["lead_min"]
        if not ok.empty:
            verdict = "OK" if ok.min() >= 2.5 else "TOO LATE: do not use dataset 400 for step 1"
            print(f"\n400: earliest-published margin check (rule assumes lead >= 2.5 min): min lead {ok.min():.2f} -> {verdict}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()

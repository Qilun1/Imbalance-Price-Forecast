"""Nord Pool REMIT UMM (urgent market messages) for Finland, every message VERSION with its own
publication time, into static_data/raw/umm/ (gitignored, AGENTS.md rule 0).

Why: unplanned outages of nuclear units and interconnectors are announced here first (Turku Energia
uses UMM as its first alert source). The 9 Sep and 15 Sep scarcity spikes coincided with a nuclear
drop and a capped SE3 import link.

Availability (AGENTS.md rule 4): a message version is usable from the first full hour at or after
its publicationDate + 15 min (margin for API latency). Later versions (updates, cancellations) never
overwrite earlier ones: every version is stored and used only from its own publication time. The
API keeps old versions (GET /messages/{id}/{version}); this script fetches any version that the
list endpoint does not return.

    uv run python -m tools.ingest.umm --start 2026-04-01 --end 2026-11-03          # fetch + flatten
    uv run python -m tools.ingest.umm --probe                                       # print the fields

Outputs: raw/umm/pages/*.json, raw/umm/versions/<id>_<v>.json, raw/umm/umm_periods.parquet (one
row per message version x unit x time period).
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from imbalance.paths import RAW_DIR
from tools.ingest.http import Client

API = "https://ummapi.nordpoolgroup.com"
FI = "10YFI-1--------U"
OUT = RAW_DIR / "umm"
PAGE = 1000
UNIT_KEYS = ("generationUnits", "productionUnits", "consumptionUnits", "transmissionUnits", "otherUnits")


def list_pages(c: Client, start: str, end: str) -> list[dict]:
    items, skip = [], 0
    while True:
        params = {"limit": PAGE, "skip": skip, "areas": FI, "includeOutdated": "true",
                  "publicationStartDate": f"{start}T00:00:00.000Z", "publicationStopDate": f"{end}T00:00:00.000Z"}
        cache = OUT / "pages" / f"{start}_{end}_{skip}.json"
        data = c.get_json(f"{API}/messages", params=params, cache=cache)
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data), encoding="utf-8")
        got = data.get("items", data if isinstance(data, list) else [])
        items += got
        total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
        print(f"  page skip={skip}: {len(got)} messages (total {total})")
        if len(got) < PAGE or len(items) >= total:
            return items
        skip += PAGE


def all_versions(c: Client, items: list[dict]) -> list[dict]:
    have = {(m["messageId"], int(m.get("version", 1))) for m in items}
    out = list(items)
    for mid, v in sorted({(m["messageId"], int(m.get("version", 1))) for m in items}):
        for old in range(1, v):
            if (mid, old) in have:
                continue
            cache = OUT / "versions" / f"{mid}_{old}.json"
            try:
                m = c.get_json(f"{API}/messages/{mid}/{old}", cache=cache)
            except Exception as e:                     # some old versions may be gone: note and continue
                print(f"  version {mid}/{old} not available: {str(e)[:80]}")
                continue
            if not cache.exists():
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(m), encoding="utf-8")
            out.append(m)
            have.add((mid, old))
    return out


def flatten(msgs: list[dict]) -> pd.DataFrame:
    rows = []
    for m in msgs:
        base = {"message_id": m.get("messageId"), "version": int(m.get("version", 1)),
                "publication_utc": m.get("publicationDate"), "message_type": m.get("messageType"),
                "unavailability_type": m.get("unavailabilityType"), "event_status": m.get("eventStatus"),
                "is_outdated": m.get("isOutdated"), "reason": (m.get("reasonCode") or m.get("unavailabilityReason")),
                "areas": ";".join(a.get("code", "") for a in m.get("areas", []) or []),
                "msg_event_start": m.get("eventStart"), "msg_event_stop": m.get("eventStop")}
        units = [(k, u) for k in UNIT_KEYS for u in (m.get(k) or [])]
        if not units:
            rows.append({**base, "unit_kind": None})
            continue
        for kind, u in units:
            ub = {**base, "unit_kind": kind, "unit_name": u.get("name"), "unit_eic": u.get("eic"),
                  "fuel": u.get("fuelType"), "installed_mw": u.get("installedCapacity"),
                  "area": u.get("areaCode") or u.get("areaName"), "in_area": u.get("inAreaCode"),
                  "out_area": u.get("outAreaCode")}
            periods = u.get("timePeriods") or [{}]
            for p in periods:
                rows.append({**ub, "start_utc": p.get("eventStart", base["msg_event_start"]),
                             "stop_utc": p.get("eventStop", base["msg_event_stop"]),
                             "unavailable_mw": p.get("unavailableCapacity"), "available_mw": p.get("availableCapacity")})
    df = pd.DataFrame(rows)
    for c in ("publication_utc", "msg_event_start", "msg_event_stop", "start_utc", "stop_utc"):
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-11-03")
    ap.add_argument("--probe", action="store_true", help="fetch 2 messages and print their fields")
    a = ap.parse_args()
    c = Client(min_interval_s=0.5)
    if a.probe:
        d = c.get_json(f"{API}/messages", params={"limit": 2, "areas": FI, "includeOutdated": "true"})
        print(json.dumps(d, indent=1)[:6000])
        return
    items = list_pages(c, a.start, a.end)
    msgs = all_versions(c, items)
    df = flatten(msgs)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "umm_periods.parquet", index=False)
    print(f"{len(items)} listed, {len(msgs)} versions, {len(df)} unit-period rows -> {OUT / 'umm_periods.parquet'}")
    print(df.groupby(["message_type", "unit_kind"], dropna=False).size().to_string())


if __name__ == "__main__":
    main()

"""CLI: python -m backend.fuel [--spot 45] [--refresh] [--out fuel_snapshot.json]"""
import argparse
import json

from .service import build_snapshot, fetch_prices

ap = argparse.ArgumentParser()
ap.add_argument("--spot", type=float, default=None, help="EUR/MWh")
ap.add_argument("--refresh", action="store_true")
ap.add_argument("--out")
a = ap.parse_args()

snap = build_snapshot(fetch_prices(force=a.refresh), a.spot)
txt = json.dumps(snap, indent=1, ensure_ascii=False)
if a.out:
    open(a.out, "w", encoding="utf-8").write(txt)
print(txt)

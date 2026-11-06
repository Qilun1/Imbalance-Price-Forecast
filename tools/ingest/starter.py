"""Ingest the organiser's starter package data into static_data/.

1. Copies the data files unchanged into static_data/raw/starter/.
2. Inserts every row of inputs.parquet and spot_nordpool.csv into the `observations` table exactly as
   given (values and first_usable_origin_utc untouched).
3. Fills `series_catalog` from the data and the organiser's availability.csv.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pandas as pd

from imbalance import store
from imbalance.paths import STARTER_DATA_DIR, STARTER_PKG, ensure_dirs

FILES = ["inputs.parquet", "inputs.csv", "spot_nordpool.csv", "actuals_validation.csv",
         "quality_report.csv", "quality_report.md"]
REQUIRED = ["inputs.parquet", "spot_nordpool.csv", "actuals_validation.csv"]
LICENCE = {
    "fingrid": "CC BY 4.0 (Fingrid Open Data)",
    "entsoe": "CC BY 4.0 (ENTSO-E Transparency Platform)",
    "nordpool": "Nord Pool, licensed to Turku Energia: hackathon use only, do not share or publish",
    "calendar": "derived (organiser)",
}


def read_long(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, dtype={"dataset_id": str})
    for col in ("timestamp_utc", "first_usable_origin_utc"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


def _availability_rule(row: pd.Series, avail: pd.DataFrame) -> str:
    for _, a in avail.iterrows():
        if a["source"] != row["source"]:
            continue
        ids = [] if pd.isna(a["dataset_id"]) else str(a["dataset_id"]).split(";")
        ds = "" if pd.isna(row["dataset_id"]) else str(row["dataset_id"])
        if row["source"] in ("nordpool", "calendar") or ds in ids or ds.split(":")[0] in ids:
            if a["availability_type"] == "lag_after_period_end":
                return f"{int(a['lag_minutes'])} min after period end, next full hour"
            if a["availability_type"] == "daily_local_time":
                return f"D{int(a['publish_day_offset'])} {a['publish_time_local']} Europe/Helsinki"
            return str(a["availability_type"])
    return "per-row first_usable_origin_utc (organiser)"


def find_src(src: Path) -> Path:
    for cand in (src, src / "data", src / "starter_package_v1" / "data"):
        if all((cand / f).exists() for f in REQUIRED):
            return cand
    raise FileNotFoundError(f"starter data files {REQUIRED} not found under {src}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(src: Path | None) -> None:
    ensure_dirs()
    if src is not None:
        src = find_src(src)
        for name in FILES:
            if (src / name).exists() and (src / name).resolve() != (STARTER_DATA_DIR / name).resolve():
                shutil.copy2(src / name, STARTER_DATA_DIR / name)
                print(f"copied {name}  sha256 {sha256(STARTER_DATA_DIR / name)[:16]}...")
    missing = [f for f in REQUIRED if not (STARTER_DATA_DIR / f).exists()]
    if missing:
        raise FileNotFoundError(f"missing in {STARTER_DATA_DIR}: {missing}. Run with --src <starter data folder>.")

    inputs = read_long(STARTER_DATA_DIR / "inputs.parquet")
    spot = read_long(STARTER_DATA_DIR / "spot_nordpool.csv")
    for name, df in (("inputs", inputs), ("spot", spot)):
        n = store.insert_observations(df, batch=f"starter_v1:{name}")
        print(f"{name}: {len(df)} rows offered, {n} inserted")

    avail = pd.read_csv(STARTER_PKG / "availability.csv", dtype={"dataset_id": str})
    long = pd.concat([inputs, spot], ignore_index=True)
    cat = long.groupby("series_id", as_index=False).first()[["series_id", "source", "dataset_id", "unit"]]
    cat["kind"] = cat["source"].map(lambda s: "calendar" if s == "calendar" else "observation")
    cat["availability_rule"] = cat.apply(_availability_rule, axis=1, avail=avail)
    cat["licence"] = cat["source"].map(LICENCE)
    cat["description"] = "starter package v1"
    store.upsert_catalog(cat)
    print(f"catalog: {len(cat)} series")

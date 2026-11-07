"""API settings, read from environment variables.

IMBALANCE_DATA_MODE   "mock" (default, invented data, needs nothing else) or "real" (needs the
                      ingested store and the forecasts in backend/infer_data).
IMBALANCE_MODEL_VAL   model answering for validation origins, default lgbm_v1-val. Its forecasts
                      are out of sample; lgbm_v1 is in-sample there, so never show it for that period.
IMBALANCE_MODEL_TEST  model answering for test origins, default lgbm_v1.
IMBALANCE_CHALLENGER_VAL / IMBALANCE_CHALLENGER_TEST
                      second model for the conflicting-signals alert, default lgbm_v2-val / lgbm_v2.
                      It must use different input data from the main model (v2 adds ECMWF weather
                      to v1's Fingrid forecasts), so a disagreement means the sources disagree.
                      Set it to "none" to turn the alert off.
IMBALANCE_NOTES_VAL / IMBALANCE_NOTES_TEST
                      event classifiers behind /notes, default alerts-val / alerts. "none" turns
                      the notes off for that period.
IMBALANCE_CORS_ORIGINS
                      comma-separated browser origins allowed to call the API directly, e.g.
                      "http://localhost:5173". Empty (default): no CORS headers. The dashboard needs
                      none, it calls through its own proxy; scripts and curl need none either.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from imbalance.contract import TEST_FIRST_ORIGIN, VALIDATION_FIRST_ORIGIN
from imbalance.paths import INFER_DB, INFER_DIR, STATIC_DB

MOCK_DB = INFER_DIR / "mock_forecasts.duckdb"     # gitignored, built by backend/api/mock.py
MOCK_MODEL = "mock-model"
MOCK_BASELINE = "mock-baseline"
MOCK_CHALLENGER = "mock-challenger"
MOCK_NOTES = "mock-notes"


@dataclass(frozen=True)
class Period:
    """Which models answer for forecast origins from `first_origin` until the next period starts.
    `challenger` is the independent second model the conflicting-signals alert compares against."""
    name: str
    model: str
    baseline: str
    first_origin: pd.Timestamp | None = None
    challenger: str | None = None
    notes: str | None = None


def _challenger(variable: str, default: str) -> str | None:
    name = os.environ.get(variable, default).strip()
    return None if name.lower() in ("", "none") else name


@dataclass(frozen=True)
class Settings:
    mode: str
    periods: tuple[Period, ...]
    forecast_db: Path
    store_db: Path


def load_settings() -> Settings:
    mode = os.environ.get("IMBALANCE_DATA_MODE", "mock").strip().lower()
    if mode == "mock":
        return Settings("mock", (Period("mock", MOCK_MODEL, MOCK_BASELINE, challenger=MOCK_CHALLENGER, notes=MOCK_NOTES),), MOCK_DB, MOCK_DB)
    if mode == "real":
        periods = (
            Period("validation", os.environ.get("IMBALANCE_MODEL_VAL", "lgbm_v1-val"), "baseline-val",
                   VALIDATION_FIRST_ORIGIN, _challenger("IMBALANCE_CHALLENGER_VAL", "lgbm_v2-val"),
                   _challenger("IMBALANCE_NOTES_VAL", "alerts-val")),
            Period("test", os.environ.get("IMBALANCE_MODEL_TEST", "lgbm_v1"), "baseline-test", TEST_FIRST_ORIGIN,
                   _challenger("IMBALANCE_CHALLENGER_TEST", "lgbm_v2"), _challenger("IMBALANCE_NOTES_TEST", "alerts")),
        )
        return Settings("real", periods, INFER_DB, STATIC_DB)
    raise ValueError(f"IMBALANCE_DATA_MODE must be 'mock' or 'real', not {mode!r}")


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def cors_origins() -> list[str]:
    return [o.strip() for o in os.environ.get("IMBALANCE_CORS_ORIGINS", "").split(",") if o.strip()]

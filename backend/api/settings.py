"""API settings, read from environment variables.

IMBALANCE_DATA_MODE   "mock" (default, invented data, needs nothing else) or "real" (needs the
                      ingested store and the forecasts in backend/infer_data).
IMBALANCE_MODEL_VAL   model answering for validation origins, default lgbm_v1-val. Its forecasts
                      are out of sample; lgbm_v1 is in-sample there, so never show it for that period.
IMBALANCE_MODEL_TEST  model answering for test origins, default lgbm_v1.
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


@dataclass(frozen=True)
class Period:
    """Which models answer for forecast origins from `first_origin` until the next period starts."""
    name: str
    model: str
    baseline: str
    first_origin: pd.Timestamp | None = None


@dataclass(frozen=True)
class Settings:
    mode: str
    periods: tuple[Period, ...]
    forecast_db: Path
    store_db: Path


def load_settings() -> Settings:
    mode = os.environ.get("IMBALANCE_DATA_MODE", "mock").strip().lower()
    if mode == "mock":
        return Settings("mock", (Period("mock", MOCK_MODEL, MOCK_BASELINE),), MOCK_DB, MOCK_DB)
    if mode == "real":
        periods = (
            Period("validation", os.environ.get("IMBALANCE_MODEL_VAL", "lgbm_v1-val"), "baseline-val",
                   VALIDATION_FIRST_ORIGIN),
            Period("test", os.environ.get("IMBALANCE_MODEL_TEST", "lgbm_v1"), "baseline-test", TEST_FIRST_ORIGIN),
        )
        return Settings("real", periods, INFER_DB, STATIC_DB)
    raise ValueError(f"IMBALANCE_DATA_MODE must be 'mock' or 'real', not {mode!r}")


@lru_cache
def get_settings() -> Settings:
    return load_settings()

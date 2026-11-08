"""API settings, read from environment variables.

IMBALANCE_DATA_MODE   "mock" (default, invented data, needs nothing else) or "real" (needs the
                      ingested store and the forecasts in backend/infer_data).
IMBALANCE_MODEL_VAL   model answering for validation origins, default ens_finald-val (the submission's
                      validation version). Its forecasts are out of sample; the final ens_finald is
                      in-sample there, so never show it for that period.
IMBALANCE_MODEL_TEST  model answering for test origins, default ens_finald (the submission). Load both
                      with tools/eval/import_submission.py after building the submission (root README).
IMBALANCE_CHALLENGER_VAL / IMBALANCE_CHALLENGER_TEST
                      second model for the conflicting-signals alert, default lgbm_v2-val / lgbm_v2.
                      It must use different input data from the main model (v2 adds ECMWF weather
                      to v1's Fingrid forecasts), so a disagreement means the sources disagree.
                      Set it to "none" to turn the alert off.
IMBALANCE_NOTES_VAL / IMBALANCE_NOTES_TEST
                      event classifiers behind /notes, default alerts-val / alerts. "none" turns
                      the notes off for that period.
Real mode replays the test period as if it were then: it opens at the first test origin, and no observed
value (imbalance price, direction, spot history) from the test period on is served, whatever the viewing
time. Test forecasts are shown; what happened in the test period is not.

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
    # Observed values stop here (the test period's first origin); None shows everything usable.
    observed_until: pd.Timestamp | None = None


def load_settings() -> Settings:
    mode = os.environ.get("IMBALANCE_DATA_MODE", "mock").strip().lower()
    if mode == "mock":
        return Settings("mock", (Period("mock", MOCK_MODEL, MOCK_BASELINE, challenger=MOCK_CHALLENGER, notes=MOCK_NOTES),), MOCK_DB, MOCK_DB)
    if mode == "real":
        periods = (
            Period("validation", os.environ.get("IMBALANCE_MODEL_VAL", "ens_finald-val"), "baseline-val",
                   VALIDATION_FIRST_ORIGIN, _challenger("IMBALANCE_CHALLENGER_VAL", "lgbm_v2-val"),
                   _challenger("IMBALANCE_NOTES_VAL", "alerts-val")),
            Period("test", os.environ.get("IMBALANCE_MODEL_TEST", "ens_finald"), "baseline-test", TEST_FIRST_ORIGIN,
                   _challenger("IMBALANCE_CHALLENGER_TEST", "lgbm_v2"), _challenger("IMBALANCE_NOTES_TEST", "alerts")),
        )
        return Settings("real", periods, INFER_DB, STATIC_DB, observed_until=TEST_FIRST_ORIGIN)
    raise ValueError(f"IMBALANCE_DATA_MODE must be 'mock' or 'real', not {mode!r}")


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def cors_origins() -> list[str]:
    return [o.strip() for o in os.environ.get("IMBALANCE_CORS_ORIGINS", "").split(",") if o.strip()]

"""The organiser's rules, in one place. Values mirror tools/starter_package/README.md (schema 1.0).

Nothing in our code may change these. The submission columns and the forecast origins are read from
the organiser's own files, never retyped.
"""
from __future__ import annotations

import pandas as pd

from .paths import STARTER_PKG

SCHEMA_VERSION = "1.0"
HORIZON_STEPS = 40
STEP_MINUTES = 15
STEP = pd.Timedelta(minutes=STEP_MINUTES)
SPIKE_MARGIN = 50.0                                   # EUR/MWh, official scoring
TARGET_SERIES = "fi_imbalance_price"
DIRECTION_SERIES = "fi_mfrr_direction"                # 1 up, -1 down, 0 none
SPOT_SERIES = "fi_spot_price"

TRAIN_END_DELIVERY = pd.Timestamp("2026-10-04T20:45:00Z")   # last training quarter-hour (4 Oct local)
VALIDATION_DAYS = ("2026-09-07", "2026-10-04")               # local dates, for make_templates.py
VALIDATION_FIRST_ORIGIN = pd.Timestamp("2026-09-06T21:00:00Z")
TEST_DAYS = ("2026-10-05", "2026-11-01")
TEST_FIRST_ORIGIN = pd.Timestamp("2026-10-04T21:00:00Z")

TEMPLATE = STARTER_PKG / "sample_submission.csv"
TEST_ORIGINS = STARTER_PKG / "forecast_origins.csv"
VALIDATOR = STARTER_PKG / "validate_submission.py"
SCORER = STARTER_PKG / "score.py"
MAKE_TEMPLATES = STARTER_PKG / "make_templates.py"

FORECAST_COLUMNS = ["p10", "p50", "p90", "p_up", "p_down", "p_none", "p_spike_high", "p_spike_low"]


def submission_columns() -> list[str]:
    """Column order exactly as in the organiser's template."""
    return pd.read_csv(TEMPLATE, nrows=0).columns.tolist()


def read_origins(path) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(pd.read_csv(path)["forecast_origin_utc"], utc=True)).as_unit("ns")

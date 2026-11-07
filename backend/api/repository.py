"""Read-only access to forecasts and actuals for the API.

Two rules are enforced here, in one place, for every route:
- Availability: actuals pass through the organiser's own rows_available_at(), so at viewing time
  `as_of` the API shows only what was usable then, and forecasts are limited to origins <= as_of.
- Licence: only DISPLAY_SERIES is ever loaded, so the spot price never enters this process.

Mock and real data use the same tables, so there is one code path and only the file differs.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from imbalance import forecasts, store
from imbalance.contract import DIRECTION_SERIES, SPOT_SERIES, TARGET_SERIES
from tools.eval.baseline import rows_available_at

from backend.api.settings import Period, Settings, get_settings

DISPLAY_SERIES = (TARGET_SERIES, DIRECTION_SERIES)
if SPOT_SERIES in DISPLAY_SERIES:
    raise RuntimeError("the spot price must never be served (AGENTS.md rule 6)")

DIRECTION_NAMES = {1.0: "up", -1.0: "down", 0.0: "none"}
HOUR = pd.Timedelta(hours=1)


class OutOfRange(LookupError):
    """The requested viewing time is outside the forecasts we hold."""


def to_utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


class Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
        for path in {settings.forecast_db, settings.store_db}:
            if not path.exists():
                raise RuntimeError(f"{path} not found. Run the pipeline first, see tools/README.md.")
        self.primary = self._load("model")
        if self.primary.empty:
            names = [p.model for p in settings.periods]
            raise RuntimeError(f"no forecasts for {names} in {settings.forecast_db}")
        self.baseline = self._load("baseline")
        self.challenger = self._load("challenger")
        self._primary_by_origin = dict(tuple(self.primary.groupby("forecast_origin_utc")))
        self._challenger_by_origin = dict(tuple(self.challenger.groupby("forecast_origin_utc")))
        self.origins = pd.DatetimeIndex(sorted(self._primary_by_origin))
        self.observations = store.load_observations(list(DISPLAY_SERIES), settings.store_db)

    def _load(self, role: str) -> pd.DataFrame:
        """Forecast rows of every period, each limited to the origins that period answers for."""
        frames = []
        periods = self.settings.periods
        for i, period in enumerate(periods):
            if getattr(period, role) is None:
                continue
            df = forecasts.read(getattr(period, role), None, self.settings.forecast_db)
            if period.first_origin is not None:
                df = df[df["forecast_origin_utc"] >= period.first_origin]
            if i + 1 < len(periods):
                df = df[df["forecast_origin_utc"] < periods[i + 1].first_origin]
            if not df.empty:
                frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=forecasts.COLS)

    # ---------- viewing time ----------
    def resolve_as_of(self, as_of) -> pd.Timestamp:
        """The viewing time, defaulting to the newest forecast. Raises OutOfRange outside the data."""
        ts = self.origins[-1] if as_of is None else to_utc(as_of)
        if ts < self.origins[0] or ts >= self.origins[-1] + HOUR:
            raise OutOfRange(f"as_of must be from {self.origins[0]} to before {self.origins[-1] + HOUR}")
        return ts

    def origin_at(self, as_of: pd.Timestamp) -> pd.Timestamp:
        """The newest forecast already made at the viewing time."""
        return self.origins[self.origins.searchsorted(as_of, side="right") - 1]

    # ---------- forecasts ----------
    def forecast(self, origin: pd.Timestamp) -> pd.DataFrame:
        return self._primary_by_origin[origin].sort_values("step").reset_index(drop=True)

    def previous_forecast(self, origin: pd.Timestamp) -> pd.DataFrame | None:
        """The forecast one hour earlier from the same model, or None. Comparing across a model
        change would show the model switch as a market change."""
        previous = self._primary_by_origin.get(origin - HOUR)
        if previous is None or previous["model"].iloc[0] != self._primary_by_origin[origin]["model"].iloc[0]:
            return None
        return previous.sort_values("step").reset_index(drop=True)

    def challenger_forecast(self, origin: pd.Timestamp) -> pd.DataFrame | None:
        """The second model's forecast made at the same origin, or None. Same origin means the same
        data cutoff, so this adds no data the main forecast could not have used."""
        rows = self._challenger_by_origin.get(origin)
        if rows is None or rows["model"].iloc[0] == self._primary_by_origin[origin]["model"].iloc[0]:
            return None
        return rows.sort_values("step").reset_index(drop=True)

    # ---------- actuals ----------
    def actuals(self, as_of: pd.Timestamp, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> pd.DataFrame:
        """Price and direction usable at `as_of`, optionally for quarter-hours in [start, end)."""
        rows = self.observations
        if start is not None:
            rows = rows[rows["timestamp_utc"] >= start]
        if end is not None:
            rows = rows[rows["timestamp_utc"] < end]
        wide = rows_available_at(rows, as_of).reindex(columns=list(DISPLAY_SERIES))
        return pd.DataFrame({
            "delivery_start_utc": wide.index,
            "imbalance_price": wide[TARGET_SERIES].to_numpy(dtype=float),
            "direction": wide[DIRECTION_SERIES].map(DIRECTION_NAMES).to_numpy(dtype=object),
        }).reset_index(drop=True)

    # ---------- periods ----------
    def period_origins(self, period: Period) -> pd.DatetimeIndex:
        rows = self.primary[self.primary["model"] == period.model]
        return pd.DatetimeIndex(sorted(rows["forecast_origin_utc"].unique()))


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.mode == "mock" and not settings.forecast_db.exists():
        from backend.api.mock import generate
        generate(settings.forecast_db)
    return Repository(settings)

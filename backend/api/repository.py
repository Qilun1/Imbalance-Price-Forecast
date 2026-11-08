"""Read-only access to forecasts and actuals for the API.

Two rules are enforced here, in one place, for every route:
- Availability: observed rows pass through the organiser's own rows_available_at(), so at viewing time
  `as_of` the API shows only what was usable then, and forecasts are limited to origins <= as_of.
- Test period: observed values stop at `settings.observed_until` (real mode: the first test origin), as
  known then, whatever the viewing time. Test forecasts are shown, what happened after them is not.
- Licence: only DISPLAY_SERIES is ever loaded. It includes the spot price because the dashboard may show
  it (AGENTS.md rule 6). Spot goes to the dashboard and nowhere else: never log or export it.

Mock and real data use the same tables, so there is one code path and only the file differs.
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from imbalance import alert_inference, forecasts, store
from imbalance.contract import DIRECTION_SERIES, SPOT_SERIES, STEP, TARGET_SERIES
from imbalance.paths import ARTIFACTS_DIR
from tools.eval.baseline import rows_available_at

from backend.api.alerts import build_alerts
from backend.api.schemas import Alert
from backend.api.settings import Period, Settings, get_settings

DISPLAY_SERIES = (TARGET_SERIES, DIRECTION_SERIES, SPOT_SERIES)

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
        self.observed_until = settings.observed_until
        # The default viewing time: the first forecast of the test period, or the newest without one.
        cut = self.observed_until
        self.start = self.origins[-1] if cut is None else self.origins[min(self.origins.searchsorted(cut), len(self.origins) - 1)]
        self.observations = store.load_observations(list(DISPLAY_SERIES), settings.store_db)
        self.event_probs = self._load("notes")
        self._notes_by_origin = dict(tuple(self.event_probs.groupby("forecast_origin_utc")))
        self.low_skill = {p.notes: _low_skill_events(p.notes) for p in settings.periods if p.notes}
        self._spot_rows = self.observations[self.observations["series_id"] == SPOT_SERIES]
        self._alerts_by_origin: dict[pd.Timestamp, list[Alert]] = {}

    def _load(self, role: str) -> pd.DataFrame:
        """Rows of every period, each limited to the origins that period answers for: forecasts, or
        event probabilities for role "notes"."""
        frames = []
        periods = self.settings.periods
        for i, period in enumerate(periods):
            if getattr(period, role) is None:
                continue
            if role == "notes":
                df = alert_inference.read_probs(period.notes, None, self.settings.forecast_db)
            else:
                df = forecasts.read(getattr(period, role), None, self.settings.forecast_db)
            if period.first_origin is not None:
                df = df[df["forecast_origin_utc"] >= period.first_origin]
            if i + 1 < len(periods):
                df = df[df["forecast_origin_utc"] < periods[i + 1].first_origin]
            if not df.empty:
                frames.append(df)
        if frames:
            return pd.concat(frames, ignore_index=True)
        return pd.DataFrame(columns=alert_inference.COLS if role == "notes" else forecasts.COLS)

    # ---------- viewing time ----------
    def resolve_as_of(self, as_of) -> pd.Timestamp:
        """The viewing time, defaulting to `start`. Raises OutOfRange outside the data."""
        ts = self.start if as_of is None else to_utc(as_of)
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

    def event_notes(self, origin: pd.Timestamp) -> pd.DataFrame | None:
        """Event probabilities made at the origin, or None if no notes model answers for it."""
        rows = self._notes_by_origin.get(origin)
        return None if rows is None else rows.reset_index(drop=True)

    def alerts_at(self, origin: pd.Timestamp) -> list[Alert]:
        """The alerts of one forecast. A past forecast never changes, so each is built once."""
        if origin not in self._alerts_by_origin:
            self._alerts_by_origin[origin] = build_alerts(self.forecast(origin), self.previous_forecast(origin),
                                                         self.challenger_forecast(origin))
        return self._alerts_by_origin[origin]

    def prepare_alerts(self) -> None:
        """Build every forecast's alerts ahead of the first history request."""
        for origin in self.origins:
            self.alerts_at(origin)

    # ---------- observed values ----------
    def observed_end(self, end: pd.Timestamp) -> pd.Timestamp:
        """`end`, cut where observed values stop (the test period's first origin in real mode)."""
        return end if self.observed_until is None else min(end, self.observed_until)

    def actuals(self, as_of: pd.Timestamp, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> pd.DataFrame:
        """Price, direction and spot usable at `as_of`, optionally for quarter-hours in [start, end).
        A quarter-hour can have spot and no realised price yet, so price and direction may be empty.
        Never past `observed_until`: neither a later quarter-hour nor a row published after it."""
        if self.observed_until is not None:
            as_of = min(as_of, self.observed_until)
            end = self.observed_end(end) if end is not None else self.observed_until
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
            "spot": wide[SPOT_SERIES].to_numpy(dtype=float),
        }).reset_index(drop=True)

    def spot(self, as_of: pd.Timestamp, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        """Spot prices usable at `as_of` for quarter-hours in [start, end), by delivery time."""
        rows = self._spot_rows
        wide = rows_available_at(rows[(rows["timestamp_utc"] >= start) & (rows["timestamp_utc"] < end)], as_of)
        return wide[SPOT_SERIES] if SPOT_SERIES in wide else pd.Series(dtype=float)

    def spot_known_until(self, as_of: pd.Timestamp) -> pd.Timestamp | None:
        """End of the last quarter-hour whose spot price was published by `as_of`."""
        rows = self._spot_rows
        known = rows.loc[rows["first_usable_origin_utc"] <= as_of, "timestamp_utc"]
        return known.max() + STEP if len(known) else None

    # ---------- periods ----------
    def period_origins(self, period: Period) -> pd.DatetimeIndex:
        rows = self.primary[self.primary["model"] == period.model]
        return pd.DatetimeIndex(sorted(rows["forecast_origin_utc"].unique()))


def _low_skill_events(model: str) -> frozenset[str]:
    """Events hidden from /notes by default (meta.json): validation Brier skill below the bundle's bar,
    or listed in its hidden_events; none if unknown."""
    path = ARTIFACTS_DIR / model / "meta.json"
    if not path.exists():
        return frozenset()
    meta = json.loads(path.read_text())
    bar = meta.get("low_skill_bss", 0.0)
    weak = {e for e, bss in meta.get("validation_bss", {}).items() if bss is not None and bss < bar}
    return frozenset(weak | set(meta.get("hidden_events", [])))


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.mode != "mock":
        return Repository(settings)
    from backend.api.mock import generate
    if not settings.forecast_db.exists():
        generate(settings.forecast_db)
    repo = Repository(settings)
    if repo.spot_known_until(repo.origins[-1]) is None or repo.challenger.empty:     # an older mock file
        generate(settings.forecast_db)
        repo = Repository(settings)
    return repo

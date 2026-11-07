"""Response shapes of the API. All timestamps are UTC; prices are EUR/MWh.

Spot fields are licensed data (AGENTS.md rule 6). The dashboard may show them, and they carry a value
only from the row's first_usable_origin_utc, so at a viewing time they hold what was published by then.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Direction = Literal["up", "down", "none"]
AlertKind = Literal["spike_risk", "regulation_expected", "forecast_changed", "conflicting_signals",
                    "high_uncertainty", "stale_data", "expert_review"]


class Driver(BaseModel):
    id: str
    label: str


class ForecastStep(BaseModel):
    step: int
    delivery_start_utc: datetime
    p10: float
    p50: float
    p90: float
    p_up: float
    p_down: float
    p_none: float
    p_spike_high: float
    p_spike_low: float
    spot: float | None
    drivers: list[Driver]


class Forecast(BaseModel):
    as_of_utc: datetime
    origin_utc: datetime
    model: str
    data_cutoff_utc: datetime | None
    data_age_minutes: int | None
    spot_known_until_utc: datetime | None
    steps: list[ForecastStep]


class ActualPoint(BaseModel):
    delivery_start_utc: datetime
    imbalance_price: float | None
    direction: Direction | None
    spot: float | None


class Actuals(BaseModel):
    as_of_utc: datetime
    from_utc: datetime
    to_utc: datetime
    points: list[ActualPoint]


class ChangePoint(BaseModel):
    delivery_start_utc: datetime
    p50: float
    p50_previous: float
    p50_change: float
    p_up_change: float
    p_spike_high_change: float
    p_spike_low_change: float


class Changes(BaseModel):
    as_of_utc: datetime
    origin_utc: datetime
    previous_origin_utc: datetime | None
    largest_p50_change: float | None
    points: list[ChangePoint]


class Alert(BaseModel):
    kind: AlertKind
    severity: Literal["watch", "review"]
    title: str
    message: str
    check: str
    window_start_utc: datetime
    window_end_utc: datetime
    drivers: list[Driver]
    evidence: dict[str, float]


class Alerts(BaseModel):
    as_of_utc: datetime
    origin_utc: datetime
    model: str
    alerts: list[Alert]


class SituationHour(BaseModel):
    """How many situations were open at one forecast. Hours with none are left out."""
    origin_utc: datetime
    review: int
    watch: int


class Situation(BaseModel):
    """One situation, from the forecast that first raised it to the last one that still did."""
    first_origin_utc: datetime
    last_origin_utc: datetime
    alert: Alert


class AlertHistory(BaseModel):
    as_of_utc: datetime
    from_utc: datetime
    to_utc: datetime
    hours: list[SituationHour]
    situations: list[Situation]


class Scores(BaseModel):
    rows: int
    mae_p50: float | None
    calibration_pinball_mean: float | None
    coverage_p10_p90: float | None
    brier_spike_mean: float | None
    brier_direction: float | None


class HorizonScores(Scores):
    horizon_hour: int


class ScoreSet(BaseModel):
    label: str
    model: str
    overall: Scores
    by_horizon: list[HorizonScores]


class OfficialScores(BaseModel):
    """Written by the organiser's score.py for the whole validation period."""
    note: str
    model: ScoreSet
    baseline: ScoreSet | None


class DiagnosticScores(BaseModel):
    """Our own window-based extra. It never replaces score.py (AGENTS.md rule 5)."""
    note: str
    model: ScoreSet | None
    baseline: ScoreSet | None


class Performance(BaseModel):
    as_of_utc: datetime
    from_utc: datetime
    to_utc: datetime
    official: OfficialScores | None
    diagnostic: DiagnosticScores


class HindsightPoint(BaseModel):
    delivery_start_utc: datetime
    p10: float
    p50: float
    p90: float
    baseline_p50: float | None
    actual: float | None
    spot: float | None


class Hindsight(BaseModel):
    """Each quarter-hour as forecast `lead_hours` ahead, against what happened."""
    as_of_utc: datetime
    from_utc: datetime
    to_utc: datetime
    lead_hours: int
    points: list[HindsightPoint]


class PeriodInfo(BaseModel):
    name: str
    model: str
    baseline: str
    first_origin_utc: datetime | None
    last_origin_utc: datetime | None
    origins: int


class Meta(BaseModel):
    mode: Literal["mock", "real"]
    note: str
    first_origin_utc: datetime
    last_origin_utc: datetime
    origins: int
    periods: list[PeriodInfo]
    horizon_steps: int
    step_minutes: int
    spike_margin_eur_mwh: float
    display_timezone: str

"""The 10-hour forecast at a viewing time, and how it changed since the previous update."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from imbalance.contract import STEP

from backend.api.labels import label_for
from backend.api.repository import Repository, get_repository
from backend.api.schemas import ChangePoint, Changes, Driver, Forecast, ForecastStep

router = APIRouter(tags=["forecast"])


def _drivers(text: str | None) -> list[Driver]:
    if not isinstance(text, str):
        return []
    return [Driver(id=name, label=label_for(name)) for name in text.split(";") if name]


@router.get("/forecast", response_model=Forecast)
def get_forecast(as_of: AwareDatetime | None = Query(None, description="Viewing time; start_origin_utc of /api/meta if omitted"),
                 repo: Repository = Depends(get_repository)) -> Forecast:
    moment = repo.resolve_as_of(as_of)
    origin = repo.origin_at(moment)
    rows = repo.forecast(origin)
    cutoff = rows["data_cutoff_utc"].iloc[0]
    has_cutoff = not pd.isna(cutoff)
    spot = repo.spot(moment, rows["delivery_start_utc"].iloc[0], rows["delivery_start_utc"].iloc[-1] + STEP)
    steps = [ForecastStep(step=int(r.step), delivery_start_utc=r.delivery_start_utc,
                          p10=round(r.p10, 2), p50=round(r.p50, 2), p90=round(r.p90, 2),
                          p_up=round(r.p_up, 4), p_down=round(r.p_down, 4), p_none=round(r.p_none, 4),
                          p_spike_high=round(r.p_spike_high, 4), p_spike_low=round(r.p_spike_low, 4),
                          spot=round(spot[r.delivery_start_utc], 2) if r.delivery_start_utc in spot.index else None,
                          drivers=_drivers(r.top_drivers))
             for r in rows.itertuples(index=False)]
    return Forecast(as_of_utc=moment, origin_utc=origin, model=rows["model"].iloc[0],
                    data_cutoff_utc=cutoff if has_cutoff else None,
                    data_age_minutes=int((origin - cutoff) / pd.Timedelta(minutes=1)) if has_cutoff else None,
                    spot_known_until_utc=repo.spot_known_until(moment), steps=steps)


@router.get("/changes", response_model=Changes)
def get_changes(as_of: AwareDatetime | None = Query(None, description="Viewing time; start_origin_utc of /api/meta if omitted"),
                repo: Repository = Depends(get_repository)) -> Changes:
    moment = repo.resolve_as_of(as_of)
    origin = repo.origin_at(moment)
    previous = repo.previous_forecast(origin)
    if previous is None:
        return Changes(as_of_utc=moment, origin_utc=origin, previous_origin_utc=None, largest_p50_change=None, points=[])
    both = repo.forecast(origin).merge(previous, on="delivery_start_utc", suffixes=("", "_prev"))
    points = [ChangePoint(delivery_start_utc=r.delivery_start_utc, p50=round(r.p50, 2), p50_previous=round(r.p50_prev, 2),
                          p50_change=round(r.p50 - r.p50_prev, 2), p_up_change=round(r.p_up - r.p_up_prev, 4),
                          p_spike_high_change=round(r.p_spike_high - r.p_spike_high_prev, 4),
                          p_spike_low_change=round(r.p_spike_low - r.p_spike_low_prev, 4))
              for r in both.itertuples(index=False)]
    largest = max((p.p50_change for p in points), key=abs) if points else None
    return Changes(as_of_utc=moment, origin_utc=origin, previous_origin_utc=previous["forecast_origin_utc"].iloc[0],
                   largest_p50_change=largest, points=points)

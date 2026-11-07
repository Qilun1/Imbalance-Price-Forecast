"""The situations worth checking at a viewing time."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from backend.api.alerts import build_alerts
from backend.api.repository import Repository, get_repository
from backend.api.schemas import Alerts

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=Alerts)
def get_alerts(as_of: AwareDatetime | None = Query(None, description="Viewing time; the newest forecast if omitted"),
               repo: Repository = Depends(get_repository)) -> Alerts:
    moment = repo.resolve_as_of(as_of)
    origin = repo.origin_at(moment)
    current = repo.forecast(origin)
    return Alerts(as_of_utc=moment, origin_utc=origin, model=current["model"].iloc[0],
                  alerts=build_alerts(current, repo.previous_forecast(origin), repo.challenger_forecast(origin)))

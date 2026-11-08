"""The situations worth checking at a viewing time, and the ones raised before it."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from backend.api.alerts import build_history
from backend.api.outcomes import add_outcomes
from backend.api.repository import Repository, get_repository, to_utc
from backend.api.schemas import AlertHistory, Alerts

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=Alerts)
def get_alerts(as_of: AwareDatetime | None = Query(None, description="Viewing time; start_origin_utc of /api/meta if omitted"),
               repo: Repository = Depends(get_repository)) -> Alerts:
    moment = repo.resolve_as_of(as_of)
    origin = repo.origin_at(moment)
    return Alerts(as_of_utc=moment, origin_utc=origin, model=repo.forecast(origin)["model"].iloc[0],
                  alerts=repo.alerts_at(origin))


@router.get("/alerts/history", response_model=AlertHistory)
def get_alert_history(start: AwareDatetime | None = Query(None, alias="from", description="First forecast time; the first forecast if omitted"),
                      end: AwareDatetime | None = Query(None, alias="to", description="End of the range, exclusive; nothing after as_of is ever included"),
                      as_of: AwareDatetime | None = Query(None, description="Viewing time; start_origin_utc of /api/meta if omitted"),
                      repo: Repository = Depends(get_repository)) -> AlertHistory:
    moment = repo.resolve_as_of(as_of)
    first = to_utc(start) if start is not None else repo.origins[0]
    last = to_utc(end) if end is not None else moment + pd.Timedelta(minutes=1)
    origins = repo.origins[(repo.origins >= first) & (repo.origins <= moment) & (repo.origins < last)]
    hours, situations = build_history({origin: repo.alerts_at(origin) for origin in origins})
    return AlertHistory(as_of_utc=moment, from_utc=first, to_utc=last, hours=hours,
                        situations=add_outcomes(repo, situations, moment))

"""Forecast against what happened, for one lead time."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from backend.api.performance import build_hindsight
from backend.api.repository import Repository, get_repository, to_utc
from backend.api.schemas import Hindsight

router = APIRouter(tags=["hindsight"])
DEFAULT_WINDOW = pd.Timedelta(days=7)


@router.get("/hindsight", response_model=Hindsight)
def get_hindsight(start: AwareDatetime | None = Query(None, alias="from", description="First quarter-hour; 7 days before as_of if omitted"),
                  end: AwareDatetime | None = Query(None, alias="to", description="End of the range, exclusive; as_of if omitted"),
                  lead_hours: int = Query(1, ge=1, le=10, description="How many hours ahead the forecast was made"),
                  as_of: AwareDatetime | None = Query(None, description="Viewing time; start_origin_utc of /api/meta if omitted"),
                  repo: Repository = Depends(get_repository)) -> Hindsight:
    moment = repo.resolve_as_of(as_of)
    first = to_utc(start) if start is not None else moment - DEFAULT_WINDOW
    last = to_utc(end) if end is not None else moment
    return build_hindsight(repo, moment, first, last, lead_hours)

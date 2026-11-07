"""Realised imbalance price and direction, limited to what was usable at the viewing time."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from backend.api.repository import Repository, get_repository, to_utc
from backend.api.schemas import ActualPoint, Actuals

router = APIRouter(tags=["actuals"])
DEFAULT_LOOKBACK = pd.Timedelta(hours=24)


@router.get("/actuals", response_model=Actuals)
def get_actuals(start: AwareDatetime | None = Query(None, alias="from", description="First quarter-hour; 24 h before as_of if omitted"),
                end: AwareDatetime | None = Query(None, alias="to", description="End of the range, exclusive; as_of if omitted"),
                as_of: AwareDatetime | None = Query(None, description="Viewing time; the newest forecast if omitted"),
                repo: Repository = Depends(get_repository)) -> Actuals:
    moment = repo.resolve_as_of(as_of)
    first = to_utc(start) if start is not None else moment - DEFAULT_LOOKBACK
    last = to_utc(end) if end is not None else moment
    rows = repo.actuals(moment, first, last)
    points = [ActualPoint(delivery_start_utc=r.delivery_start_utc,
                          imbalance_price=None if pd.isna(r.imbalance_price) else round(r.imbalance_price, 2),
                          direction=None if pd.isna(r.direction) else r.direction)
              for r in rows.itertuples(index=False)]
    return Actuals(as_of_utc=moment, from_utc=first, to_utc=last, points=points)

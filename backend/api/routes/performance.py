"""How the forecast has performed: official validation scores plus a chosen window."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from backend.api.performance import build_performance
from backend.api.repository import Repository, get_repository, to_utc
from backend.api.schemas import Performance

router = APIRouter(tags=["performance"])
DEFAULT_WINDOW = pd.Timedelta(days=7)


@router.get("/performance", response_model=Performance)
def get_performance(start: AwareDatetime | None = Query(None, alias="from", description="First quarter-hour; 7 days before as_of if omitted"),
                    end: AwareDatetime | None = Query(None, alias="to", description="End of the range, exclusive; as_of if omitted"),
                    as_of: AwareDatetime | None = Query(None, description="Viewing time; the newest forecast if omitted"),
                    repo: Repository = Depends(get_repository)) -> Performance:
    moment = repo.resolve_as_of(as_of)
    first = to_utc(start) if start is not None else moment - DEFAULT_WINDOW
    last = to_utc(end) if end is not None else moment
    return build_performance(repo, moment, first, last)

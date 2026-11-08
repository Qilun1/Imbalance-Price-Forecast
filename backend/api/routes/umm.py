"""Nord Pool UMM messages that affect Finland's supply or imports in the next hours, with links."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel

from backend.api.repository import Repository, get_repository
from backend.api.umm_feed import available, umm_feed

router = APIRouter(tags=["umm"])


class UmmMessage(BaseModel):
    message_id: str
    version: int
    kind: str                     # generation | transmission
    unplanned: bool
    units: list[str]
    fuel: str | None
    unavailable_mw: float
    event_start_utc: datetime
    event_stop_utc: datetime
    publication_utc: datetime
    fresh: bool                   # first published in the last 3 h
    reason: str | None
    url: str                      # the message on umm.nordpoolgroup.com


class UmmFeed(BaseModel):
    as_of_utc: datetime
    available: bool               # False when the UMM data has not been ingested (mock mode)
    messages: list[UmmMessage]


@router.get("/umm", response_model=UmmFeed)
def get_umm(as_of: AwareDatetime | None = Query(None, description="Viewing time; start_origin_utc of /api/meta if omitted"),
            hours: float = Query(10.0, ge=1, le=48, description="Look-ahead window"),
            min_mw: float = Query(50.0, ge=0, description="Smallest unavailable capacity to show"),
            repo: Repository = Depends(get_repository)) -> UmmFeed:
    moment = pd.Timestamp(repo.resolve_as_of(as_of))
    return UmmFeed(as_of_utc=moment.to_pydatetime(), available=available(),
                   messages=[UmmMessage(**m) for m in umm_feed(moment, hours, min_mw)])

"""Learned event notes for the trader and plant-operator views."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime

from backend.api.notes import build_notes, parse_thresholds
from backend.api.repository import Repository, get_repository
from backend.api.schemas import Notes, Persona

router = APIRouter(tags=["notes"])


@router.get("/notes", response_model=Notes)
def get_notes(persona: Persona | None = Query(None, description="trader or operator (CHP with electric boilers); every event if omitted"),
              as_of: AwareDatetime | None = Query(None, description="Viewing time; start_origin_utc of /api/meta if omitted"),
              thresholds: str | None = Query(None, description="Per-event thresholds overriding the defaults, "
                                             "e.g. spike_high:0.3,extreme_price:0.2"),
              include_low_skill: bool = Query(False, description="Also return events with little validation skill"),
              repo: Repository = Depends(get_repository)) -> Notes:
    try:
        overrides = parse_thresholds(thresholds)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    moment = repo.resolve_as_of(as_of)
    origin = repo.origin_at(moment)
    probs = repo.event_notes(origin)
    if probs is None:
        return Notes(as_of_utc=moment, origin_utc=origin, persona=persona, model="none", notes=[])
    model = probs["model"].iloc[0]
    return Notes(as_of_utc=moment, origin_utc=origin, persona=persona, model=model,
                 notes=build_notes(probs, persona, origin, repo.low_skill.get(model, frozenset()), overrides,
                                   include_low_skill))

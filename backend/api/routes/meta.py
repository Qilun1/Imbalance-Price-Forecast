"""What the API is serving: data mode, models and the range of viewing times."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from imbalance.contract import HORIZON_STEPS, SPIKE_MARGIN, STEP_MINUTES

from backend.api.alerts import DISPLAY_TZ
from backend.api.repository import Repository, get_repository
from backend.api.schemas import Meta, PeriodInfo

router = APIRouter(tags=["meta"])

NOTES = {"mock": "Invented demo data. Not a real forecast and not real prices.",
         "real": "Backtest forecasts made only with data usable at each forecast time."}


@router.get("/meta", response_model=Meta)
def get_meta(repo: Repository = Depends(get_repository)) -> Meta:
    periods = []
    for period in repo.settings.periods:
        origins = repo.period_origins(period)
        periods.append(PeriodInfo(name=period.name, model=period.model, baseline=period.baseline,
                                  first_origin_utc=origins[0] if len(origins) else None,
                                  last_origin_utc=origins[-1] if len(origins) else None, origins=len(origins)))
    return Meta(mode=repo.settings.mode, note=NOTES[repo.settings.mode],
                first_origin_utc=repo.origins[0], last_origin_utc=repo.origins[-1], origins=len(repo.origins),
                periods=periods, horizon_steps=HORIZON_STEPS, step_minutes=STEP_MINUTES,
                spike_margin_eur_mwh=SPIKE_MARGIN, display_timezone=DISPLAY_TZ)

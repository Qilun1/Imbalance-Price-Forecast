"""FastAPI router, registered in backend/api/main.py (prefix /api).

GET /api/fuel/snapshot          -> panel JSON; the Naantali CHP screen calls it without spot
GET /api/fuel/snapshot?spot=45.2 -> also fills in the e-boiler comparison. Not for the dashboard:
                                   the query string lands in the access log (AGENTS.md rule 6)
GET /api/fuel/snapshot?refresh=true -> force a re-fetch from Statistics Finland
"""
from fastapi import APIRouter, Query

from .service import build_snapshot, fetch_prices

router = APIRouter(prefix="/fuel", tags=["fuel"])


@router.get("/snapshot")
def snapshot(spot: float | None = Query(None, description="EUR/MWh"),
             refresh: bool = False) -> dict:
    return build_snapshot(fetch_prices(force=refresh), spot)

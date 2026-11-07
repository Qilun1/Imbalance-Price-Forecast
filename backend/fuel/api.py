"""FastAPI router, not registered yet. To enable, add it to the router loop in
backend/api/main.py (prefix /api):

    from backend.fuel import api as fuel

GET /api/fuel/snapshot?spot=45.2   -> panel JSON (spot optional; pass the current or
                                  forecast spot so the e-boiler comparison fills in)
GET /fuel/snapshot?refresh=true -> force a re-fetch from Statistics Finland
"""
from fastapi import APIRouter, Query

from .service import build_snapshot, fetch_prices

router = APIRouter(prefix="/fuel", tags=["fuel"])


@router.get("/snapshot")
def snapshot(spot: float | None = Query(None, description="EUR/MWh"),
             refresh: bool = False) -> dict:
    return build_snapshot(fetch_prices(force=refresh), spot)

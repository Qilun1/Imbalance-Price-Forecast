"""Situational API for the imbalance price forecast.

Run from the repo root:  uv run uvicorn backend.api.main:app --reload --port 8000
Interactive docs:        http://127.0.0.1:8000/docs
Set IMBALANCE_DATA_MODE=real to serve the pipeline's forecasts; the default is invented mock data.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.api.repository import OutOfRange, get_repository
from backend.api.routes import actuals, alerts, forecast, meta, notes, performance


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_repository()            # fail at start-up with a clear message, not on the first request
    yield


app = FastAPI(title="Imbalance price forecast API", version="0.1.0", lifespan=lifespan)

for module in (meta, forecast, actuals, alerts, notes, performance):
    app.include_router(module.router, prefix="/api")


@app.exception_handler(OutOfRange)
async def out_of_range(_: Request, error: OutOfRange) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})

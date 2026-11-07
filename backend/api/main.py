"""Situational API for the imbalance price forecast.

Run from the repo root:  uv run python -m uvicorn backend.api.main:app --reload --port 8000
Interactive docs:        http://127.0.0.1:8000/docs
Set IMBALANCE_DATA_MODE=real to serve the pipeline's forecasts; the default is invented mock data.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.repository import OutOfRange, get_repository
from backend.api.routes import actuals, alerts, forecast, hindsight, meta, notes, performance, umm
from backend.api.settings import cors_origins


@asynccontextmanager
async def lifespan(_: FastAPI):
    repo = get_repository()     # fail at start-up with a clear message, not on the first request
    Thread(target=repo.prepare_alerts, daemon=True).start()     # takes seconds over all real forecasts
    yield


app = FastAPI(title="Imbalance price forecast API", version="0.1.0", lifespan=lifespan)

for module in (meta, forecast, actuals, alerts, notes, performance, hindsight, umm):
    app.include_router(module.router, prefix="/api")

# Browser apps on another origin need CORS; off unless IMBALANCE_CORS_ORIGINS names them. Read-only API.
if cors_origins():
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["GET"])


# Plain HTML/CSS/JS mockup of the notification chat (mockup/), separate from the React frontend.
MOCKUP_DIR = Path(__file__).resolve().parents[2] / "mockup"
if MOCKUP_DIR.is_dir():
    app.mount("/mockup", StaticFiles(directory=MOCKUP_DIR, html=True), name="mockup")


@app.exception_handler(OutOfRange)
async def out_of_range(_: Request, error: OutOfRange) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})

"""Repository paths. Everything is resolved relative to the repo root so the code runs the same on
Windows, macOS and Linux, from any working directory."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("IMBALANCE_REPO_ROOT", Path(__file__).resolve().parents[2]))

STATIC_DIR = REPO_ROOT / "static_data"
RAW_DIR = STATIC_DIR / "raw"
STARTER_DATA_DIR = RAW_DIR / "starter"
PROCESSED_DIR = STATIC_DIR / "processed"
STATIC_DB = STATIC_DIR / "static.duckdb"

BACKEND_DIR = REPO_ROOT / "backend"
ARTIFACTS_DIR = BACKEND_DIR / "artifacts"
INFER_DIR = BACKEND_DIR / "infer_data"
INFER_DB = INFER_DIR / "forecasts.duckdb"

TOOLS_DIR = REPO_ROOT / "tools"
STARTER_PKG = TOOLS_DIR / "starter_package"     # organiser's package: read-only
CONFIGS_DIR = TOOLS_DIR / "training" / "configs"
WORK_DIR = STATIC_DIR / "work"                  # scratch outputs (templates, scores), gitignored


def ensure_dirs() -> None:
    for d in (RAW_DIR, STARTER_DATA_DIR, PROCESSED_DIR, ARTIFACTS_DIR, INFER_DIR, WORK_DIR):
        d.mkdir(parents=True, exist_ok=True)

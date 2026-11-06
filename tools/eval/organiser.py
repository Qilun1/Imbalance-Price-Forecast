"""Run the organiser's locked scripts (make_templates.py, validate_submission.py, score.py) unchanged.

They are called as subprocesses with their own command-line interface, exactly as the README
documents. Outputs go to static_data/work/, never into tools/starter_package/.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from imbalance.contract import (MAKE_TEMPLATES, SCORER, SPIKE_MARGIN, TEMPLATE, TEST_DAYS, TEST_ORIGINS,
                                VALIDATION_DAYS, VALIDATOR)
from imbalance.paths import STARTER_DATA_DIR, STARTER_PKG, WORK_DIR

PERIOD_DAYS = {"val": VALIDATION_DAYS, "test": TEST_DAYS}


def _run(args: list[str]) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, *args], cwd=STARTER_PKG, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    return r


def templates(period: str) -> tuple[Path, Path]:
    """(sample_submission.csv, forecast_origins.csv) for a period. Test uses the package's own files."""
    if period == "test":
        return TEMPLATE, TEST_ORIGINS
    out = WORK_DIR / "templates" / period
    tpl, ori = out / "sample_submission.csv", out / "forecast_origins.csv"
    if not (tpl.exists() and ori.exists()):
        out.mkdir(parents=True, exist_ok=True)
        start, end = PERIOD_DAYS[period]
        r = _run([str(MAKE_TEMPLATES), "--test-start", start, "--test-end", end, "--output-dir", str(out)])
        if r.returncode != 0:
            raise RuntimeError(r.stdout + r.stderr)
    return tpl, ori


def validate(submission: Path, origins: Path) -> tuple[bool, str]:
    r = _run([str(VALIDATOR), "--backtest", str(submission), "--origins", str(origins)])
    return r.returncode == 0, r.stdout + r.stderr


def score(submission: Path, out_dir: Path, baseline_summary: Path | None = None) -> tuple[bool, str]:
    args = [str(SCORER), "--submission", str(submission), "--actuals", str(STARTER_DATA_DIR / "actuals_validation.csv"),
            "--spike-margin", str(int(SPIKE_MARGIN)), "--output-dir", str(out_dir)]
    if baseline_summary is not None and baseline_summary.exists():
        args += ["--baseline-summary", str(baseline_summary)]
    r = _run(args)
    return r.returncode == 0, r.stdout + r.stderr

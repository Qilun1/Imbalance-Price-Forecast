"""How the forecast has performed, in two clearly separated parts.

official    the organiser's score.py results for the validation period, read as written. These are
            the numbers to quote.
diagnostic  the same formulas over a chosen window, for the dashboard. Calculated by calling the
            organiser's compute_metrics() unchanged, so the formulas cannot drift.

Test-period diagnostics are for display only: they must never guide model choice, tuning or
calibration (AGENTS.md rule 4).
"""
from __future__ import annotations

import importlib.util
import math
import sys
from functools import lru_cache

import pandas as pd

from imbalance.contract import SCORER, SPIKE_MARGIN
from imbalance.paths import WORK_DIR

from backend.api.repository import Repository
from backend.api.schemas import (DiagnosticScores, Hindsight, HindsightPoint, HorizonScores, OfficialScores,
                                 Performance, Scores, ScoreSet)

OFFICIAL_NOTE = "Organiser's score.py, validation period, spike margin 50 EUR/MWh."
DIAGNOSTIC_NOTE = ("Diagnostic, not an official score. Organiser's formulas over this window, using only prices "
                   "usable at the viewing time. Test-period results are for display only and must not guide "
                   "model choice or tuning.")
STEPS_PER_HOUR = 4


@lru_cache
def _organiser_metrics():
    """The organiser's compute_metrics(), loaded without writing anything into their folder."""
    spec = importlib.util.spec_from_file_location("organiser_score", SCORER)
    module = importlib.util.module_from_spec(spec)
    sys.modules["organiser_score"] = module
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = keep
    return module.compute_metrics


def _number(value) -> float | None:
    value = float(value)
    return None if math.isnan(value) else round(value, 4)


def _scores(metrics: dict) -> dict:
    return {
        "rows": int(metrics["rows_scored_price"]),
        "mae_p50": _number(metrics["mae_p50"]),
        "calibration_pinball_mean": _number(metrics["calibration_pinball_mean"]),
        "coverage_p10_p90": _number(metrics["coverage_p10_p90"]),
        "brier_spike_mean": _number(metrics["brier_spike_mean"]),
        "brier_direction": _number(metrics["brier_direction"]),
        "observed_spike_high_share": _number(metrics.get("observed_spike_high_share", math.nan)),
        "observed_spike_low_share": _number(metrics.get("observed_spike_low_share", math.nan)),
        "forecast_spike_high_share": _number(metrics.get("forecast_spike_high_share", math.nan)),
        "forecast_spike_low_share": _number(metrics.get("forecast_spike_low_share", math.nan)),
    }


def _metrics(rows: pd.DataFrame) -> dict:
    """The organiser's metrics, plus the model's mean spike probabilities over the rows they score for spikes."""
    metrics = _organiser_metrics()(rows, SPIKE_MARGIN)
    spike = rows[rows["imbalance_price"].notna() & rows["spot_price"].notna()]
    metrics["forecast_spike_high_share"] = spike["p_spike_high"].mean()
    metrics["forecast_spike_low_share"] = spike["p_spike_low"].mean()
    return metrics


def _window_scores(forecast: pd.DataFrame, actuals: pd.DataFrame, label: str) -> ScoreSet | None:
    """Scores for forecast rows joined to usable actuals, or None when nothing can be scored."""
    rows = forecast.merge(actuals, on="delivery_start_utc", how="inner")
    if rows.empty or rows["imbalance_price"].notna().sum() == 0:
        return None
    rows = rows.rename(columns={"spot": "spot_price"})
    by_hour = [HorizonScores(horizon_hour=int(hour), **_scores(_metrics(group)))
               for hour, group in rows.groupby((rows["step"] - 1) // STEPS_PER_HOUR + 1, sort=True)]
    model = ",".join(sorted(rows["model"].unique()))
    return ScoreSet(label=label, model=model, overall=Scores(**_scores(_metrics(rows))), by_horizon=by_hour)


def _read_official(model: str, label: str) -> ScoreSet | None:
    folder = WORK_DIR / "scores" / model
    if not (folder / "score_summary.csv").exists() or not (folder / "score_by_horizon.csv").exists():
        return None
    summary = pd.read_csv(folder / "score_summary.csv").iloc[0].to_dict()
    by_hour = [HorizonScores(horizon_hour=int(r["horizon_hour"]), **_scores(r.to_dict()))
               for _, r in pd.read_csv(folder / "score_by_horizon.csv").iterrows()]
    return ScoreSet(label=label, model=model, overall=Scores(**_scores(summary)), by_horizon=by_hour)


def build_hindsight(repo: Repository, as_of: pd.Timestamp, start: pd.Timestamp, end: pd.Timestamp,
                    lead_hours: int) -> Hindsight:
    """Quarter-hours in [start, end) as forecast `lead_hours` ahead. Each hourly forecast gives four of
    them at every lead time, so each quarter-hour appears exactly once. Ends where observed values stop."""
    first_step = (lead_hours - 1) * STEPS_PER_HOUR + 1
    end = repo.observed_end(end)

    def at_lead(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        keep = (frame["forecast_origin_utc"] <= as_of) & frame["step"].between(first_step, first_step + STEPS_PER_HOUR - 1)
        keep &= (frame["delivery_start_utc"] >= start) & (frame["delivery_start_utc"] < end)
        return frame.loc[keep]

    def number(value) -> float | None:
        return None if pd.isna(value) else round(float(value), 2)

    model = at_lead(repo.primary)[["delivery_start_utc", "p10", "p50", "p90", "p_up", "p_down"]]
    rows = model.merge(repo.actuals(as_of, start, end), on="delivery_start_utc", how="left")
    baseline = at_lead(repo.baseline)
    if baseline.empty:
        rows = rows.assign(baseline_p50=float("nan"))
    else:
        rows = rows.merge(baseline[["delivery_start_utc", "p50"]].rename(columns={"p50": "baseline_p50"}),
                          on="delivery_start_utc", how="left")
    points = [HindsightPoint(delivery_start_utc=r.delivery_start_utc, p10=round(r.p10, 2), p50=round(r.p50, 2),
                             p90=round(r.p90, 2), p_up=round(r.p_up, 4), p_down=round(r.p_down, 4),
                             baseline_p50=number(r.baseline_p50),
                             actual=number(r.imbalance_price), spot=number(r.spot))
              for r in rows.sort_values("delivery_start_utc").itertuples(index=False)]
    return Hindsight(as_of_utc=as_of, from_utc=start, to_utc=end, lead_hours=lead_hours, points=points)


def official_scores(repo: Repository) -> OfficialScores | None:
    """Validation scores from score.py. None in mock mode or before the pipeline has run."""
    period = next((p for p in repo.settings.periods if p.name == "validation"), None)
    if period is None:
        return None
    model = _read_official(period.model, "Model")
    if model is None:
        return None
    return OfficialScores(note=OFFICIAL_NOTE, model=model, baseline=_read_official(period.baseline, "Baseline"))


def build_performance(repo: Repository, as_of: pd.Timestamp, start: pd.Timestamp, end: pd.Timestamp) -> Performance:
    actuals = repo.actuals(as_of, start, end)

    def visible(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        keep = (frame["forecast_origin_utc"] <= as_of) & (frame["delivery_start_utc"] >= start) & (frame["delivery_start_utc"] < end)
        return frame[keep]

    return Performance(
        as_of_utc=as_of, from_utc=start, to_utc=end,
        official=official_scores(repo),
        diagnostic=DiagnosticScores(note=DIAGNOSTIC_NOTE,
                                    model=_window_scores(visible(repo.primary), actuals, "Model"),
                                    baseline=_window_scores(visible(repo.baseline), actuals, "Baseline")),
    )

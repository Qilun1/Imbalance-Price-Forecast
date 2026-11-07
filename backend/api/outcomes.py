"""Did a past situation come true? Judged only on prices usable at the viewing time.

The dashboard shows this next to each past situation. It is a diagnostic, not a score: it never replaces
score.py, and test-period outcomes must not guide model choice, tuning or alert thresholds (AGENTS.md
rules 4 and 5).

Only situations that make a claim can be judged. High uncertainty, conflicting signals and stale data
say "be careful", so no price can prove them right or wrong.
"""
from __future__ import annotations

import pandas as pd

from imbalance.contract import SPIKE_MARGIN, STEP

from backend.api.repository import Repository
from backend.api.schemas import Situation

MOVES_AGAINST_REVISION = "The revision moved away from the actual price"
MOVES_WITH_REVISION = "The revision moved towards the actual price"


def _exceptional(rows: pd.DataFrame, side: str) -> pd.Series:
    if side == "high":
        return rows["imbalance_price"] > rows["spot"] + SPIKE_MARGIN
    return rows["imbalance_price"] < rows["spot"] - SPIKE_MARGIN


def _spike(rows: pd.DataFrame, side: str) -> tuple[str, str]:
    hits = int(_exceptional(rows, side).sum())
    if hits:
        return "happened", f"Exceptionally {side} price in {hits} of {len(rows)} quarter-hours"
    return "did_not_happen", f"No exceptionally {side} price in this window"


def _regulation(rows: pd.DataFrame, word: str) -> tuple[str, str]:
    hits = int((rows["direction"] == word).sum())
    status = "happened" if hits * 2 >= len(rows) else "did_not_happen"
    return status, f"{word.capitalize()}-regulation in {hits} of {len(rows)} quarter-hours"


def _either_spike(rows: pd.DataFrame) -> tuple[str, str]:
    hits = int((_exceptional(rows, "high") | _exceptional(rows, "low")).sum())
    if hits:
        return "happened", f"Exceptional price in {hits} of {len(rows)} quarter-hours"
    return "did_not_happen", "No exceptional price in this window"


def _revision(rows: pd.DataFrame, repo: Repository, origin: pd.Timestamp) -> tuple[str, str]:
    previous = repo.previous_forecast(origin)
    if previous is None:
        return "not_applicable", ""
    times = rows.index
    revised = repo.forecast(origin).set_index("delivery_start_utc")["p50"].reindex(times)
    before = previous.set_index("delivery_start_utc")["p50"].reindex(times)
    actual = rows["imbalance_price"]
    if (actual - revised).abs().mean() < (actual - before).abs().mean():
        return "happened", MOVES_WITH_REVISION
    return "did_not_happen", MOVES_AGAINST_REVISION


def _judge(situation: Situation, rows: pd.DataFrame, repo: Repository) -> tuple[str, str]:
    alert = situation.alert
    if alert.kind == "spike_risk":
        return _spike(rows, "high" if "high" in alert.title else "low")
    if alert.kind == "regulation_expected":
        return _regulation(rows, "up" if alert.title.startswith("Up") else "down")
    if alert.kind == "expert_review":
        return _either_spike(rows)
    if alert.kind == "forecast_changed":
        return _revision(rows, repo, pd.Timestamp(situation.first_origin_utc))
    return "not_applicable", ""


def add_outcomes(repo: Repository, situations: list[Situation], as_of: pd.Timestamp) -> list[Situation]:
    """Fill in each situation's outcome from what was usable at `as_of`. Reads the masked rows once."""
    known = repo.actuals(as_of).set_index("delivery_start_utc")
    known = known[known["imbalance_price"].notna()]
    judged = []
    for situation in situations:
        alert = situation.alert
        start, end = pd.Timestamp(alert.window_start_utc), pd.Timestamp(alert.window_end_utc)
        rows = known.loc[start:end - STEP]
        if alert.kind in ("high_uncertainty", "conflicting_signals", "stale_data"):
            status, note = "not_applicable", ""
        elif len(rows) * STEP < end - start:
            status, note = "pending", ""
        else:
            status, note = _judge(situation, rows, repo)
        judged.append(situation.model_copy(update={"outcome": status, "outcome_note": note or None}))
    return judged

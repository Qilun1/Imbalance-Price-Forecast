"""Turns the event classifiers' probabilities at one origin into a persona's notes.

The trader and the plant operator (CHP with electric boilers) see different events and different
"what to check" wording, from the same probabilities (imbalance/events.py). A note fires when its
probability reaches the threshold: the bundle's default (1.5 x the training base rate, capped) or a
user-set value. Changing a threshold changes only `fires`, never the probabilities.

Events with little skill on validation are left out unless asked for, so the views do not cry wolf.
"""
from __future__ import annotations

import pandas as pd

from backend.api.schemas import Note
from imbalance.contract import STEP
from imbalance.events import CHECKS, EVENT_BY_ID, WINDOW_LABELS, WINDOWS

WINDOW_ORDER = {w: i for i, w in enumerate(WINDOWS)}


def parse_thresholds(text: str | None) -> dict[str, float]:
    """"spike_high:0.3,extreme_price:0.2" -> {"spike_high": 0.3, "extreme_price": 0.2}."""
    if not text:
        return {}
    out = {}
    for part in text.split(","):
        event, _, value = part.partition(":")
        event = event.strip()
        if event not in EVENT_BY_ID:
            raise ValueError(f"unknown event {event!r}; known: {', '.join(EVENT_BY_ID)}")
        p = float(value)
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"threshold for {event} must be in [0, 1], not {p}")
        out[event] = p
    return out


def build_notes(probs: pd.DataFrame, persona: str, origin: pd.Timestamp, low_skill: frozenset[str] = frozenset(),
                thresholds: dict[str, float] | None = None, include_low_skill: bool = False) -> list[Note]:
    """Notes for one origin: firing notes first, then soonest window, then the largest lift."""
    thresholds = thresholds or {}
    notes = []
    for row in probs.itertuples(index=False):
        event = EVENT_BY_ID.get(row.event)
        if event is None or persona not in event.personas:
            continue
        weak = row.event in low_skill
        if weak and not include_low_skill:
            continue
        first, last = WINDOWS[row.window]
        threshold = thresholds.get(row.event, float(row.threshold))
        notes.append(Note(
            event=row.event, title=event.title, definition=event.definition, window=row.window,
            window_label=WINDOW_LABELS[row.window],
            window_start_utc=origin + (first - 1) * STEP, window_end_utc=origin + last * STEP,
            probability=round(float(row.p), 4), probability_low=round(float(row.p_lo), 4),
            probability_high=round(float(row.p_hi), 4), base_rate=round(float(row.base_rate), 4),
            lift=round(float(row.lift), 2), threshold=threshold, fires=bool(row.p >= threshold),
            confidence=row.confidence, low_skill=weak,
            drivers=[d for d in str(row.drivers or "").split(";") if d],
            check=CHECKS[(persona, row.event)]))
    return sorted(notes, key=lambda n: (not n.fires, WINDOW_ORDER[n.window], -n.lift))

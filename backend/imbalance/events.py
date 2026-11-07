"""Events worth a note, and their labels: did the event happen in this window after the origin?

The event classifiers (alert_model.py) learn P(event in window | what is known at the origin). This
module defines the events once, for training labels, evaluation and the API alike.

Labels read realised values through Store.truth, which is for targets only. Nothing here is a
feature. A window whose quarters are partly unknown gets a label only when the known quarters already
decide it (the event happened); otherwise the label is NaN and the row is left out of training.

Levels are fixed constants taken from training data before the validation period (deliveries up to
2026-09-06T20:45Z, `tools/training/event_rates.py`), never from validation or test data (AGENTS.md
rule 4). The spike margin is the official one (SPIKE_MARGIN, 50 EUR/MWh) and is not changed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import HORIZON_STEPS, SPIKE_MARGIN

# (first step, last step), inclusive; step 1 starts at the origin.
WINDOWS: dict[str, tuple[int, int]] = {"now": (1, 8), "soon": (9, 20), "later": (21, 40)}
WINDOW_LABELS = {"now": "next 2 h", "soon": "in 2–5 h", "later": "in 5–10 h"}

# Training-period levels (deliveries <= 2026-09-06T20:45Z): see module docstring.
EXTREME_PRICE = 170.0        # EUR/MWh, about P97.5 of the imbalance price
DEEP_NEGATIVE = -10.0        # EUR/MWh, about P5 of the imbalance price
LARGE_UP_MW = 205.0          # P95 of activated mFRR up (MW)
LARGE_DOWN_MW = -405.0       # P5 of activated mFRR down (MW, stored negative)
FORECAST_MISS = 100.0        # EUR/MWh, |imbalance - p50|


@dataclass(frozen=True)
class Event:
    id: str
    title: str
    definition: str
    personas: tuple[str, ...]
    default_threshold: float = 0.5      # probability at which a note fires; tuned on validation later


EVENTS: tuple[Event, ...] = (
    Event("spike_high", "Exceptionally high imbalance price",
          f"at least 2 quarter-hours with imbalance price above spot + {SPIKE_MARGIN:.0f} EUR/MWh",
          ("trader", "operator")),
    Event("spike_low", "Exceptionally low imbalance price",
          f"at least 2 quarter-hours with imbalance price below spot - {SPIKE_MARGIN:.0f} EUR/MWh",
          ("trader", "operator")),
    Event("up_episode", "Sustained up-regulation",
          "at least 4 consecutive quarter-hours with up as the dominating mFRR direction",
          ("trader", "operator")),
    Event("direction_flip", "Regulation direction turns",
          "at least 4 consecutive quarter-hours in the opposite direction to the latest one known at the origin",
          ("trader",)),
    Event("extreme_price", "Extreme imbalance price",
          f"at least 1 quarter-hour with imbalance price above {EXTREME_PRICE:.0f} EUR/MWh",
          ("trader", "operator")),
    Event("deep_negative", "Sustained negative imbalance price",
          f"at least 4 consecutive quarter-hours with imbalance price below {DEEP_NEGATIVE:.0f} EUR/MWh",
          ("operator",)),
    Event("large_up_activation", "Large up-regulation activation",
          f"at least 2 quarter-hours with activated mFRR up above {LARGE_UP_MW:.0f} MW",
          ("operator",)),
    Event("large_down_activation", "Large down-regulation activation",
          f"at least 2 quarter-hours with activated mFRR down above {-LARGE_DOWN_MW:.0f} MW",
          ("operator",)),
    Event("forecast_miss", "Price forecast likely to miss badly",
          f"at least 2 quarter-hours where the imbalance price is more than {FORECAST_MISS:.0f} EUR/MWh "
          "from the P50 forecast", ("trader",)),
)
EVENT_IDS = tuple(e.id for e in EVENTS)
PERSONAS = ("trader", "operator")


def max_run(mask: np.ndarray) -> np.ndarray:
    """Longest run of consecutive True per row of a 2-D boolean array."""
    best = np.zeros(len(mask), dtype=int)
    run = np.zeros(len(mask), dtype=int)
    for j in range(mask.shape[1]):
        run = np.where(mask[:, j], run + 1, 0)
        best = np.maximum(best, run)
    return best


def _count_rule(hit: np.ndarray, known: np.ndarray, need: int) -> np.ndarray:
    """1 if at least `need` quarters hit; 0 if that is impossible even if every unknown quarter hit; else NaN."""
    hits = (hit & known).sum(axis=1)
    possible = hits + (~known).sum(axis=1)
    return np.where(hits >= need, 1.0, np.where(possible < need, 0.0, np.nan))


def _run_rule(hit: np.ndarray, known: np.ndarray, need: int) -> np.ndarray:
    """1 if a run of `need` consecutive hits exists; 0 if none exists even with unknown quarters as hits; else NaN."""
    return np.where(max_run(hit & known) >= need, 1.0, np.where(max_run(hit | ~known) < need, 0.0, np.nan))


def window_labels(real: dict[str, np.ndarray], last_dir: np.ndarray, p50: np.ndarray | None = None) -> pd.DataFrame:
    """Labels for every (origin row, window).

    real: arrays of shape (n_origins, HORIZON_STEPS) with keys imbalance, spot, direction, mfrr_up,
          mfrr_down; NaN where unknown.
    last_dir: latest mFRR direction usable at each origin (feature side, availability-masked).
    p50: the base model's P50 forecast in the same shape; without it forecast_miss is NaN.
    """
    n = len(last_dir)
    rows = []
    for window, (a, b) in WINDOWS.items():
        s = slice(a - 1, b)
        imb, spot, d = real["imbalance"][:, s], real["spot"][:, s], real["direction"][:, s]
        up, down = real["mfrr_up"][:, s], real["mfrr_down"][:, s]
        spread = imb - spot
        k_spread, k_imb, k_dir = ~np.isnan(spread), ~np.isnan(imb), ~np.isnan(d)
        opposite = np.where(last_dir[:, None] == 1, d == -1, d == 1)
        flip_known = k_dir & np.isin(last_dir, (-1, 1))[:, None]
        lab = {
            "spike_high": _count_rule(spread > SPIKE_MARGIN, k_spread, 2),
            "spike_low": _count_rule(spread < -SPIKE_MARGIN, k_spread, 2),
            "up_episode": _run_rule(d == 1, k_dir, 4),
            "direction_flip": _run_rule(opposite, flip_known, 4),
            "extreme_price": _count_rule(imb > EXTREME_PRICE, k_imb, 1),
            "deep_negative": _run_rule(imb < DEEP_NEGATIVE, k_imb, 4),
            "large_up_activation": _count_rule(up > LARGE_UP_MW, ~np.isnan(up), 2),
            "large_down_activation": _count_rule(down < LARGE_DOWN_MW, ~np.isnan(down), 2),
        }
        if p50 is None:
            lab["forecast_miss"] = np.full(n, np.nan)
        else:
            err = np.abs(imb - p50[:, s])
            lab["forecast_miss"] = _count_rule(err > FORECAST_MISS, ~np.isnan(err), 2)
        rows.append(pd.DataFrame({"row": np.arange(n), "window": window, **lab}))
    return pd.concat(rows, ignore_index=True)[["row", "window", *EVENT_IDS]]


def realised(store, origins: pd.DatetimeIndex) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Realised values over each origin's horizon (targets, via Store.truth) and the latest usable
    direction at each origin (via the availability-masked Store.get)."""
    origins = pd.DatetimeIndex(origins).as_unit("ns")
    o_ns = origins.asi8
    d_idx = store.index_of(origins)[:, None] + np.arange(HORIZON_STEPS)[None, :]
    inside = d_idx < len(store.grid)

    def truth(sid: str) -> np.ndarray:
        v = store.truth(sid, d_idx)
        return np.where(inside, v, np.nan)

    real = {"imbalance": truth("fi_imbalance_price"), "spot": truth("fi_spot_price"),
            "direction": truth("fi_mfrr_direction"), "mfrr_up": truth("fi_mfrr_up_activated"),
            "mfrr_down": truth("fi_mfrr_down_activated")}
    last = store.latest_index("fi_mfrr_direction", o_ns)
    last_dir = np.where(last >= 0, store.get("fi_mfrr_direction", np.maximum(last, 0), o_ns), np.nan)
    return real, last_dir


def labels(store, origins: pd.DatetimeIndex, p50: np.ndarray | None = None,
           last_delivery: pd.Timestamp | None = None) -> pd.DataFrame:
    """Long table: forecast_origin_utc, window, one 0/1/NaN column per event.

    last_delivery: quarters after it are treated as unknown, so labels never look past a training
    cutoff (a window crossing the cutoff is labelled only if its earlier quarters already decide it).
    """
    origins = pd.DatetimeIndex(origins).as_unit("ns")
    real, last_dir = realised(store, origins)
    if last_delivery is not None:
        delivery = origins.asi8[:, None] + np.arange(HORIZON_STEPS)[None, :] * pd.Timedelta(minutes=15).value
        after = delivery > pd.Timestamp(last_delivery).value
        real = {k: np.where(after, np.nan, v) for k, v in real.items()}
        if p50 is not None:
            p50 = np.where(after, np.nan, p50)
    out = window_labels(real, last_dir, p50)
    out.insert(0, "forecast_origin_utc", origins[out.pop("row").to_numpy()])
    return out

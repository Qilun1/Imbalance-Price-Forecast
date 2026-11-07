"""How often each event happens per window, and where the fixed levels in events.py come from.

Uses training data before the validation period only: deliveries up to 2026-09-06T20:45Z (AGENTS.md
rule 4). Prints aggregate rates and quantiles; it writes nothing. forecast_miss needs out-of-sample
P50 forecasts and is reported once those exist (alert_train.py).

    uv run python -m tools.training.event_rates
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from imbalance import events
from imbalance.contract import VALIDATION_FIRST_ORIGIN
from imbalance.features import load_store

LAST_DELIVERY = VALIDATION_FIRST_ORIGIN - pd.Timedelta(minutes=15)    # 2026-09-06T20:45Z


def level_check(store) -> pd.DataFrame:
    """Quantiles behind the fixed levels, recomputed on the same period."""
    keep = store.grid <= LAST_DELIVERY
    rows = []
    for name, sid, q, fixed in [("EXTREME_PRICE", "fi_imbalance_price", 97.5, events.EXTREME_PRICE),
                                ("DEEP_NEGATIVE", "fi_imbalance_price", 5, events.DEEP_NEGATIVE),
                                ("LARGE_UP_MW", "fi_mfrr_up_activated", 95, events.LARGE_UP_MW),
                                ("LARGE_DOWN_MW", "fi_mfrr_down_activated", 5, events.LARGE_DOWN_MW)]:
        v = store.val[sid][keep]
        rows.append({"level": name, "quantile": q, "fixed": fixed, "recomputed": float(np.nanpercentile(v, q))})
    return pd.DataFrame(rows)


def rates(store) -> pd.DataFrame:
    first = (store.grid[0] + pd.Timedelta(hours=27)).ceil("h")
    origins = pd.date_range(first, VALIDATION_FIRST_ORIGIN - pd.Timedelta(hours=1), freq="h")
    lab = events.labels(store, origins, last_delivery=LAST_DELIVERY)
    ids = [e for e in events.EVENT_IDS if e != "forecast_miss"]
    rate = lab.groupby("window", sort=False)[ids].mean().T
    known = lab.groupby("window", sort=False)[ids].count().T
    out = rate.round(3)
    out.columns = [f"rate_{c}" for c in out.columns]
    return out.assign(labelled_rows=known.min(axis=1))


def main() -> None:
    store = load_store()
    pd.set_option("display.width", 140)
    print(f"Training period before validation: deliveries up to {LAST_DELIVERY:%Y-%m-%dT%H:%MZ}\n")
    print(level_check(store).round(1).to_string(index=False), "\n")
    print("Share of (origin, window) rows where the event happens:")
    print(rates(store).to_string())


if __name__ == "__main__":
    main()

"""Run the event classifiers for a set of forecast origins and store the result in infer_data.

At each origin: base and challenger forecasts from the saved base models (also at the origin one
hour earlier, for the revision inputs), the classifier inputs (alert_features.build), then the
event probabilities with their interval, base rate, lift, default threshold, drivers and a
confidence tier. Everything is read from availability-masked feature tables; nothing here touches
the submission (forecast_backtest.csv).

Table `event_probs` in backend/infer_data/forecasts.duckdb: one row per (model, origin, window, event).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import alert_features, forecasts
from .alert_model import AlertBundle
from .features import build_table
from .model import Bundle
from .paths import INFER_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS event_probs (
    model VARCHAR NOT NULL,
    forecast_origin_utc TIMESTAMPTZ NOT NULL,
    "window" VARCHAR NOT NULL,
    event VARCHAR NOT NULL,
    p DOUBLE, p_lo DOUBLE, p_hi DOUBLE, base_rate DOUBLE, lift DOUBLE, threshold DOUBLE,
    confidence VARCHAR, drivers VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (model, forecast_origin_utc, "window", event)
);
"""
COLS = ["model", "forecast_origin_utc", "window", "event", "p", "p_lo", "p_hi", "base_rate", "lift", "threshold",
        "confidence", "drivers"]
HOUR = pd.Timedelta(hours=1)

# Confidence tier. Interval widths: about P90 and P98 of alerts-val intervals on validation origins only
# (never test, AGENTS.md rule 4); data age and model disagreement use the rule-based alerts' bars.
WIDTH_MEDIUM = 0.017
WIDTH_LOW = 0.087
STALE_MINUTES = 135.0
CONFLICT_P50_GAP = 45.0


def confidence(width: np.ndarray, data_age_min: np.ndarray, p50_gap: np.ndarray) -> np.ndarray:
    low = (width > WIDTH_LOW) | (np.nan_to_num(data_age_min) >= STALE_MINUTES)
    medium = (width > WIDTH_MEDIUM) | (np.nan_to_num(p50_gap) >= CONFLICT_P50_GAP)
    return np.where(low, "low", np.where(medium, "medium", "high"))


def _forecast(bundle: Bundle, features: pd.DataFrame, origins: pd.DatetimeIndex) -> pd.DataFrame:
    rows = features[features["forecast_origin_utc"].isin(origins)].reset_index(drop=True)
    missing = set(origins) - set(rows["forecast_origin_utc"])
    if missing:
        raise RuntimeError(f"{bundle.name}: no feature rows for {len(missing)} origins, e.g. {sorted(missing)[0]}")
    pred = bundle.predict(rows)
    return pd.concat([rows[["forecast_origin_utc", "delivery_start_utc", "step"]], pred], axis=1)


def base_models_of(alerts: AlertBundle) -> tuple[str, str]:
    """The base and challenger models a bundle was trained to read: "-val" models for the -val bundle,
    so validation notes stay out of sample."""
    suffix = "-val" if alerts.meta.get("variant") == "val" else ""
    return f"{alerts.meta['base_model']}{suffix}", f"{alerts.meta['challenger_model']}{suffix}"


def infer(alert_model: str, origins: pd.DatetimeIndex, base_features: pd.DataFrame | None = None,
          challenger_features: pd.DataFrame | None = None, write: bool = True, path: Path = INFER_DB) -> pd.DataFrame:
    """Event probabilities for every origin.

    The base and challenger models come from the bundle's meta.json, so they always match what the
    classifiers were trained on. Feature tables are built from the store (availability-masked) when not
    given; they must cover the origins and the hour before each (for the revision inputs)."""
    alerts = AlertBundle.load(alert_model)
    base_name, challenger_name = base_models_of(alerts)
    base_bundle, challenger_bundle = Bundle.load(base_name), Bundle.load(challenger_name)
    origins = pd.DatetimeIndex(origins)
    with_prev = origins.union(origins - HOUR)
    if base_features is None:
        base_features = build_table(with_prev, with_targets=False, feature_set=base_bundle.meta["feature_set"])
    if challenger_features is None:
        challenger_features = build_table(origins, with_targets=False,
                                          feature_set=challenger_bundle.meta["feature_set"])
    prev_available = with_prev[with_prev.isin(base_features["forecast_origin_utc"])]
    base = _forecast(base_bundle, base_features, prev_available.union(origins))
    challenger = _forecast(challenger_bundle, challenger_features, origins)
    X = alert_features.build(base_features, base, challenger, origins)
    missing = [c for c in alerts.inputs if c not in X.columns]
    if missing:
        raise RuntimeError(f"{alert_model}: inputs missing at inference, e.g. {missing[:3]}")
    out = alerts.predict(X)
    per_row = X.set_index(["forecast_origin_utc", "window"])[["f_data_age_min", "gap_p50_max"]]
    joined = per_row.reindex(pd.MultiIndex.from_frame(out[["forecast_origin_utc", "window"]]))
    out["confidence"] = confidence((out["p_hi"] - out["p_lo"]).to_numpy(), joined["f_data_age_min"].to_numpy(),
                                   joined["gap_p50_max"].to_numpy())
    out["model"] = alert_model
    out = out[COLS]
    if write:
        write_probs(out, path)
    return out


def write_probs(df: pd.DataFrame, path: Path = INFER_DB) -> int:
    with forecasts.connect(path) as con:
        con.execute(SCHEMA).fetchall()
        con.register("incoming", df[COLS])
        con.execute("DELETE FROM event_probs WHERE model IN (SELECT DISTINCT model FROM incoming) AND "
                    "forecast_origin_utc IN (SELECT DISTINCT forecast_origin_utc FROM incoming)").fetchall()
        con.execute(f"INSERT INTO event_probs ({', '.join(c if c != 'window' else chr(34) + 'window' + chr(34) for c in COLS)}) "
                    "SELECT * FROM incoming").fetchall()
    return len(df)


def read_probs(model: str, origins: pd.DatetimeIndex | None = None, path: Path = INFER_DB) -> pd.DataFrame:
    with forecasts.connect(path, read_only=True) as con:
        exists = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'event_probs'").fetchall()[0][0]
        if not exists:
            return pd.DataFrame(columns=COLS)
        q = 'SELECT model, forecast_origin_utc, "window", event, p, p_lo, p_hi, base_rate, lift, threshold, ' \
            "confidence, drivers FROM event_probs WHERE model = ?"
        if origins is not None:
            con.register("wanted", pd.DataFrame({"o": pd.DatetimeIndex(origins)}))
            q += " AND forecast_origin_utc IN (SELECT o FROM wanted)"
        df = con.execute(q + " ORDER BY forecast_origin_utc", [model]).df()
    df["forecast_origin_utc"] = pd.to_datetime(df["forecast_origin_utc"], utc=True)
    return df

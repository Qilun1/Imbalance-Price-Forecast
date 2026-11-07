"""Inferred forecast sets in backend/infer_data/forecasts.duckdb, and export to the submission CSV.

Table `forecasts`: one row per (model, forecast_origin_utc, step) with every submission column.
Export reads the organiser's template for column order and rows, so the CSV format can never drift.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .contract import FORECAST_COLUMNS, TEMPLATE, submission_columns
from .paths import INFER_DB
from .store import open_duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecasts (
    model VARCHAR NOT NULL,
    forecast_origin_utc TIMESTAMPTZ NOT NULL,
    delivery_start_utc TIMESTAMPTZ NOT NULL,
    step INTEGER NOT NULL,
    p10 DOUBLE, p50 DOUBLE, p90 DOUBLE,
    p_up DOUBLE, p_down DOUBLE, p_none DOUBLE,
    p_spike_high DOUBLE, p_spike_low DOUBLE,
    data_cutoff_utc TIMESTAMPTZ,
    top_drivers VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (model, forecast_origin_utc, step)
);
"""
COLS = ["model", "forecast_origin_utc", "delivery_start_utc", "step", *FORECAST_COLUMNS,
        "data_cutoff_utc", "top_drivers"]


@contextmanager
def connect(path: Path = INFER_DB, read_only: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = open_duckdb(path, read_only)
    try:
        con.execute("SET TimeZone = 'UTC'").fetchall()
        if not read_only:
            for stmt in SCHEMA.split(";"):
                if stmt.strip():
                    con.execute(stmt).fetchall()
        yield con
    finally:
        con.close()


def write(model: str, df: pd.DataFrame, path: Path = INFER_DB) -> int:
    """Replace the forecasts of `model` for the origins in df."""
    df = df.copy()
    df["model"] = model
    df = df[COLS]
    with connect(path) as con:
        con.register("incoming", df)
        con.execute("DELETE FROM forecasts WHERE model = ? AND forecast_origin_utc IN "
                    "(SELECT DISTINCT forecast_origin_utc FROM incoming)", [model]).fetchall()
        con.execute(f"INSERT INTO forecasts ({', '.join(COLS)}) SELECT * FROM incoming").fetchall()
    return len(df)


def read(model: str, origins: pd.DatetimeIndex | None = None, path: Path = INFER_DB) -> pd.DataFrame:
    q = f"SELECT {', '.join(COLS)} FROM forecasts WHERE model = ?"
    params: list = [model]
    with connect(path, read_only=True) as con:
        if origins is not None:
            con.register("wanted", pd.DataFrame({"o": pd.DatetimeIndex(origins)}))
            q += " AND forecast_origin_utc IN (SELECT o FROM wanted)"
        df = con.execute(q + " ORDER BY forecast_origin_utc, step", params).df()
    for c in ("forecast_origin_utc", "delivery_start_utc", "data_cutoff_utc"):
        df[c] = pd.to_datetime(df[c], utc=True)
    return df


def models(path: Path = INFER_DB) -> pd.DataFrame:
    with connect(path, read_only=True) as con:
        return con.execute("SELECT model, count(DISTINCT forecast_origin_utc) AS origins, min(forecast_origin_utc) "
                           "AS first_origin, max(forecast_origin_utc) AS last_origin, max(created_at) AS created "
                           "FROM forecasts GROUP BY model ORDER BY model").df()


def _fmt(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def export_submission(model: str, template: Path, out: Path, path: Path = INFER_DB) -> Path:
    """Write a submission CSV that follows `template` (organiser's) row for row, column for column."""
    tpl = pd.read_csv(template, dtype=str)
    cols = submission_columns()
    assert tpl.columns.tolist() == cols, "template columns differ from the organiser's sample_submission.csv"
    origins = pd.DatetimeIndex(pd.to_datetime(tpl["forecast_origin_utc"].unique(), utc=True))
    fc = read(model, origins, path)
    if fc.empty:
        raise RuntimeError(f"no forecasts for model {model!r} at the template's origins")
    fc["forecast_origin_utc"] = _fmt(fc["forecast_origin_utc"])
    fc["data_cutoff_utc"] = _fmt(fc["data_cutoff_utc"])
    fc["step"] = fc["step"].astype(int)
    tpl["step"] = tpl["step"].astype(int)
    merged = tpl[["forecast_origin_utc", "delivery_start_utc", "step"]].merge(
        fc.drop(columns=["model", "delivery_start_utc"]), on=["forecast_origin_utc", "step"],
        how="left", validate="one_to_one")
    if merged[FORECAST_COLUMNS].isna().any().any():
        n = int(merged["p50"].isna().sum())
        raise RuntimeError(f"{n} template rows have no forecast for model {model!r}")
    # probabilities: 6 decimals, p_down written as the exact complement so the three sum to 1 exactly
    for c in ("p_up", "p_none", "p_spike_high", "p_spike_low"):
        merged[c] = merged[c].round(6)
    merged["p_down"] = (1.0 - merged["p_up"] - merged["p_none"]).round(6)
    over = merged["p_spike_high"] + merged["p_spike_low"] > 1.0
    merged.loc[over, "p_spike_low"] = (1.0 - merged.loc[over, "p_spike_high"]).round(6)
    for c in ("p10", "p50", "p90"):
        merged[c] = merged[c].round(4)
    assert (merged["p10"] <= merged["p50"]).all() and (merged["p50"] <= merged["p90"]).all()
    assert merged[FORECAST_COLUMNS].notna().all().all() and np.isfinite(merged[FORECAST_COLUMNS].to_numpy()).all()
    out.parent.mkdir(parents=True, exist_ok=True)
    merged[cols].to_csv(out, index=False, float_format="%.6f", lineterminator="\n", encoding="utf-8")
    return out


__all__ = ["write", "read", "models", "export_submission", "TEMPLATE"]

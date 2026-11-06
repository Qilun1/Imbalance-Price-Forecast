"""DuckDB store for all source data (static_data/static.duckdb).

Tables
- observations   : one value per (series_id, timestamp_utc), in the organiser's long format.
- forecast_runs  : vintaged forecasts, several runs per valid time (NWP etc.).
- series_catalog : what each series is, where it comes from, its availability rule and licence.
- ingest_log     : what was loaded when.

Rules (see AGENTS.md): organiser rows are inserted unchanged and never overwritten
(INSERT ... ON CONFLICT DO NOTHING); every row has first_usable_origin_utc. All times are UTC.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

from .paths import STATIC_DB

LONG_COLUMNS = ["series_id", "source", "dataset_id", "timestamp_utc", "value", "unit",
                "first_usable_origin_utc"]
RUN_COLUMNS = ["series_id", "source", "location_id", "run_init_utc", "valid_time_utc", "member",
               "value", "unit", "first_usable_origin_utc"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    series_id VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    dataset_id VARCHAR,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    value DOUBLE,
    unit VARCHAR,
    first_usable_origin_utc TIMESTAMPTZ NOT NULL,
    ingest_batch VARCHAR,
    PRIMARY KEY (series_id, timestamp_utc)
);
CREATE TABLE IF NOT EXISTS forecast_runs (
    series_id VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    location_id VARCHAR NOT NULL,
    run_init_utc TIMESTAMPTZ NOT NULL,
    valid_time_utc TIMESTAMPTZ NOT NULL,
    member INTEGER NOT NULL,
    value DOUBLE,
    unit VARCHAR,
    first_usable_origin_utc TIMESTAMPTZ NOT NULL,
    ingest_batch VARCHAR,
    PRIMARY KEY (series_id, location_id, run_init_utc, valid_time_utc, member)
);
CREATE TABLE IF NOT EXISTS series_catalog (
    series_id VARCHAR PRIMARY KEY,
    source VARCHAR,
    dataset_id VARCHAR,
    unit VARCHAR,
    kind VARCHAR,                 -- observation | forecast_run | calendar
    availability_rule VARCHAR,
    licence VARCHAR,
    description VARCHAR
);
CREATE TABLE IF NOT EXISTS ingest_log (
    ingest_batch VARCHAR,
    source VARCHAR,
    table_name VARCHAR,
    rows_offered BIGINT,
    rows_inserted BIGINT,
    ingested_at TIMESTAMPTZ DEFAULT now()
);
"""


@contextmanager
def connect(path: Path = STATIC_DB, read_only: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only and path.exists())
    try:
        con.execute("SET TimeZone = 'UTC'").fetchall()
        if not read_only:
            for stmt in SCHEMA.split(";"):
                if stmt.strip():
                    con.execute(stmt).fetchall()
        yield con
    finally:
        con.close()


def _utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True)


def insert_observations(df: pd.DataFrame, batch: str, path: Path = STATIC_DB) -> int:
    """Insert long-format rows; existing (series_id, timestamp_utc) rows are kept as they are."""
    missing = set(LONG_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    df = df[LONG_COLUMNS].copy()
    df["timestamp_utc"] = _utc(df["timestamp_utc"])
    df["first_usable_origin_utc"] = _utc(df["first_usable_origin_utc"])
    if df["first_usable_origin_utc"].isna().any():
        raise ValueError("every row needs first_usable_origin_utc")
    if df.duplicated(["series_id", "timestamp_utc"]).any():
        raise ValueError("duplicate (series_id, timestamp_utc) in input")
    df["dataset_id"] = df["dataset_id"].astype("string")
    df["ingest_batch"] = batch
    with connect(path) as con:
        before = con.execute("SELECT count(*) FROM observations").fetchall()[0][0]
        con.register("incoming", df)
        con.execute("INSERT INTO observations SELECT * FROM incoming ON CONFLICT DO NOTHING").fetchall()
        after = con.execute("SELECT count(*) FROM observations").fetchall()[0][0]
        con.execute("INSERT INTO ingest_log (ingest_batch, source, table_name, rows_offered, rows_inserted) "
                    "VALUES (?, ?, 'observations', ?, ?)",
                    [batch, ",".join(sorted(df["source"].unique())), len(df), after - before]).fetchall()
    return after - before


def insert_forecast_runs(df: pd.DataFrame, batch: str, path: Path = STATIC_DB) -> int:
    missing = set(RUN_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    df = df[RUN_COLUMNS].copy()
    for c in ("run_init_utc", "valid_time_utc", "first_usable_origin_utc"):
        df[c] = _utc(df[c])
    if (df["first_usable_origin_utc"] <= df["run_init_utc"]).any():
        raise ValueError("a forecast run cannot be usable at or before its init time")
    df["ingest_batch"] = batch
    with connect(path) as con:
        before = con.execute("SELECT count(*) FROM forecast_runs").fetchall()[0][0]
        con.register("incoming", df)
        con.execute("INSERT INTO forecast_runs SELECT * FROM incoming ON CONFLICT DO NOTHING").fetchall()
        after = con.execute("SELECT count(*) FROM forecast_runs").fetchall()[0][0]
        con.execute("INSERT INTO ingest_log (ingest_batch, source, table_name, rows_offered, rows_inserted) "
                    "VALUES (?, ?, 'forecast_runs', ?, ?)",
                    [batch, ",".join(sorted(df["source"].unique())), len(df), after - before]).fetchall()
    return after - before


def upsert_catalog(df: pd.DataFrame, path: Path = STATIC_DB) -> None:
    cols = ["series_id", "source", "dataset_id", "unit", "kind", "availability_rule", "licence", "description"]
    df = df[cols].copy()
    with connect(path) as con:
        con.register("incoming", df)
        con.execute("INSERT OR REPLACE INTO series_catalog SELECT * FROM incoming").fetchall()


def load_observations(series: list[str] | None = None, path: Path = STATIC_DB) -> pd.DataFrame:
    """Long-format rows (organiser schema) with UTC timestamps."""
    q = f"SELECT {', '.join(LONG_COLUMNS)} FROM observations"
    params: list = []
    if series:
        q += f" WHERE series_id IN ({', '.join('?' * len(series))})"
        params = list(series)
    with connect(path, read_only=True) as con:
        df = con.execute(q + " ORDER BY series_id, timestamp_utc", params).df()
    for c in ("timestamp_utc", "first_usable_origin_utc"):
        df[c] = pd.to_datetime(df[c], utc=True)
    return df


def load_forecast_runs(series: list[str] | None = None, path: Path = STATIC_DB) -> pd.DataFrame:
    q = f"SELECT {', '.join(RUN_COLUMNS)} FROM forecast_runs"
    params: list = []
    if series:
        q += f" WHERE series_id IN ({', '.join('?' * len(series))})"
        params = list(series)
    with connect(path, read_only=True) as con:
        df = con.execute(q, params).df()
    for c in ("run_init_utc", "valid_time_utc", "first_usable_origin_utc"):
        df[c] = pd.to_datetime(df[c], utc=True)
    return df


def catalog(path: Path = STATIC_DB) -> pd.DataFrame:
    with connect(path, read_only=True) as con:
        return con.execute("SELECT * FROM series_catalog ORDER BY source, series_id").df()


def summary(path: Path = STATIC_DB) -> pd.DataFrame:
    with connect(path, read_only=True) as con:
        return con.execute("""
            SELECT series_id, source, count(*) AS rows, min(timestamp_utc) AS first, max(timestamp_utc) AS last
            FROM observations GROUP BY 1, 2
            UNION ALL
            SELECT series_id, source, count(*), min(valid_time_utc), max(valid_time_utc)
            FROM forecast_runs GROUP BY 1, 2
            ORDER BY 2, 1""").df()

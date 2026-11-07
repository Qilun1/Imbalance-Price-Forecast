"""Invented demo data for the API and dashboard.

Nothing here is read from, derived from or calibrated on the organiser's files. Every number comes
from the seeded generator below, so the result holds no licensed data and is safe to show. The rows
use the same tables as real data (`forecasts`, `observations`), so the API has one code path.

The week crosses the daylight saving change of 25 Oct and scripts one of each situation the dashboard
has to surface, listed in SCENARIOS. Output: backend/infer_data/mock_forecasts.duckdb (gitignored).

Run from the repo root:  uv run python -m backend.api.mock
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from imbalance import forecasts, store
from imbalance.contract import DIRECTION_SERIES, FORECAST_COLUMNS, HORIZON_STEPS, SPOT_SERIES, STEP, TARGET_SERIES

from backend.api.settings import MOCK_BASELINE, MOCK_CHALLENGER, MOCK_DB, MOCK_MODEL, MOCK_NOTES

SEED = 20261107
DISPLAY_TZ = "Europe/Helsinki"
FIRST_ORIGIN = pd.Timestamp("2026-10-21T21:00:00Z")   # 22 Oct 00:00 Helsinki
N_ORIGINS = 168                                       # one week of hourly forecasts
HISTORY = pd.Timedelta(days=3)                        # actuals before the first forecast
LAST_KNOWN_LAG = 5                                    # newest usable quarter-hour starts 75 min before the origin
NORMAL_DRIVERS = ["cons_fc", "wind_fc", "resid_load_fc", "solar_fc", "spot_vs_horizon_mean", "dir_mean4",
                  "spread_mean4", "wind_fc_change_vs_lag", "hour_local", "se1_flow_last"]


@dataclass(frozen=True)
class Scenario:
    """A scripted situation: `as_of` is a forecast time at which it is visible in the dashboard."""
    name: str
    as_of: pd.Timestamp
    delivery_from: pd.Timestamp
    delivery_to: pd.Timestamp
    drivers: str


def _ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text)


SCENARIOS = (
    Scenario("spike_risk_rising", _ts("2026-10-23T07:00:00Z"), _ts("2026-10-23T13:00:00Z"), _ts("2026-10-23T15:00:00Z"),
             "wind_fc_change_vs_lag;cons_fc;se1_flow_last"),
    Scenario("direction_flip", _ts("2026-10-24T10:00:00Z"), _ts("2026-10-24T17:00:00Z"), _ts("2026-10-24T20:00:00Z"),
             "dir_mean4;wind_fc;resid_load_fc"),
    Scenario("large_revision", _ts("2026-10-25T03:00:00Z"), _ts("2026-10-25T07:00:00Z"), _ts("2026-10-25T10:00:00Z"),
             "wind_fc_change_vs_lag;resid_load_fc;spread_mean4"),
    Scenario("wide_uncertainty", _ts("2026-10-26T05:00:00Z"), _ts("2026-10-26T05:00:00Z"), _ts("2026-10-26T09:00:00Z"),
             "spread_std16;cons_err_mean4;wind_fc"),
    Scenario("stale_data", _ts("2026-10-27T10:00:00Z"), _ts("2026-10-27T10:00:00Z"), _ts("2026-10-27T20:00:00Z"),
             "cons_fc;wind_fc;hour_local"),
    Scenario("conflicting_signals", _ts("2026-10-27T20:00:00Z"), _ts("2026-10-28T03:00:00Z"), _ts("2026-10-28T05:00:00Z"),
             "dir_mean4;spread_max16;cons_fc"),
)
_BY_NAME = {s.name: s for s in SCENARIOS}


def _expit(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _grid() -> pd.DatetimeIndex:
    last_delivery = FIRST_ORIGIN + (N_ORIGINS - 1) * pd.Timedelta(hours=1) + (HORIZON_STEPS - 1) * STEP
    return pd.date_range(FIRST_ORIGIN - HISTORY, last_delivery, freq=STEP)


def _actual_series(grid: pd.DatetimeIndex, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(level, price, direction) per quarter-hour. `level` is an invented daily shape and doubles as
    the mock's spot price, so spike risk and direction relate to it the way they do to the real one."""
    local = grid.tz_convert("Europe/Helsinki")
    hour = np.asarray(local.hour + local.minute / 60.0)
    level = 24.0 + 15.0 * np.sin(2 * np.pi * (hour - 6.0) / 24.0)
    direction = np.empty(len(grid))
    state = -1.0
    for i in range(len(grid)):
        if rng.random() < 0.10:
            state = -state
        direction[i] = 0.0 if rng.random() < 0.004 else state
    size = rng.gamma(2.0, 13.0, len(grid))
    price = level + direction * size
    for name, extra in (("spike_risk_rising", 130.0), ("large_revision", 55.0)):
        s = _BY_NAME[name]
        hit = (grid >= s.delivery_from) & (grid < s.delivery_to)
        price[hit] += extra
        direction[hit] = 1.0
    flip = _BY_NAME["direction_flip"]
    hit = (grid >= flip.delivery_from) & (grid < flip.delivery_to)
    price[hit] = level[hit] + np.abs(price[hit] - level[hit])
    direction[hit] = 1.0
    return level, price, direction


def _model_rows(grid: pd.DatetimeIndex, level: np.ndarray, price: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    origins = pd.date_range(FIRST_ORIGIN, periods=N_ORIGINS, freq="h")
    steps = np.arange(1, HORIZON_STEPS + 1)
    o_idx = np.asarray(grid.get_indexer(origins))
    d_idx = o_idx[:, None] + steps[None, :] - 1
    delivery = grid[d_idx.ravel()].to_numpy(dtype="datetime64[ns]").reshape(d_idx.shape)
    origin_m = np.repeat(origins.to_numpy(dtype="datetime64[ns]")[:, None], HORIZON_STEPS, axis=1)

    def when(origin_from: str | None, origin_to: str | None, scenario: str) -> np.ndarray:
        s = _BY_NAME[scenario]
        mask = (delivery >= s.delivery_from.to_datetime64()) & (delivery < s.delivery_to.to_datetime64())
        if origin_from:
            mask &= origin_m >= _ts(origin_from).to_datetime64()
        if origin_to:
            mask &= origin_m <= _ts(origin_to).to_datetime64()
        return mask

    smooth = pd.Series(price - level).rolling(8, center=True, min_periods=1).mean().to_numpy()
    skill = np.exp(-steps / 28.0)[None, :]
    p50 = level[d_idx] + skill * smooth[d_idx] + rng.normal(0.0, 2.0, d_idx.shape)
    below = 18.0 + 1.1 * steps[None, :] * np.ones(d_idx.shape)
    above = 30.0 + 1.6 * steps[None, :] * np.ones(d_idx.shape)
    excess = p50 - level[d_idx]
    p_up = np.clip(_expit(excess / 18.0 - 0.6), 0.05, 0.95)
    high = 0.02 + 0.20 * _expit((excess - 50.0) / 18.0)
    low = 0.02 + 0.20 * _expit((-excess - 40.0) / 18.0)
    combos = np.array([";".join(rng.choice(NORMAL_DRIVERS, 3, replace=False)) for _ in range(40)], dtype=object)
    drivers = rng.choice(combos, d_idx.shape)
    cutoff = np.broadcast_to((origins - LAST_KNOWN_LAG * STEP).to_numpy(dtype="datetime64[ns]")[:, None], d_idx.shape).copy()

    # the scripted situations, in the order of SCENARIOS
    s = "spike_risk_rising"
    high[when("2026-10-23T07:00:00Z", None, s)] += 0.30
    late = when("2026-10-23T09:00:00Z", None, s)
    high[late] += 0.20
    p50[late] += 60.0
    above[late] *= 1.8
    drivers[when("2026-10-23T07:00:00Z", None, s)] = _BY_NAME[s].drivers

    s = "direction_flip"
    p_up[when(None, "2026-10-24T09:00:00Z", s)] = 0.22
    flipped = when("2026-10-24T10:00:00Z", None, s)
    p_up[flipped] = 0.88
    drivers[flipped] = _BY_NAME[s].drivers

    s = "large_revision"
    revised = when("2026-10-25T03:00:00Z", None, s)
    p50[revised] += 45.0
    drivers[revised] = _BY_NAME[s].drivers

    s = "wide_uncertainty"
    wide = when("2026-10-26T05:00:00Z", "2026-10-26T07:00:00Z", s)
    below[wide] *= 3.2
    above[wide] *= 3.2
    drivers[wide] = _BY_NAME[s].drivers

    s = "conflicting_signals"
    conflict = when("2026-10-27T20:00:00Z", None, s)
    p_up[conflict] = 0.15
    high[conflict] = 0.42
    drivers[conflict] = _BY_NAME[s].drivers

    stale = (origin_m >= _ts("2026-10-27T09:00:00Z").to_datetime64()) & (origin_m <= _ts("2026-10-27T11:00:00Z").to_datetime64())
    cutoff[stale] = cutoff[stale] - np.timedelta64(3, "h")

    p_none = 0.003
    p_up = np.clip(p_up, 0.0, 1.0 - p_none)
    high, low = np.clip(high, 0.0, 0.95), np.clip(low, 0.0, 0.04)
    return pd.DataFrame({
        "forecast_origin_utc": pd.to_datetime(origin_m.ravel(), utc=True),
        "delivery_start_utc": pd.to_datetime(delivery.ravel(), utc=True),
        "step": np.tile(steps, N_ORIGINS),
        "p10": (p50 - below).ravel(), "p50": p50.ravel(), "p90": (p50 + above).ravel(),
        "p_up": p_up.ravel(), "p_down": (1.0 - p_up - p_none).ravel(), "p_none": p_none,
        "p_spike_high": high.ravel(), "p_spike_low": low.ravel(),
        "data_cutoff_utc": pd.to_datetime(cutoff.ravel(), utc=True),
        "top_drivers": drivers.ravel(),
    })


def _challenger_rows(model: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """A second model on different input data: close to the main one, apart from the scripted conflict,
    where it sees up-regulation and no high-price risk while the main model sees the opposite."""
    out = model.copy()
    shift = rng.normal(0.0, 3.0, len(out))
    for column in ("p10", "p50", "p90"):
        out[column] += shift
    p_none = out["p_none"].to_numpy()
    p_up = np.clip(out["p_up"].to_numpy() + rng.normal(0.0, 0.03, len(out)), 0.0, 1.0 - p_none)
    high = out["p_spike_high"].to_numpy().copy()
    s = _BY_NAME["conflicting_signals"]
    conflict = ((out["forecast_origin_utc"] >= s.as_of) & (out["delivery_start_utc"] >= s.delivery_from)
                & (out["delivery_start_utc"] < s.delivery_to)).to_numpy()
    p_up[conflict] = 0.70
    high[conflict] = 0.05
    out["p_up"], out["p_down"], out["p_spike_high"] = p_up, 1.0 - p_up - p_none, high
    return out


def _baseline_rows(grid: pd.DatetimeIndex, price: np.ndarray) -> pd.DataFrame:
    """A persistence reference in the spirit of the organiser's baseline, on invented prices."""
    origins = pd.date_range(FIRST_ORIGIN, periods=N_ORIGINS, freq="h")
    steps = np.arange(1, HORIZON_STEPS + 1)
    last_known = price[np.asarray(grid.get_indexer(origins)) - LAST_KNOWN_LAG]
    rep = np.repeat(np.arange(N_ORIGINS), HORIZON_STEPS)
    step_all = np.tile(steps, N_ORIGINS)
    p50 = last_known[rep]
    return pd.DataFrame({
        "forecast_origin_utc": origins[rep],
        "delivery_start_utc": origins[rep] + pd.to_timedelta((step_all - 1) * 15, unit="min"),
        "step": step_all,
        "p10": p50 - (30.0 + step_all), "p50": p50, "p90": p50 + (30.0 + step_all),
        "p_up": 0.35, "p_down": 0.645, "p_none": 0.005, "p_spike_high": 0.08, "p_spike_low": 0.06,
        "data_cutoff_utc": origins[rep] - LAST_KNOWN_LAG * STEP,
        "top_drivers": "last_imbalance_price",
    })


def _spot_usable(grid: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Day-ahead prices come out at 14:00 Helsinki time on the day before delivery."""
    delivery_day = grid.tz_convert(DISPLAY_TZ).tz_localize(None).normalize()
    return (delivery_day - pd.Timedelta(days=1) + pd.Timedelta(hours=14)).tz_localize(DISPLAY_TZ).tz_convert("UTC")


def _observation_rows(grid: pd.DatetimeIndex, price: np.ndarray, direction: np.ndarray, level: np.ndarray) -> pd.DataFrame:
    usable = (grid + STEP + pd.Timedelta(minutes=60)).ceil("h")     # same shape of delay as the package
    def series(series_id: str, values: np.ndarray, unit: str, first_usable: pd.DatetimeIndex) -> pd.DataFrame:
        return pd.DataFrame({"series_id": series_id, "source": "mock", "dataset_id": "", "timestamp_utc": grid,
                             "value": values, "unit": unit, "first_usable_origin_utc": first_usable})
    return pd.concat([series(TARGET_SERIES, price, "EUR/MWh", usable), series(DIRECTION_SERIES, direction, "-1/0/1", usable),
                      series(SPOT_SERIES, level, "EUR/MWh", _spot_usable(grid))], ignore_index=True)


def check_rows(df: pd.DataFrame) -> None:
    """The organiser's submission rules (README section 5.1), so mock rows behave like real ones."""
    assert not df[FORECAST_COLUMNS].isna().any().any(), "empty forecast values"
    assert (df["p10"] <= df["p50"]).all() and (df["p50"] <= df["p90"]).all(), "quantiles out of order"
    assert df[["p_up", "p_down", "p_none", "p_spike_high", "p_spike_low"]].stack().between(0.0, 1.0).all(), "probability range"
    assert (df["p_up"] + df["p_down"] + df["p_none"] - 1.0).abs().max() < 1e-9, "direction sum"
    assert (df["p_spike_high"] + df["p_spike_low"]).max() <= 1.0, "spike sum"
    assert (df["data_cutoff_utc"] <= df["forecast_origin_utc"]).all(), "data cutoff after origin"


MOCK_BASE_RATES = {"spike_high": 0.18, "spike_low": 0.15, "up_episode": 0.40, "direction_flip": 0.40,
                   "extreme_price": 0.10, "deep_negative": 0.05, "large_up_activation": 0.13,
                   "large_down_activation": 0.12, "forecast_miss": 0.08}
MOCK_NOTE_DRIVERS = ["Price forecast", "Wind", "Recent balancing", "Spot price shape", "Cross-border flows",
                     "Change since the previous forecast"]


def _note_rows(model: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Invented event probabilities that follow the mock forecast, in the event_probs table's shape."""
    from imbalance.alert_inference import COLS
    from imbalance.events import EVENT_IDS, WINDOWS
    df = model.copy()
    df["window"] = pd.cut(df["step"], [0, *[b for _, b in WINDOWS.values()]], labels=list(WINDOWS)).astype(str)
    g = df.groupby(["forecast_origin_utc", "window"], sort=False)
    agg = g.agg(hi=("p_spike_high", "max"), lo=("p_spike_low", "max"), up=("p_up", "mean"),
                width=("p90", "max")).reset_index()
    agg["width"] = agg["width"] - g["p10"].min().to_numpy()
    signal = {"spike_high": agg["hi"], "spike_low": agg["lo"], "up_episode": agg["up"], "direction_flip": agg["up"],
              "extreme_price": agg["hi"] * 0.6, "deep_negative": agg["lo"] * 0.4, "large_up_activation": agg["up"] * 0.4,
              "large_down_activation": (1 - agg["up"]) * 0.3, "forecast_miss": np.clip(agg["width"] / 400, 0, 1)}
    frames = []
    for event in EVENT_IDS:
        p = np.clip(signal[event].to_numpy(float) + rng.normal(0, 0.03, len(agg)), 0.005, 0.95)
        half = rng.uniform(0.001, 0.03, len(agg))
        base = MOCK_BASE_RATES[event]
        frames.append(pd.DataFrame({
            "model": MOCK_NOTES, "forecast_origin_utc": agg["forecast_origin_utc"], "window": agg["window"],
            "event": event, "p": p, "p_lo": np.clip(p - half, 0, 1), "p_hi": np.clip(p + half, 0, 1),
            "base_rate": base, "lift": p / base, "threshold": min(0.6, 1.5 * base),
            "confidence": np.where(half > 0.025, "low", np.where(half > 0.015, "medium", "high")),
            "drivers": [";".join(rng.choice(MOCK_NOTE_DRIVERS, 2, replace=False)) for _ in range(len(agg))]}))
    return pd.concat(frames, ignore_index=True)[COLS]


def generate(path: Path = MOCK_DB) -> Path:
    """Rebuild the mock database from scratch. Same seed, same bytes of data."""
    rng = np.random.default_rng(SEED)
    grid = _grid()
    level, price, direction = _actual_series(grid, rng)
    model = _model_rows(grid, level, price, rng)
    baseline = _baseline_rows(grid, price)
    challenger = _challenger_rows(model, rng)       # drawn after the model, so the main model's rows do not change
    notes = _note_rows(model, rng)                  # drawn last, for the same reason
    for rows in (model, baseline, challenger):
        check_rows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    forecasts.write(MOCK_MODEL, model, path)
    forecasts.write(MOCK_BASELINE, baseline, path)
    store.insert_observations(_observation_rows(grid, price, direction, level), "mock", path)
    forecasts.write(MOCK_CHALLENGER, challenger, path)
    from imbalance.alert_inference import write_probs
    write_probs(notes, path)
    return path


if __name__ == "__main__":
    out = generate()
    print(f"mock data: {N_ORIGINS} forecast times x {HORIZON_STEPS} steps -> {out}")

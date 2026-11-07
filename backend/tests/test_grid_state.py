"""v9 grid-state features on a synthetic store: availability (15 min rule, full-hour rounding) and no
look-ahead (values after the origin's cutoff cannot change the features)."""
import numpy as np
import pandas as pd

from imbalance.features import Store, add_grid_state

T0 = pd.Timestamp("2026-08-01T00:00:00Z")
GRID = pd.date_range(T0, periods=4 * 24, freq="15min")
RT = ["fi_surplus_deficit_rt", "fi_frequency_rt", "fi_net_import_rt", "fi_eboiler_rt",
      "fi_bess_discharge_rt", "fi_bess_charge_rt", "fi_wind_production_rt", "fi_consumption_rt"]


def long(values: dict) -> pd.DataFrame:
    parts = []
    for sid in RT:
        fu = (GRID + pd.Timedelta(minutes=15 + 15)).ceil("h")     # end of quarter-hour + 15 min, next full hour
        parts.append(pd.DataFrame({"series_id": sid, "timestamp_utc": GRID, "value": values.get(sid, 0.0),
                                   "first_usable_origin_utc": fu}))
    for sid in ("fi_wind_fc_da", "fi_consumption_fc_da"):        # day-ahead: usable from the start
        parts.append(pd.DataFrame({"series_id": sid, "timestamp_utc": GRID, "value": 100.0,
                                   "first_usable_origin_utc": T0}))
    return pd.concat(parts, ignore_index=True)


def rows(origin: pd.Timestamp) -> pd.DataFrame:
    steps = np.arange(1, 5)
    return pd.DataFrame({"forecast_origin_utc": origin, "step": steps,
                         "delivery_start_utc": origin + pd.to_timedelta(15 * (steps - 1), "min"),
                         "data_cutoff_utc": origin - pd.Timedelta(hours=1)})


def test_latest_usable_quarter_hour_and_values():
    surplus = np.arange(len(GRID), dtype=float)                  # value = grid index
    st = Store(long({"fi_surplus_deficit_rt": surplus, "fi_frequency_rt": 50.01,
                     "fi_bess_discharge_rt": 30.0, "fi_bess_charge_rt": 10.0, "fi_wind_production_rt": 160.0}))
    o = T0 + pd.Timedelta(hours=10)
    out = add_grid_state(rows(o), st)
    last = st.index_of([o - pd.Timedelta(minutes=30)])[0]         # quarter-hour 09:30-09:45 ends 15 min before
    assert out["grid_surplus_last"].iloc[0] == last
    assert out["grid_surplus_trend_1h"].iloc[0] == 3.0
    assert np.isclose(out["grid_freq_dev_last"].iloc[0], 10.0)
    assert out["grid_bess_net_last"].iloc[0] == 20.0
    assert out["grid_wind_err_last"].iloc[0] == 60.0
    assert out["grid_obs_lead_h"].iloc[0] == 0.5                  # delivery 10:00 vs observed 09:30
    assert (out["data_cutoff_utc"] == o - pd.Timedelta(minutes=30)).all()


def test_no_look_ahead():
    o = T0 + pd.Timedelta(hours=10)
    a = add_grid_state(rows(o), Store(long({"fi_surplus_deficit_rt": 1.0})))
    later = np.where(GRID >= o - pd.Timedelta(minutes=15), 999.0, 1.0)   # change only rows not yet usable
    b = add_grid_state(rows(o), Store(long({"fi_surplus_deficit_rt": later})))
    cols = [c for c in a.columns if c.startswith("grid_")]
    pd.testing.assert_frame_equal(a[cols], b[cols])

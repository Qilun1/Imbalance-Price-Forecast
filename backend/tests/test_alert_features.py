"""Event-classifier inputs on a synthetic forecast: window aggregation, revision and challenger gap."""
import numpy as np
import pandas as pd

from imbalance import alert_features
from imbalance.contract import HORIZON_STEPS

H = HORIZON_STEPS
O1 = pd.Timestamp("2026-08-01T10:00:00Z")
O0 = O1 - pd.Timedelta(hours=1)


def forecast(origin, p50=50.0, spike=0.1, up=0.3):
    steps = np.arange(1, H + 1)
    return pd.DataFrame({"forecast_origin_utc": origin, "step": steps,
                         "delivery_start_utc": origin + pd.to_timedelta((steps - 1) * 15, unit="min"),
                         "p10": p50 - 20.0, "p50": p50, "p90": p50 + 30.0, "p_up": up,
                         "p_spike_high": spike, "p_spike_low": 0.05})


def features(origin):
    steps = np.arange(1, H + 1)
    return pd.DataFrame({"forecast_origin_utc": origin, "delivery_start_utc": origin + pd.to_timedelta((steps - 1) * 15, unit="min"),
                         "step": steps, "spot": 40.0 + steps, "imb_last": 33.0, "data_cutoff_utc": origin})


def test_one_row_per_window_and_aggregates():
    cur = forecast(O1)
    cur.loc[cur["step"] == 3, "p_spike_high"] = 0.6
    out = alert_features.build(features(O1), cur, origins=pd.DatetimeIndex([O1])).set_index("window")
    assert list(out.index) == ["now", "soon", "later"]
    assert out.loc["now", "b_max_p_spike_high"] == 0.6 and out.loc["soon", "b_max_p_spike_high"] == 0.1
    assert out.loc["now", "fmax_spot"] == 48.0 and out.loc["later", "fmin_spot"] == 61.0
    assert out.loc["now", "f_imb_last"] == 33.0                      # origin-level value carried as is
    expected = 1 - (1 - 0.6) * (1 - 0.1) ** 7
    assert np.isclose(out.loc["now", "b_union_spike_high"], expected)
    assert out[["rev_p50_mean", "gap_p50_max"]].isna().all().all()  # no earlier forecast, no challenger


def test_revision_compares_the_same_delivery_quarters():
    prev, cur = forecast(O0, p50=50.0), forecast(O1, p50=80.0)
    out = alert_features.build(features(O1), pd.concat([prev, cur]), origins=pd.DatetimeIndex([O1])).set_index("window")
    # The previous forecast covers deliveries up to O0 + 39 quarters = O1 + 35 quarters.
    assert out.loc["now", "rev_p50_mean"] == 30.0 and out.loc["later", "rev_p50_max"] == 30.0
    assert len(out) == 3                                             # previous origin's rows are not output


def test_challenger_gap():
    out = alert_features.build(features(O1), forecast(O1, up=0.3), forecast(O1, p50=20.0, up=0.9),
                               origins=pd.DatetimeIndex([O1])).set_index("window")
    assert np.allclose(out["gap_p50_max"], 30.0) and np.allclose(out["gap_p_up_max"], 0.6)

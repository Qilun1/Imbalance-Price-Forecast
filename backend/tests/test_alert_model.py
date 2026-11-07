"""Event classifier mechanics on synthetic data: calibration interval, folds, drivers, save/load."""
import numpy as np
import pandas as pd
import pytest

from imbalance import alert_model, events
from imbalance.alert_model import AlertBundle, VennAbers, driver_family, time_folds


def synthetic(n_origins: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    origins = pd.date_range("2026-07-01T00:00:00Z", periods=n_origins, freq="h")
    rows = []
    for i, w in enumerate(events.WINDOWS):
        signal = rng.normal(size=n_origins)
        p = 1 / (1 + np.exp(-(2 * signal - 1.5 + 0.3 * i)))
        y = (rng.random(n_origins) < p).astype(float)
        frame = pd.DataFrame({"forecast_origin_utc": origins, "window": w, "window_idx": float(i),
                              "f_wind_fc": signal, "b_union_spike_high": p, "noise": rng.normal(size=n_origins)})
        for rule_input in {c for cols in alert_model.RULE_INPUTS.values() for c in cols}:
            frame[rule_input] = frame.get(rule_input, signal)
        for e in events.EVENT_IDS:
            frame[e] = y
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def test_venn_abers_interval_is_ordered_and_calibrated():
    rng = np.random.default_rng(1)
    s = rng.random(4000)
    y = (rng.random(4000) < s).astype(float)          # scores already calibrated
    va = VennAbers.fit(s, y)
    p, lo, hi = va.predict(np.linspace(0.05, 0.95, 19))
    assert np.all(lo <= p + 1e-12) and np.all(p <= hi + 1e-12)
    assert np.all((hi - lo) < 0.05)                    # plenty of data: a narrow interval
    assert np.allclose(p, np.linspace(0.05, 0.95, 19), atol=0.08)


def test_venn_abers_interval_is_wide_with_little_data():
    rng = np.random.default_rng(2)
    s = rng.random(30)
    va = VennAbers.fit(s, (rng.random(30) < s).astype(float))
    _, lo, hi = va.predict(np.array([0.5]))
    assert hi[0] - lo[0] > 0.05


def test_folds_hold_out_blocks_with_an_embargo():
    origins = pd.Series(pd.date_range("2026-07-01T00:00:00Z", periods=400, freq="h"))
    covered = np.zeros(len(origins), bool)
    for train, held in time_folds(origins):
        assert not (train & held).any()
        gap = (origins[train].to_numpy()[:, None] - origins[held].to_numpy()[None, :])
        assert np.abs(gap).min() > alert_model.EMBARGO
        covered |= held
    assert covered.all()


@pytest.mark.parametrize("column, family", [
    ("f_mfrr_up_px_vs_spot_last", "Recent balancing"), ("f_se3imb_vs_fispot", "Neighbour imbalance prices"),
    ("f_ee__imb_mean4", "Neighbour imbalance prices"), ("fmax_wind_fc_ramp", "Wind"), ("f_nwp_temp_c", "Temperature"),
    ("fmin_spot", "Spot price shape"), ("b_union_spike_high", "Price forecast"), ("rev_p50_max", "Change since the previous forecast"),
    ("gap_p_up_max", "Disagreement between models"), ("f_se1_flow_last", "Cross-border flows"), ("window_idx", "How far ahead"),
])
def test_driver_families(column, family):
    assert driver_family(column) == family


@pytest.mark.parametrize("family", alert_model.FAMILIES)
def test_bundle_round_trip(tmp_path, family):
    table = synthetic()
    inputs = ["window_idx", "f_wind_fc", "noise", *sorted({c for cols in alert_model.RULE_INPUTS.values() for c in cols}
                                                          - {"f_wind_fc"})]
    inputs = list(dict.fromkeys(inputs))
    bundle = AlertBundle.train("alerts-test", table, inputs, {e: family for e in events.EVENT_IDS},
                               {e: e for e in events.EVENT_IDS})
    bundle.save(tmp_path)
    loaded = AlertBundle.load("alerts-test", tmp_path)
    a, b = bundle.predict(table), loaded.predict(table)
    assert np.allclose(a[["p", "p_lo", "p_hi"]], b[["p", "p_lo", "p_hi"]])
    assert (a["drivers"] == b["drivers"]).all()
    assert a["p"].between(0, 1).all() and (a["p_lo"] <= a["p_hi"] + 1e-12).all()
    assert set(a["event"]) == set(events.EVENT_IDS) and len(a) == len(table) * len(events.EVENT_IDS)
    t = a.groupby("window")["threshold"].first()
    assert (t <= alert_model.DEFAULT_THRESHOLD_CAP).all()

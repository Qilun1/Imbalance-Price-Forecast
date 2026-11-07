"""Event labels on synthetic series: definitions, unknown quarters and the training cutoff."""
import numpy as np
import pandas as pd
import pytest

from imbalance import events
from imbalance.contract import HORIZON_STEPS, SPIKE_MARGIN
from imbalance.paths import STATIC_DB

H = HORIZON_STEPS


def quiet(n: int = 1) -> dict[str, np.ndarray]:
    """A calm horizon: price at spot, down-regulation, small activations."""
    return {"imbalance": np.full((n, H), 40.0), "spot": np.full((n, H), 40.0),
            "direction": np.full((n, H), -1.0), "mfrr_up": np.zeros((n, H)), "mfrr_down": np.full((n, H), -20.0)}


def lab(real, last_dir=(-1.0,), p50=None) -> pd.DataFrame:
    return events.window_labels(real, np.array(last_dir), p50).set_index("window")


def test_windows_cover_the_horizon_once():
    steps = [s for a, b in events.WINDOWS.values() for s in range(a, b + 1)]
    assert steps == list(range(1, H + 1))


def test_calm_horizon_has_no_events():
    out = lab(quiet(), p50=np.full((1, H), 40.0))
    assert (out[list(events.EVENT_IDS)] == 0).all().all()


def test_spike_needs_two_quarters_in_the_window():
    real = quiet()
    real["imbalance"][0, 2] = 40 + SPIKE_MARGIN + 1          # one quarter in "now": not enough
    assert lab(real).loc["now", "spike_high"] == 0
    real["imbalance"][0, 5] = 40 + SPIKE_MARGIN + 1          # second quarter in "now"
    out = lab(real)
    assert out.loc["now", "spike_high"] == 1 and out.loc["soon", "spike_high"] == 0
    real["imbalance"][0, 30:32] = 40 - SPIKE_MARGIN - 1
    assert lab(real).loc["later", "spike_low"] == 1


def test_margin_is_strict():
    real = quiet()
    real["imbalance"][0, :8] = 40 + SPIKE_MARGIN               # exactly at the margin is not a spike
    assert lab(real).loc["now", "spike_high"] == 0


def test_episodes_need_consecutive_quarters():
    real = quiet()
    real["direction"][0, [8, 9, 10, 12]] = 1                  # 3 in a row, then a gap
    assert lab(real).loc["soon", "up_episode"] == 0
    real["direction"][0, 11] = 1
    out = lab(real)
    assert out.loc["soon", "up_episode"] == 1
    assert out.loc["soon", "direction_flip"] == 1              # latest known direction was down


def test_flip_is_relative_to_the_latest_direction():
    real = quiet()                                             # down all along
    assert lab(real, last_dir=(1.0,)).loc["now", "direction_flip"] == 1
    assert lab(real, last_dir=(-1.0,)).loc["now", "direction_flip"] == 0
    assert np.isnan(lab(real, last_dir=(np.nan,)).loc["now", "direction_flip"])


def test_levels_and_activations():
    real = quiet()
    real["imbalance"][0, 25] = events.EXTREME_PRICE + 1
    real["spot"][0, 25] = events.EXTREME_PRICE + 1              # not a spike, but extreme
    real["imbalance"][0, 0:4] = events.DEEP_NEGATIVE - 1
    real["mfrr_up"][0, 9:11] = events.LARGE_UP_MW + 1
    real["mfrr_down"][0, 30:32] = events.LARGE_DOWN_MW - 1
    out = lab(real)
    assert out.loc["later", "extreme_price"] == 1 and out.loc["later", "spike_high"] == 0
    assert out.loc["now", "deep_negative"] == 1
    assert out.loc["soon", "large_up_activation"] == 1
    assert out.loc["later", "large_down_activation"] == 1


def test_forecast_miss_needs_p50():
    real = quiet()
    real["imbalance"][0, 0:2] = 200.0
    assert np.isnan(lab(real).loc["now", "forecast_miss"])
    assert lab(real, p50=np.full((1, H), 40.0)).loc["now", "forecast_miss"] == 1


def test_unknown_quarters_give_nan_unless_already_decided():
    real = quiet()
    real["imbalance"][0, 3:8] = np.nan                         # part of "now" unknown, no spike so far
    assert np.isnan(lab(real).loc["now", "spike_high"])
    real["imbalance"][0, 0:2] = 40 + SPIKE_MARGIN + 1          # already decided by the known quarters
    assert lab(real).loc["now", "spike_high"] == 1
    real = quiet()
    real["imbalance"][0, 7] = np.nan                           # one unknown quarter cannot make 2 spikes
    assert lab(real).loc["now", "spike_high"] == 0


@pytest.mark.skipif(not STATIC_DB.exists(), reason="static store not built")
def test_labels_never_look_past_the_cutoff():
    from imbalance.features import load_store
    store = load_store()
    cutoff = pd.Timestamp("2026-08-01T20:45:00Z")
    origins = pd.date_range("2026-08-01T12:00:00Z", "2026-08-01T20:00:00Z", freq="h")
    cut = events.labels(store, origins, last_delivery=cutoff)
    # Recompute from realised values with every quarter after the cutoff blanked by hand.
    real, last_dir = events.realised(store, origins)
    delivery = origins.as_unit("ns").asi8[:, None] + np.arange(H)[None, :] * pd.Timedelta(minutes=15).value
    real = {k: np.where(delivery > cutoff.value, np.nan, v) for k, v in real.items()}
    expected = events.window_labels(real, last_dir)
    ids = list(events.EVENT_IDS)
    assert np.array_equal(cut[ids].to_numpy(), expected[ids].to_numpy(), equal_nan=True)
    # The last origin's "later" window lies wholly after the cutoff: no event can be known there.
    last = cut[(cut["forecast_origin_utc"] == origins[-1]) & (cut["window"] == "later")]
    assert last[ids].isna().all(axis=1).all()

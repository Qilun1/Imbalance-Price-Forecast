"""Inference of the event classifiers: reproducible from the store alone, and wired to the right models."""
import numpy as np
import pandas as pd
import pytest

from imbalance import alert_inference
from imbalance.alert_model import AlertBundle
from imbalance.contract import TEST_FIRST_ORIGIN, VALIDATION_FIRST_ORIGIN
from imbalance.paths import ARTIFACTS_DIR, INFER_DB, STATIC_DB

trained = pytest.mark.skipif(
    not (STATIC_DB.exists() and INFER_DB.exists() and (ARTIFACTS_DIR / "alerts" / "meta.json").exists()
         and (ARTIFACTS_DIR / "alerts-val" / "meta.json").exists()),
    reason="event classifiers have not been trained and run")


def test_confidence_tiers():
    tier = alert_inference.confidence(np.array([0.001, 0.03, 0.2, 0.001, 0.001]),
                                      np.array([60, 60, 60, 200, 60]), np.array([0, 0, 0, 0, 80]))
    assert tier.tolist() == ["high", "medium", "low", "low", "medium"]


@trained
@pytest.mark.parametrize("bundle, base, challenger", [("alerts-val", "lgbm_v4s-val", "lgbm_v4ms-val"),
                                                      ("alerts", "lgbm_v4s", "lgbm_v4ms")])
def test_bundles_read_the_models_they_were_trained_on(bundle, base, challenger):
    assert alert_inference.base_models_of(AlertBundle.load(bundle)) == (base, challenger)


@trained
@pytest.mark.parametrize("bundle, origin", [("alerts-val", VALIDATION_FIRST_ORIGIN + pd.Timedelta(days=10)),
                                            ("alerts", TEST_FIRST_ORIGIN + pd.Timedelta(days=12, hours=7))])
def test_inference_from_the_store_matches_the_stored_notes(bundle, origin):
    """Building features from scratch at inference gives the same probabilities as the batch run."""
    origins = pd.DatetimeIndex([origin])
    fresh = alert_inference.infer(bundle, origins, write=False)
    stored = alert_inference.read_probs(bundle, origins)
    assert len(fresh) == len(stored) == 27                       # 9 events x 3 windows
    keys = ["window", "event"]
    both = fresh.merge(stored, on=keys, suffixes=("", "_stored"))
    for c in ("p", "p_lo", "p_hi", "base_rate", "threshold"):
        assert np.allclose(both[c], both[f"{c}_stored"], atol=1e-9), c
    assert (both["confidence"] == both["confidence_stored"]).all()

"""Guards for the organiser's rules. Tests that need the starter data skip if it is not ingested."""
import json

import numpy as np
import pandas as pd
import pytest

from imbalance import contract, store
from imbalance.paths import STATIC_DB, STARTER_PKG


def test_submission_columns_come_from_template():
    assert contract.submission_columns() == [
        "forecast_origin_utc", "delivery_start_utc", "step", "p10", "p50", "p90", "p_up", "p_down",
        "p_none", "p_spike_high", "p_spike_low", "data_cutoff_utc", "top_drivers"]


def test_test_origins_count():
    assert len(contract.read_origins(contract.TEST_ORIGINS)) == 673


def test_organiser_files_unchanged():
    """Hashes from the organiser's SHA256SUMS.txt (starter package v1, locked 3 Nov 2026)."""
    import hashlib
    expected = {
        "validate_submission.py": "61b10ea961e08551ab35c63eeea6dcbd523d844a26279c80414e11905f813d72",
        "score.py": "da0857c8a644f4ceef7805dd262114dccb2162d6904a717c4ea9b882762f42d5",
        "make_templates.py": "7b5ef6606e61c1053f7bdebadf1b9b482944e92fac3f43fa2f59e5702a148e6e",
        "sample_submission.csv": "f21e9dd1f992c168e47b904d28d27ad7c38c31f92fb72c4890d92b7f3045a6b0",
        "forecast_origins.csv": "fb5a7dd9cf9311ad7e22f7f8a86a85a81670aaee4df0194c95af537851117223",
        "availability.csv": "b1de7b9895981d96d72eb5f5f51db0765b2814b72ac6af512c34e54a0ba96f8d",
    }
    for name, h in expected.items():
        data = (STARTER_PKG / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == h, f"{name} differs from the organiser's file"


needs_store = pytest.mark.skipif(not STATIC_DB.exists(), reason="store not ingested")


@needs_store
def test_fingrid_rule_matches_organiser():
    """Our Fingrid availability rules reproduce the organiser's first_usable_origin_utc exactly."""
    from tools.ingest.fingrid import DATASETS, first_usable
    obs = store.load_observations([v[0] for k, v in DATASETS.items() if k in (319, 124, 246)])
    for ds in (319, 124, 246):
        sid, _, rule = DATASETS[ds]
        g = obs[obs["series_id"] == sid]
        ours = first_usable(g["timestamp_utc"], rule, pd.Timedelta(minutes=15))
        assert (ours.to_numpy() == g["first_usable_origin_utc"].to_numpy()).all(), sid


@needs_store
def test_store_never_overwrites(tmp_path):
    db = tmp_path / "t.duckdb"
    row = dict(series_id="x", source="t", dataset_id="1", timestamp_utc=pd.Timestamp("2026-01-01", tz="UTC"),
               value=1.0, unit="u", first_usable_origin_utc=pd.Timestamp("2026-01-01T01:00", tz="UTC"))
    assert store.insert_observations(pd.DataFrame([row]), "a", db) == 1
    assert store.insert_observations(pd.DataFrame([{**row, "value": 2.0}]), "b", db) == 0
    assert store.load_observations(path=db)["value"].tolist() == [1.0]


def test_openmeteo_parse(monkeypatch):
    from tools.ingest import openmeteo
    sites = pd.DataFrame({"site_id": ["a", "b"], "lat": [64.0, 65.0], "lon": [24.0, 25.0]})
    t0 = int(pd.Timestamp("2026-10-01T00:00Z").timestamp())
    payload = [{"hourly": {"time": [t0, t0 + 3600], "wind_speed_100m": [5.0, 6.0], "temperature_2m": [1, 2]}}] * 2

    class Fake:
        def get_json(self, url, params=None, cache=None, weight=1.0):
            assert weight == 2, "each location must count as one API call"
            assert params["run"] == "2026-10-01T00:00" and params["models"] == "ecmwf_ifs"
            return payload

    df = openmeteo.fetch_run(Fake(), "ecmwf_ifs", pd.Timestamp("2026-10-01T00:00Z"), sites)
    assert set(df["location_id"]) == {"a", "b"}
    assert (df["first_usable_origin_utc"] == pd.Timestamp("2026-10-01T07:00Z")).all()
    assert (df["first_usable_origin_utc"] > df["run_init_utc"]).all()

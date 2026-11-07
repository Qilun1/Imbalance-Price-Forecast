"""API contract: the organiser's rules hold for everything the dashboard can see.

Most tests run on invented mock data, so they need no licensed files. The last group runs on the real
forecasts and is skipped if the pipeline has not been run.
"""
import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api import mock
from backend.api.alerts import build_alerts
from backend.api.labels import LABELS, label_for
from backend.api.main import app
from backend.api.repository import DISPLAY_SERIES, Repository, get_repository
from backend.api.settings import MOCK_BASELINE, MOCK_CHALLENGER, MOCK_MODEL, Period, Settings
from imbalance.contract import SPOT_SERIES, TEST_FIRST_ORIGIN, VALIDATION_FIRST_ORIGIN
from imbalance.paths import ARTIFACTS_DIR, INFER_DB, STATIC_DB

SCENARIO = {s.name: s for s in mock.SCENARIOS}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    path = mock.generate(tmp_path_factory.mktemp("mock") / "mock.duckdb")
    return Repository(Settings("mock", (Period("mock", MOCK_MODEL, MOCK_BASELINE, challenger=MOCK_CHALLENGER),), path, path))


@pytest.fixture()
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def keys_of(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_of(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_of(v)}
    return set()


def test_mock_is_repeatable_and_follows_the_rules(tmp_path, repo):
    again = Repository(replace(repo.settings, forecast_db=(p := mock.generate(tmp_path / "again.duckdb")), store_db=p))
    numbers = ["p10", "p50", "p90", "p_up", "p_spike_high"]
    assert np.array_equal(again.primary[numbers].to_numpy(), repo.primary[numbers].to_numpy())
    mock.check_rows(repo.primary)
    mock.check_rows(repo.baseline)
    mock.check_rows(repo.challenger)


def test_spot_is_never_loaded(repo):
    assert SPOT_SERIES not in DISPLAY_SERIES
    assert set(repo.observations["series_id"]) == set(DISPLAY_SERIES)


def test_meta(client):
    body = client.get("/api/meta").json()
    assert body["mode"] == "mock" and body["origins"] == mock.N_ORIGINS
    assert body["horizon_steps"] == 40 and body["spike_margin_eur_mwh"] == 50.0


def test_forecast_has_40_valid_steps(client):
    body = client.get("/api/forecast").json()
    steps = body["steps"]
    assert [s["step"] for s in steps] == list(range(1, 41))
    assert steps[0]["delivery_start_utc"] == body["origin_utc"]
    for s in steps:
        assert s["p10"] <= s["p50"] <= s["p90"]
        assert abs(s["p_up"] + s["p_down"] + s["p_none"] - 1.0) < 0.001
        assert s["p_spike_high"] + s["p_spike_low"] <= 1.001


def test_as_of_uses_the_newest_forecast_already_made(client):
    body = client.get("/api/forecast", params={"as_of": "2026-10-23T07:40:00Z"}).json()
    assert body["origin_utc"] == "2026-10-23T07:00:00Z"
    assert body["data_cutoff_utc"] <= body["origin_utc"]
    assert body["data_age_minutes"] == 75


def test_as_of_outside_the_data_is_a_clear_error(client):
    assert client.get("/api/forecast", params={"as_of": "2020-01-01T00:00:00Z"}).status_code == 404
    assert client.get("/api/forecast", params={"as_of": "2030-01-01T00:00:00Z"}).status_code == 404


def test_naive_timestamps_are_rejected(client):
    assert client.get("/api/forecast", params={"as_of": "2026-10-23T07:00:00"}).status_code == 422


def test_actuals_show_only_what_was_usable_at_that_moment(client, repo):
    as_of = pd.Timestamp("2026-10-23T07:00:00Z")
    body = client.get("/api/actuals", params={"as_of": iso(as_of), "from": iso(as_of - pd.Timedelta(days=2)),
                                              "to": iso(as_of + pd.Timedelta(days=2))}).json()
    usable = repo.observations.query("series_id == 'fi_imbalance_price'").set_index("timestamp_utc")["first_usable_origin_utc"]
    shown = pd.to_datetime([p["delivery_start_utc"] for p in body["points"]], utc=True)
    assert (usable.loc[shown] <= as_of).all()
    assert shown.max() == as_of - pd.Timedelta(minutes=75)      # README section 4: 60 min delay, then next full hour
    assert body["points"][-1]["direction"] in ("up", "down", "none")


def test_changes_cover_the_36_overlapping_quarter_hours(client):
    body = client.get("/api/changes", params={"as_of": iso(SCENARIO["large_revision"].as_of)}).json()
    assert body["previous_origin_utc"] == "2026-10-25T02:00:00Z"
    assert len(body["points"]) == 36
    assert body["largest_p50_change"] >= 25


def test_first_forecast_has_nothing_to_compare_with(client):
    body = client.get("/api/changes", params={"as_of": iso(mock.FIRST_ORIGIN)}).json()
    assert body["previous_origin_utc"] is None and body["points"] == []


@pytest.mark.parametrize("scenario, kind", [
    ("spike_risk_rising", "spike_risk"), ("direction_flip", "regulation_expected"),
    ("large_revision", "forecast_changed"), ("wide_uncertainty", "high_uncertainty"),
    ("stale_data", "stale_data"), ("conflicting_signals", "conflicting_signals"),
])
def test_each_scripted_situation_raises_its_alert(client, scenario, kind):
    body = client.get("/api/alerts", params={"as_of": iso(SCENARIO[scenario].as_of)}).json()
    assert kind in {a["kind"] for a in body["alerts"]}


def test_conflict_means_an_independent_model_disagrees(client, repo):
    as_of = SCENARIO["conflicting_signals"].as_of
    body = client.get("/api/alerts", params={"as_of": iso(as_of)}).json()
    alert = next(a for a in body["alerts"] if a["kind"] == "conflicting_signals")
    assert "second model built on different input data" in alert["message"]
    assert "regulation direction" in alert["message"] and alert["evidence"]["largest_direction_gap"] >= 0.30
    current = repo.forecast(repo.origin_at(as_of))
    assert not [a for a in build_alerts(current, None) if a.kind == "conflicting_signals"], "no second model, no conflict"
    assert not [a for a in build_alerts(current, None, current) if a.kind == "conflicting_signals"], "a model agrees with itself"


def test_meta_names_the_second_model(client):
    assert client.get("/api/meta").json()["periods"][0]["challenger"] == MOCK_CHALLENGER


def test_overlapping_risks_ask_for_an_expert_review(client):
    body = client.get("/api/alerts", params={"as_of": "2026-10-23T09:00:00Z"}).json()
    review = [a for a in body["alerts"] if a["kind"] == "expert_review"]
    assert review and review[0]["severity"] == "review"
    assert body["alerts"][0]["severity"] == "review", "the most serious alert comes first"


def test_alerts_suggest_a_check_and_name_drivers(client):
    body = client.get("/api/alerts", params={"as_of": iso(SCENARIO["spike_risk_rising"].as_of)}).json()
    alert = next(a for a in body["alerts"] if a["kind"] == "spike_risk")
    assert "Worth checking" in alert["message"] and alert["drivers"]
    assert "exceptionally high price has increased" in alert["message"]
    assert alert["window_start_utc"] == "2026-10-23T13:00:00Z" and alert["window_end_utc"] == "2026-10-23T15:00:00Z"


def test_alert_times_read_in_helsinki_across_the_clock_change(client):
    body = client.get("/api/alerts", params={"as_of": iso(SCENARIO["large_revision"].as_of)}).json()
    alert = next(a for a in body["alerts"] if a["kind"] == "forecast_changed")
    assert "09:00–12:00" in alert["message"]                    # 07:00-10:00 UTC, after the clocks went back


def test_performance_never_looks_past_the_viewing_time(client):
    earlier = client.get("/api/performance", params={"as_of": "2026-10-23T07:00:00Z", "from": "2026-10-22T00:00:00Z",
                                                     "to": "2026-10-29T00:00:00Z"}).json()
    later = client.get("/api/performance", params={"as_of": "2026-10-27T07:00:00Z", "from": "2026-10-22T00:00:00Z",
                                                   "to": "2026-10-29T00:00:00Z"}).json()
    assert 0 < earlier["diagnostic"]["model"]["overall"]["rows"] < later["diagnostic"]["model"]["overall"]["rows"]


def test_performance_is_labelled_and_compares_with_the_baseline(client):
    body = client.get("/api/performance").json()
    assert body["official"] is None
    assert body["diagnostic"]["note"].startswith("Diagnostic")
    model, baseline = body["diagnostic"]["model"], body["diagnostic"]["baseline"]
    assert model["overall"]["brier_spike_mean"] is None         # needs spot, which the API never loads
    assert 0.0 <= model["overall"]["coverage_p10_p90"] <= 1.0
    assert [h["horizon_hour"] for h in model["by_horizon"]] == list(range(1, 11))
    assert model["overall"]["mae_p50"] < baseline["overall"]["mae_p50"]


@pytest.mark.parametrize("path", ["/api/meta", "/api/forecast", "/api/changes", "/api/actuals", "/api/alerts", "/api/performance"])
def test_no_response_has_a_spot_field(client, path):
    assert not [k for k in keys_of(client.get(path).json()) if "spot" in k.lower()]


def test_every_model_feature_has_a_label():
    metas = sorted(ARTIFACTS_DIR.glob("*/meta.json"))   # models are not tracked: only those trained locally
    if not metas:
        pytest.skip("no trained models")
    for meta in metas:
        content = json.loads(meta.read_text(encoding="utf-8"))
        if "features" not in content:      # event classifiers (alerts*): drivers are grouped into families
            continue
        features = content["features"]
        assert not [f for f in features if f not in LABELS], meta.parent.name


def test_unknown_driver_ids_still_read_well():
    assert label_for("new_wind__signal") == "New wind signal"


# ---------- real forecasts ----------
needs_real = pytest.mark.skipif(not (STATIC_DB.exists() and INFER_DB.exists()), reason="pipeline has not been run")


@pytest.fixture(scope="module")
def real_repo():
    from backend.api.settings import load_settings
    import os
    keep = os.environ.get("IMBALANCE_DATA_MODE")
    os.environ["IMBALANCE_DATA_MODE"] = "real"
    try:
        return Repository(load_settings())
    finally:
        os.environ.pop("IMBALANCE_DATA_MODE") if keep is None else os.environ.__setitem__("IMBALANCE_DATA_MODE", keep)


@pytest.fixture()
def real_client(real_repo):
    app.dependency_overrides[get_repository] = lambda: real_repo
    yield TestClient(app)
    app.dependency_overrides.clear()


@needs_real
def test_real_periods_use_the_out_of_sample_model_for_validation(real_client):
    validation = real_client.get("/api/forecast", params={"as_of": iso(VALIDATION_FIRST_ORIGIN)}).json()
    test = real_client.get("/api/forecast", params={"as_of": iso(TEST_FIRST_ORIGIN)}).json()
    assert validation["model"] == "lgbm_v1-val" and test["model"] == "lgbm_v1"


@needs_real
def test_real_data_never_loads_spot(real_repo):
    assert "nordpool" not in set(real_repo.observations["source"])


@needs_real
def test_real_actuals_match_the_organisers_rule(real_client, real_repo):
    as_of = pd.Timestamp("2026-10-20T08:00:00Z")
    body = real_client.get("/api/actuals", params={"as_of": iso(as_of), "from": "2026-10-19T00:00:00Z",
                                                   "to": "2026-10-22T00:00:00Z"}).json()
    usable = real_repo.observations.query("series_id == 'fi_imbalance_price'").set_index("timestamp_utc")["first_usable_origin_utc"]
    shown = pd.to_datetime([p["delivery_start_utc"] for p in body["points"]], utc=True)
    assert (usable.loc[shown] <= as_of).all() and shown.max() == as_of - pd.Timedelta(minutes=75)


@needs_real
def test_model_switch_is_not_reported_as_a_market_change(real_client):
    body = real_client.get("/api/changes", params={"as_of": iso(TEST_FIRST_ORIGIN)}).json()
    assert body["previous_origin_utc"] is None


@needs_real
def test_official_scores_are_the_organisers(real_client):
    official = real_client.get("/api/performance").json()["official"]
    assert official["baseline"]["overall"]["mae_p50"] == pytest.approx(66.2033, abs=1e-4)
    assert official["model"]["overall"]["mae_p50"] < official["baseline"]["overall"]["mae_p50"]

"""Contract of /api/notes: personas, windows, thresholds, low-skill events, periods and the spot rule."""
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api import mock
from backend.api.main import app
from backend.api.repository import Repository, get_repository
from backend.api.settings import MOCK_BASELINE, MOCK_CHALLENGER, MOCK_MODEL, MOCK_NOTES, Period, Settings
from imbalance import events
from imbalance.contract import STEP, TEST_FIRST_ORIGIN, VALIDATION_FIRST_ORIGIN
from imbalance.paths import ARTIFACTS_DIR, INFER_DB, STATIC_DB


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    path = mock.generate(tmp_path_factory.mktemp("mock") / "mock.duckdb")
    period = Period("mock", MOCK_MODEL, MOCK_BASELINE, challenger=MOCK_CHALLENGER, notes=MOCK_NOTES)
    return Repository(Settings("mock", (period,), path, path))


@pytest.fixture()
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def get(client, **params):
    response = client.get("/api/notes", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("persona", events.PERSONAS)
def test_each_persona_sees_only_its_events_in_every_window(client, persona):
    body = get(client, persona=persona)
    mine = {e.id for e in events.EVENTS if persona in e.personas}
    assert {n["event"] for n in body["notes"]} == mine
    assert len(body["notes"]) == len(mine) * len(events.WINDOWS)
    for n in body["notes"]:
        assert n["check"] == events.CHECKS[(persona, n["event"])]
        assert 0 <= n["probability_low"] <= n["probability"] <= n["probability_high"] <= 1
        assert n["fires"] == (n["probability"] >= n["threshold"])


def test_windows_follow_the_origin(client):
    body = get(client, persona="trader")
    origin = pd.Timestamp(body["origin_utc"])
    for n in body["notes"]:
        first, last = events.WINDOWS[n["window"]]
        assert pd.Timestamp(n["window_start_utc"]) == origin + (first - 1) * STEP
        assert pd.Timestamp(n["window_end_utc"]) == origin + last * STEP


def test_firing_notes_come_first(client):
    fires = [n["fires"] for n in get(client, persona="operator")["notes"]]
    assert fires == sorted(fires, reverse=True)


def test_threshold_override_changes_only_fires(client):
    default = {(n["event"], n["window"]): n for n in get(client, persona="trader")["notes"]}
    zero = {(n["event"], n["window"]): n for n in get(client, persona="trader", thresholds="spike_high:0")["notes"]}
    for key, n in zero.items():
        assert n["probability"] == default[key]["probability"]
        if key[0] == "spike_high":
            assert n["threshold"] == 0 and n["fires"]
        else:
            assert n["fires"] == default[key]["fires"]


@pytest.mark.parametrize("bad", ["nonsense:0.2", "spike_high:2", "spike_high:x"])
def test_bad_thresholds_are_rejected(client, bad):
    assert client.get("/api/notes", params={"persona": "trader", "thresholds": bad}).status_code == 422


def test_persona_is_required_and_checked(client):
    assert client.get("/api/notes").status_code == 422
    assert client.get("/api/notes", params={"persona": "ceo"}).status_code == 422


def test_low_skill_events_are_hidden_unless_asked(repo, client):
    repo.low_skill[MOCK_NOTES] = frozenset({"spike_high"})
    try:
        hidden = get(client, persona="trader")
        shown = get(client, persona="trader", include_low_skill=True)
    finally:
        repo.low_skill[MOCK_NOTES] = frozenset()
    assert "spike_high" not in {n["event"] for n in hidden["notes"]}
    flagged = [n for n in shown["notes"] if n["event"] == "spike_high"]
    assert flagged and all(n["low_skill"] for n in flagged)


def test_no_spot_field_in_notes(client):
    """As for every other route: no key carries a spot value. Definitions name the rule ("spot + 50"),
    a constant, from which no spot price can be recovered."""
    def keys_of(value):
        if isinstance(value, dict):
            return set(value) | {k for v in value.values() for k in keys_of(v)}
        if isinstance(value, list):
            return {k for v in value for k in keys_of(v)}
        return set()
    for persona in events.PERSONAS:
        assert not [k for k in keys_of(get(client, persona=persona)) if "spot" in k.lower()]


# ---------- real pipeline output ----------
needs_real = pytest.mark.skipif(
    not (STATIC_DB.exists() and INFER_DB.exists() and (ARTIFACTS_DIR / "alerts" / "meta.json").exists()),
    reason="event classifiers have not been trained and run")


@pytest.fixture(scope="module")
def real_client():
    from backend.api.settings import load_settings
    keep = os.environ.get("IMBALANCE_DATA_MODE")
    os.environ["IMBALANCE_DATA_MODE"] = "real"
    try:
        real = Repository(load_settings())
    finally:
        os.environ.pop("IMBALANCE_DATA_MODE") if keep is None else os.environ.__setitem__("IMBALANCE_DATA_MODE", keep)
    app.dependency_overrides[get_repository] = lambda: real
    yield TestClient(app)
    app.dependency_overrides.clear()


@needs_real
def test_real_notes_use_the_out_of_sample_bundle_for_validation(real_client):
    val = real_client.get("/api/notes", params={"persona": "trader", "as_of": VALIDATION_FIRST_ORIGIN.isoformat()}).json()
    test = real_client.get("/api/notes", params={"persona": "trader", "as_of": TEST_FIRST_ORIGIN.isoformat()}).json()
    assert val["model"] == "alerts-val" and test["model"] == "alerts"
    assert val["notes"] and test["notes"]

"""UMM feed: availability rule and API contract (works with or without ingested UMM data)."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.umm_feed import available, umm_feed


def test_umm_endpoint_contract():
    with TestClient(app) as c:
        r = c.get("/api/umm")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"as_of_utc", "available", "messages"}


@pytest.mark.skipif(not available(), reason="UMM data not ingested")
def test_umm_feed_uses_only_published_versions():
    as_of = pd.Timestamp("2026-09-09T17:00:00Z")
    msgs = umm_feed(as_of, hours=10, min_mw=0)
    assert all(pd.Timestamp(m["publication_utc"]) + pd.Timedelta(minutes=5) <= as_of for m in msgs)
    assert all(m["url"].startswith("https://umm.nordpoolgroup.com/") for m in msgs)
    before = umm_feed(pd.Timestamp("2026-09-09T16:00:00Z"), hours=10, min_mw=1000)
    after = umm_feed(as_of, hours=10, min_mw=1000)
    assert not any(m["unplanned"] and m["fresh"] for m in before)      # the OL3 trip is not known yet
    assert any(m["unplanned"] and m["fresh"] and m["fuel"] == "nuclear" for m in after)

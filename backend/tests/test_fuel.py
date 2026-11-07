"""Offline tests. Fixtures mirror real Statistics Finland json-stat2 responses
(13p7 2026M04-M06 and 12gb 2026Q1-Q2, fetched 7 Nov 2026)."""
import json
import time

import pytest

from backend.fuel import costs, service, sources
from backend.fuel import config as C

P13 = {
    "id": ["timeperiod_m", "energia_47_20220101", "contentscode"],
    "size": [3, 4, 1],
    "dimension": {
        "timeperiod_m": {"category": {"index": {"2026M04": 0, "2026M05": 1, "2026M06": 2}}},
        "energia_47_20220101": {"category": {"index": {"A": 0, "B": 1, "C": 2, "D": 3}}},
        "contentscode": {"category": {"index": {"vl_polttoaine_hinta": 0}}},
    },
    "value": [57, None, 38, 16, 56, None, 38, 16, 56, None, 38, 16],
    "updated": "2026-09-24T05:00:00Z",
}
P12 = {
    "id": ["timeperiod_q", "energia_27_20200611", "contentscode"],
    "size": [2, 5, 1],
    "dimension": {
        "timeperiod_q": {"category": {"index": {"2026Q1": 0, "2026Q2": 1}}},
        "energia_27_20200611": {"category": {"index": {k: i for i, k in enumerate("ABCDE")}}},
        "contentscode": {"category": {"index": {"hinta_eur_mwh": 0}}},
    },
    "value": [22.3, 16.6, None, None, 37.6, 21.5, 15.8, None, None, 37.6],
}


def test_parse_13p7():
    s = sources.parse_jsonstat2(P13, C.STATFI_POWER_TIME, C.STATFI_POWER_FUEL_DIM,
                                C.STATFI_POWER_FUELS)
    assert s["forest_chips"][-1] == ("2026M06", 38.0)
    assert s["natural_gas"][0] == ("2026M04", 57.0)
    assert s["coal"] == []  # suppressed value -> empty series


def test_parse_12gb():
    s = sources.parse_jsonstat2(P12, C.STATFI_DOMESTIC_TIME, C.STATFI_DOMESTIC_FUEL_DIM,
                                C.STATFI_DOMESTIC_FUELS)
    assert s["milled_peat"] == [("2026Q1", 16.6), ("2026Q2", 15.8)]
    assert s["forest_chips"][-1] == ("2026Q2", 37.6)


def _prices():
    mk = lambda js, t, d, m, src: {"series": sources.parse_jsonstat2(js, t, d, m),
                                   "updated": None, "source": src}
    return {
        "power": mk(P13, C.STATFI_POWER_TIME, C.STATFI_POWER_FUEL_DIM, C.STATFI_POWER_FUELS, "13p7"),
        "domestic": mk(P12, C.STATFI_DOMESTIC_TIME, C.STATFI_DOMESTIC_FUEL_DIM,
                       C.STATFI_DOMESTIC_FUELS, "12gb"),
        "eua": {"eur_t": 80.0, "as_of": "x", "source": "test"},
    }


def test_cost_formulas():
    assert costs.fuel_cost_with_co2(16, 0.381, 80) == pytest.approx(46.48)
    # back-pressure: heat credit can make power cost negative
    assert costs.chp_power_cost(38, 0.28, 0.60, 70) == pytest.approx((38 - 42) / 0.28)
    # breakeven consistency: at the breakeven spot both heat sources cost the same
    be = costs.e_boiler_breakeven_spot(43.2, 6, 0.99)
    assert costs.e_boiler_heat_cost(be, 6, 0.99) == pytest.approx(43.2)


def test_snapshot_without_spot():
    snap = service.build_snapshot(_prices())
    f = snap["fuels"]
    assert f["forest_chips"]["source"] == "13p7"  # monthly preferred over quarterly
    assert f["milled_peat"]["eur_mwh_incl_co2"] == pytest.approx(16 + 0.381 * 80, abs=0.01)
    assert f["srf"]["eur_mwh"] is None
    assert snap["heat"]["cheapest"] == "heat_only_boiler"
    rows = {r["fuel"]: r for r in snap["chp"]["by_fuel"]}
    assert rows["coal"]["power_cost_gross"] is None  # no public coal price for power in 2026
    assert rows["forest_chips"]["power_cost_after_heat_credit"] is not None
    json.dumps(snap)  # JSON-serialisable


def test_snapshot_low_spot_switches_to_e_boiler():
    snap = service.build_snapshot(_prices(), spot_eur_mwh=5.0)
    assert snap["heat"]["cheapest"] == "electric_boiler"
    be = snap["heat"]["e_boiler_cheaper_below_spot"]
    assert service.build_snapshot(_prices(), be + 1)["heat"]["cheapest"] == "heat_only_boiler"


def test_cache_keeps_stale_on_failure(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({**_prices(), "fetched_at": time.time() - 10 * C.CACHE_TTL_S}))

    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(sources, "fetch_statfi_power_fuels", boom)
    monkeypatch.setattr(sources, "fetch_statfi_domestic_fuels", boom)
    out = service.fetch_prices(cache_path=cache)
    assert out["errors"]["note"] == "using stale cache"
    assert "power" in out


def test_failed_fetch_is_not_cached(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"fetched_at": time.time(), "errors": {"power": "x"}}))
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise OSError("offline")
    monkeypatch.setattr(sources, "fetch_statfi_power_fuels", boom)
    monkeypatch.setattr(sources, "fetch_statfi_domestic_fuels", boom)
    out = service.fetch_prices(cache_path=cache)  # fresh but empty cache must be retried
    assert calls and "power" not in out
    assert json.loads(cache.read_text())["errors"] == {"power": "x"}  # not rewritten
    snap = service.build_snapshot({**out, "eua": {"eur_t": 80.0}})
    assert snap["heat"]["heat_only_boiler_eur_mwh"] is None

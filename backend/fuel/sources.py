"""Fetchers for reference fuel and carbon prices. Stdlib only."""
from __future__ import annotations

import json
import os
import urllib.request

from . import config as C


def _post_json(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=C.HTTP_TIMEOUT_S) as r:
        return json.load(r)


def parse_jsonstat2(js: dict, time_dim: str, fuel_dim: str, fuel_map: dict) -> dict:
    """Return {fuel: [(period, value), ...]} from a json-stat2 cube with dims
    (time, fuel, content) and exactly one content code."""
    ids = js["id"]
    size = js["size"]
    dims = js["dimension"]

    def ordered(dim):
        idx = dims[dim]["category"]["index"]
        return sorted(idx, key=idx.get) if isinstance(idx, dict) else list(idx)

    times, fuels = ordered(time_dim), ordered(fuel_dim)
    strides = {}
    s = 1
    for d, n in zip(reversed(ids), reversed(size)):
        strides[d] = s
        s *= n

    out: dict[str, list] = {}
    for fi, fcode in enumerate(fuels):
        name = fuel_map.get(fcode)
        if not name:
            continue
        series = []
        for ti, t in enumerate(times):
            v = js["value"][ti * strides[time_dim] + fi * strides[fuel_dim]]
            if v is not None:
                series.append((t, float(v)))
        out[name] = series
    return out


def _query(time_dim: str, n: int, content: str) -> dict:
    return {
        "query": [
            {"code": time_dim, "selection": {"filter": "top", "values": [str(n)]}},
            {"code": "contentscode", "selection": {"filter": "item", "values": [content]}},
        ],
        "response": {"format": "json-stat2"},
    }


def fetch_statfi_power_fuels(months: int = 13) -> dict:
    js = _post_json(C.STATFI_BASE + C.STATFI_POWER_TABLE,
                    _query(C.STATFI_POWER_TIME, months, C.STATFI_POWER_CONTENT))
    return {"series": parse_jsonstat2(js, C.STATFI_POWER_TIME, C.STATFI_POWER_FUEL_DIM,
                                      C.STATFI_POWER_FUELS),
            "updated": js.get("updated"), "source": "Statistics Finland 13p7 (monthly)"}


def fetch_statfi_domestic_fuels(quarters: int = 5) -> dict:
    js = _post_json(C.STATFI_BASE + C.STATFI_DOMESTIC_TABLE,
                    _query(C.STATFI_DOMESTIC_TIME, quarters, C.STATFI_DOMESTIC_CONTENT))
    return {"series": parse_jsonstat2(js, C.STATFI_DOMESTIC_TIME, C.STATFI_DOMESTIC_FUEL_DIM,
                                      C.STATFI_DOMESTIC_FUELS),
            "updated": js.get("updated"), "source": "Statistics Finland 12gb (quarterly)"}


def fetch_eua() -> dict:
    """EUA spot via OilPriceAPI if OILPRICEAPI_KEY is set, else the manual value."""
    key = os.environ.get("OILPRICEAPI_KEY")
    err = None
    if key:
        try:
            req = urllib.request.Request(
                "https://api.oilpriceapi.com/v1/prices/latest?by_code=EU_CARBON_EUR",
                headers={"Authorization": f"Token {key}"},
            )
            with urllib.request.urlopen(req, timeout=C.HTTP_TIMEOUT_S) as r:
                d = json.load(r)["data"]
            return {"eur_t": float(d["price"]), "as_of": d.get("created_at"),
                    "source": "OilPriceAPI EU_CARBON_EUR"}
        except Exception as e:  # fall through to manual
            err = f"{type(e).__name__}: {e}"
    return {"eur_t": C.EUA_MANUAL_EUR_T, "as_of": C.EUA_MANUAL_AS_OF,
            "source": "manual (config.EUA_MANUAL_EUR_T)", "error": err}

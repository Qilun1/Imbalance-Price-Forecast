"""Builds the fuel-context snapshot the dashboard reads.

fetch_prices() -> cached raw prices (refresh daily; the data are monthly/quarterly)
build_snapshot(prices, spot) -> JSON-ready dict for the expandable panel
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import config as C
from . import costs, sources

# static_data/ is git-ignored (AGENTS.md rule 0: never commit data).
CACHE_PATH = Path(__file__).resolve().parents[2] / "static_data" / "cache" / "fuel" / "fuel_prices.json"


def fetch_prices(force: bool = False, cache_path: Path = CACHE_PATH) -> dict:
    cached = json.loads(cache_path.read_text()) if cache_path.exists() else None
    if cached is not None and "power" not in cached:
        cached = None  # a failed fetch is never a valid cache
    if not force and cached and time.time() - cached.get("fetched_at", 0) < C.CACHE_TTL_S:
        return cached

    out = {"fetched_at": time.time(), "errors": {}}
    for key, fn in (("power", sources.fetch_statfi_power_fuels),
                    ("domestic", sources.fetch_statfi_domestic_fuels)):
        try:
            out[key] = fn()
        except Exception as e:
            out["errors"][key] = f"{type(e).__name__}: {e}"
    out["eua"] = sources.fetch_eua()

    # Never overwrite a good cache with a failed fetch, and never cache a failure.
    if "power" not in out:
        if cached:
            cached["errors"] = {**out["errors"], "note": "using stale cache"}
            return cached
        return out
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out, indent=1))
    return out


def latest_fuel_prices(prices: dict) -> dict:
    """{fuel: {eur_mwh, period, source, history}}; monthly 13p7 first, 12gb fallback."""
    res: dict[str, dict] = {}
    for key in ("power", "domestic"):
        block = prices.get(key)
        if not block:
            continue
        for fuel, series in block["series"].items():
            if fuel in res or not series:
                continue
            period, val = series[-1]
            res[fuel] = {"eur_mwh": val, "period": period, "source": block["source"],
                         "history": series}
    for fuel, val in C.MANUAL_FUEL_PRICE_EUR_MWH.items():
        if fuel not in res:
            res[fuel] = {"eur_mwh": val, "period": None,
                         "source": "manual" if val is not None else "not available",
                         "history": []}
    return res


def build_snapshot(prices: dict, spot_eur_mwh: float | None = None) -> dict:
    eua = prices["eua"]["eur_t"]
    fuels = latest_fuel_prices(prices)

    for f, d in fuels.items():
        ef = C.EMISSION_FACTOR_T_PER_MWH.get(f, 0.0)
        d["co2_t_mwh"] = ef
        d["eur_mwh_incl_co2"] = (None if d["eur_mwh"] is None
                                 else round(costs.fuel_cost_with_co2(d["eur_mwh"], ef, eua), 2))

    # Alternative heat source for the CHP heat credit.
    hb = C.HEAT_ONLY_BOILER
    hb_fuel = fuels.get(hb["fuel"], {}).get("eur_mwh_incl_co2")
    heat_only = None if hb_fuel is None else costs.heat_only_cost(hb_fuel, hb["eta"])
    eb = C.UNITS["EB"]
    eb_heat = (None if spot_eur_mwh is None
               else costs.e_boiler_heat_cost(spot_eur_mwh, eb["adders_eur_mwh"], eb["eta"]))
    alts = {k: v for k, v in (("heat_only_boiler", heat_only), ("electric_boiler", eb_heat))
            if v is not None}
    heat_credit_src = min(alts, key=alts.get) if alts else None
    heat_credit = alts.get(heat_credit_src)

    chp = C.UNITS["NA4"]
    chp_rows = []
    for f in chp["fuels"]:
        c = fuels.get(f, {}).get("eur_mwh_incl_co2")
        row = {"fuel": f, "fuel_eur_mwh_incl_co2": c,
               "power_cost_gross": None, "power_cost_after_heat_credit": None}
        if c is not None:
            row["power_cost_gross"] = round(costs.chp_gross_power_cost(c, chp["eta_el"]), 1)
            if heat_credit is not None:
                row["power_cost_after_heat_credit"] = round(costs.chp_power_cost(
                    c, chp["eta_el"], chp["eta_heat"], heat_credit), 1)
        chp_rows.append(row)

    breakeven = (None if heat_only is None
                 else round(costs.e_boiler_breakeven_spot(heat_only, eb["adders_eur_mwh"], eb["eta"]), 1))

    return {
        "label": "Reference fuel prices (national averages, not TSE contract prices)",
        "eua": prices["eua"],
        "spot_eur_mwh": spot_eur_mwh,
        "fuels": {f: {k: v for k, v in d.items() if k != "history"} for f, d in fuels.items()},
        "history": {f: d["history"] for f, d in fuels.items() if d["history"]},
        "heat": {
            "heat_only_boiler_eur_mwh": None if heat_only is None else round(heat_only, 1),
            "electric_boiler_eur_mwh": None if eb_heat is None else round(eb_heat, 1),
            "cheapest": heat_credit_src,
            "e_boiler_cheaper_below_spot": breakeven,
        },
        "chp": {"unit": chp["label"], "heat_credit_eur_mwh":
                None if heat_credit is None else round(heat_credit, 1),
                "heat_credit_source": heat_credit_src, "by_fuel": chp_rows},
        "assumptions": {"NA4": {k: chp[k] for k in ("eta_el", "eta_heat")},
                        "EB": {k: eb[k] for k in ("eta", "adders_eur_mwh")},
                        "heat_only_boiler": hb, "placeholders": True},
        "errors": prices.get("errors", {}),
    }

"""Marginal cost arithmetic. Pure functions, no I/O.

Units: fuel prices EUR/MWh fuel, EUA EUR/tCO2, outputs EUR/MWh of product.
"""
from __future__ import annotations


def fuel_cost_with_co2(fuel_eur_mwh: float, ef_t_mwh: float, eua_eur_t: float) -> float:
    """Fuel + carbon cost per MWh of fuel input."""
    return fuel_eur_mwh + ef_t_mwh * eua_eur_t


def heat_only_cost(fuel_co2_eur_mwh: float, eta: float) -> float:
    """EUR per MWh heat from a heat-only boiler."""
    return fuel_co2_eur_mwh / eta


def e_boiler_heat_cost(spot_eur_mwh: float, adders_eur_mwh: float, eta: float) -> float:
    """EUR per MWh heat from an electric boiler at a given electricity price."""
    return (spot_eur_mwh + adders_eur_mwh) / eta


def chp_power_cost(fuel_co2_eur_mwh: float, eta_el: float, eta_heat: float,
                   heat_credit_eur_mwh: float) -> float:
    """Back-pressure CHP: net cost per MWh electricity after crediting the heat
    at the cost of the cheapest alternative heat source.

    C_el = (c_fuel - eta_heat * h_alt) / eta_el
    Negative means the heat alone pays for the fuel and power is "free".
    """
    return (fuel_co2_eur_mwh - eta_heat * heat_credit_eur_mwh) / eta_el


def chp_gross_power_cost(fuel_co2_eur_mwh: float, eta_el: float) -> float:
    """Condensing-equivalent cost per MWh electricity, no heat credit (upper bound)."""
    return fuel_co2_eur_mwh / eta_el


def e_boiler_breakeven_spot(heat_alt_eur_mwh: float, adders_eur_mwh: float, eta: float) -> float:
    """Spot price below which the e-boiler is the cheaper heat source."""
    return heat_alt_eur_mwh * eta - adders_eur_mwh

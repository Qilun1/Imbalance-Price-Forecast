"""Static assumptions for the fuel context panel.

Everything here is an editable placeholder until Turku Energia / TSE confirms
plant data. Efficiencies are net, on fuel input (LHV).
"""

# Statistics Finland PxWeb API (open data, CC BY 4.0, no key)
STATFI_BASE = "https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin/ehi/"

# Table 13p7: power plant fuel prices in electricity production, EUR/MWh fuel,
# monthly, tax-free (electricity production fuels are exempt from excise tax).
STATFI_POWER_TABLE = "13p7.px"
STATFI_POWER_TIME = "timeperiod_m"
STATFI_POWER_FUEL_DIM = "energia_47_20220101"
STATFI_POWER_FUELS = {"A": "natural_gas", "B": "coal", "C": "forest_chips", "D": "milled_peat"}
STATFI_POWER_CONTENT = "vl_polttoaine_hinta"

# Table 12gb: domestic fuel user prices in energy production, EUR/MWh, quarterly.
# Used as a fallback for chips/peat when 13p7 has a gap.
STATFI_DOMESTIC_TABLE = "12gb.px"
STATFI_DOMESTIC_TIME = "timeperiod_q"
STATFI_DOMESTIC_FUEL_DIM = "energia_27_20200611"
STATFI_DOMESTIC_FUELS = {"B": "milled_peat", "E": "forest_chips"}  # B = peat excl. excise tax
STATFI_DOMESTIC_CONTENT = "hinta_eur_mwh"
# Coal: 13p7 suppresses it and table 12he has no values after 2022M12, so there is
# no free public coal price. Enter it manually below (API2 Rotterdam is paid).

# CO2 emission factors, tCO2 per MWh fuel (Statistics Finland fuel
# classification defaults; biogenic CO2 counts as 0 under EU ETS).
# Check against the current classification before quoting numbers.
EMISSION_FACTOR_T_PER_MWH = {
    "forest_chips": 0.0,
    "milled_peat": 0.381,   # 105.9 t/TJ
    "coal": 0.341,          # 94.6 t/TJ
    "natural_gas": 0.198,   # ~55 t/TJ
    "heavy_fuel_oil": 0.284,  # 78.8 t/TJ
    "srf": 0.11,            # placeholder: depends on fossil share of the SRF
}

# Fuels without a public market price: manual EUR/MWh fuel. None = unknown.
MANUAL_FUEL_PRICE_EUR_MWH = {
    "srf": None,            # gate-fee fuel, can be negative; ask TSE
    "heavy_fuel_oil": None,  # start-up only
    "coal": None,           # reserve fuel only since NA3 closed (Dec 2024)
}

# EUA fallback when no API key is configured (EUR/tCO2). Update by hand.
EUA_MANUAL_EUR_T = 80.0
EUA_MANUAL_AS_OF = "2026-11-07"

# Naantali (TSE). NA4 multi-fuel CHP is treated as back-pressure:
# fuel F gives eta_el*F electricity and eta_heat*F heat.
UNITS = {
    "NA4": {
        "label": "Naantali NA4 multi-fuel CHP",
        "type": "chp",
        "fuels": ["forest_chips", "milled_peat", "srf", "coal"],
        "eta_el": 0.28,     # placeholder
        "eta_heat": 0.60,   # placeholder
    },
    "EB": {
        "label": "Naantali electric boilers (district heat)",
        "type": "electric_boiler",
        "eta": 0.99,
        # Grid fee + electricity tax class II + other variable costs, EUR/MWh_el.
        "adders_eur_mwh": 6.0,  # placeholder
    },
}

# Heat-only alternative used for the CHP heat credit when the e-boiler is dearer.
HEAT_ONLY_BOILER = {"fuel": "forest_chips", "eta": 0.88}

CACHE_TTL_S = 24 * 3600
HTTP_TIMEOUT_S = 20

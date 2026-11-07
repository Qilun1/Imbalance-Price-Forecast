"""Population centres used to weight NWP temperature for electricity demand.

Weights are approximate regional populations (Statistics Finland, regions, about 2024; rounded),
each represented by its largest city. Together they cover roughly 70 % of Finland's population.
A proxy for heating demand, not a census: only relative weights matter.
"""
from __future__ import annotations

import pandas as pd

# site_id, place, lat, lon, approximate regional population (thousands)
POP_CENTRES = [
    ("pop_helsinki", "Helsinki (Uusimaa)", 60.17, 24.94, 1750),
    ("pop_tampere", "Tampere (Pirkanmaa)", 61.50, 23.76, 530),
    ("pop_turku", "Turku (Varsinais-Suomi)", 60.45, 22.27, 490),
    ("pop_oulu", "Oulu (Pohjois-Pohjanmaa)", 65.01, 25.47, 420),
    ("pop_jyvaskyla", "Jyvaskyla (Keski-Suomi)", 62.24, 25.75, 280),
    ("pop_kuopio", "Kuopio (Pohjois-Savo)", 62.89, 27.68, 250),
    ("pop_lahti", "Lahti (Paijat-Hame)", 60.98, 25.66, 200),
]


def load_pop_sites() -> pd.DataFrame:
    return pd.DataFrame([{"site_id": s, "region": "pop", "place": p, "lat": la, "lon": lo, "capacity_mw": w}
                         for s, p, la, lo, w in POP_CENTRES])

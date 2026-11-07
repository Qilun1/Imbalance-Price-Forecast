"""Rebuild the imbalance price with Fingrid's 1 June 2026 volume-weighted rule from public inputs,
check it against the realised price after 1 June, and write a rebuilt target for earlier periods.

Rule (Fingrid, "Imbalance price in Finland 1.6.2026"): dominating direction from mFRR only.
- mFRR activated in the dominating direction: price = (VWA_aFRR * aFRR_volume + mFRR_price * mFRR_energy)
  / (aFRR_volume + mFRR_energy), both in the dominating direction.
- otherwise with a direction: max (up) / min (down) of mFRR marginal price and VWA aFRR price.
- no dominating direction: day-ahead price (left NaN here: we do not read spot in this tool).

Inputs: static_data/raw/fingrid_history/*.parquet from tools.ingest.fingrid_history.
Diagnostic only: the rebuilt series is never a feature; it is a candidate TARGET for pre-training.

    uv run python -m tools.eval.rebuild_price
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from imbalance.paths import REPO_ROOT, RAW_DIR

SRC = RAW_DIR / "fingrid_history"
OUT = REPO_ROOT / "static_data" / "processed" / "imbalance_rebuilt_hist.parquet"
NEW_RULE = pd.Timestamp("2026-06-01T00:00:00+03:00")    # local midnight, Helsinki


def load() -> pd.DataFrame:
    cols = {}
    for f in SRC.glob("*.parquet"):
        name = f.stem.split("_", 1)[1]
        s = pd.read_parquet(f).set_index("timestamp_utc")["value"]
        step = s.index.to_series().diff().median()
        # hourly data -> repeat for the four quarter-hours; finer -> quarter-hour mean
        s = s.resample("15min").ffill(limit=3) if step >= pd.Timedelta(hours=1) else s.resample("15min").mean()
        cols[name] = s
    return pd.DataFrame(cols).sort_index()


def rebuild(df: pd.DataFrame) -> pd.DataFrame:
    d = df["fi_mfrr_direction"]
    up, dn = d == 1, d == -1
    pick = lambda u, w: pd.Series(np.where(up, df[u], np.where(dn, df[w], np.nan)), df.index)
    mf = pick("fi_mfrr_up_price", "fi_mfrr_down_price")
    af = pick("fi_afrr_up_price", "fi_afrr_down_price")
    m_e = pick("fi_mfrr_up_activated", "fi_mfrr_down_activated").abs() * 0.25          # MW max -> MWh proxy
    a_v = pick("fi_afrr_up_volume", "fi_afrr_down_volume").abs() * 0.25 if "fi_afrr_up_volume" in df else None
    old = pd.Series(np.where(up, np.fmax(mf, af), np.where(dn, np.fmin(mf, af), np.nan)), df.index)
    out = pd.DataFrame({"direction": d, "mfrr_only": mf.where(d != 0), "old_rule": old})
    if a_v is not None:
        afv = a_v.fillna(0).where(af.notna(), 0)
        vwa = (af.fillna(0) * afv + mf * m_e) / (afv + m_e)
        out["new_rule"] = np.where(m_e > 0, vwa, old)
    out["actual"] = df.get("fi_imbalance_price")
    return out


def report(r: pd.DataFrame) -> None:
    for period, m in [("after 1 Jun 2026 (new rule)", r.index >= NEW_RULE), ("before 1 Jun 2026", r.index < NEW_RULE)]:
        x = r[m & r["actual"].notna() & (r["direction"] != 0)]
        print(f"\n{period}: {len(x):,} quarter-hours with a direction")
        for c in ["new_rule", "old_rule", "mfrr_only"]:
            if c in x:
                e = (x["actual"] - x[c]).abs()
                print(f"  {c:10s} exact (<0.02) {(e < 0.02).mean():6.1%}   within 1 EUR {(e < 1).mean():6.1%}   MAE {e.mean():7.2f}")


def main() -> None:
    df = load()
    r = rebuild(df)
    report(r)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    r.to_parquet(OUT)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

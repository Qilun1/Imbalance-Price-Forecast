import numpy as np, pandas as pd
import pathlib; U = str(pathlib.Path(__file__).resolve().parents[2])
act = pd.read_csv(f"{U}/static_data/raw/starter/actuals_validation.csv")
def load(n): return pd.read_csv(f"{U}/static_data/work/submissions/{n}-val_val.csv").merge(act, on="delivery_start_utc").dropna(subset=["imbalance_price", "spot_price"])
M, B = load("ens_finald"), load("baseline")
for d in (M, B): d["spread"] = d.imbalance_price - d.spot_price
WEEKS = 4.0  # validation length
ANN = 52 / WEEKS

def value(d, lead_step, thr, cost, mode="prob"):
    """1 MW of flexibility: raise output / cut load for the quarter-hour when P(spike high) >= thr (paid the spread),
    take load when P(spike low) >= thr (paid -spread). cost = EUR/MWh activation cost (efficiency, wear, heat rebalancing)."""
    x = d[d.step == lead_step]
    if mode == "prob":
        up, dn = x.p_spike_high >= thr, x.p_spike_low >= thr
    elif mode == "p50":   # act on the point forecast alone
        up, dn = x.p50 - x.spot_price > 50, x.p50 - x.spot_price < -50
    elif mode == "oracle":
        up, dn = x.spread > 50, x.spread < -50
    gain = np.where(up, x.spread - cost, 0) + np.where(dn, -x.spread - cost, 0)
    acts = int(up.sum() + dn.sum())
    hits = int(((up) & (x.spread > cost)).sum() + ((dn) & (-x.spread > cost)).sum())
    return gain.sum() * 0.25, acts, hits, len(x)

print("EUR per MW over the 4 validation weeks (x13 = per year); lead = hours ahead; cost = activation cost EUR/MWh")
for lead in (1, 2, 4):
    step = lead * 4 + 1
    for cost in (0, 20, 40):
        print(f"\nlead {lead} h, cost {cost}:")
        o = value(M, step, 0, cost, "oracle")
        print(f"  perfect foresight      {o[0]:8.0f}  acts {o[1]:4d}")
        for thr in (0.25, 0.3, 0.4, 0.5):
            v = value(M, step, thr, cost)
            print(f"  model, p>={thr:.2f}         {v[0]:8.0f}  acts {v[1]:4d} hits {v[2]:4d}  -> {v[0]*ANN/1000:6.1f} kEUR/MW/yr")
        b = value(B, step, 0.3, cost, "p50")
        print(f"  baseline (persistence) {b[0]:8.0f}  acts {b[1]:4d} hits {b[2]:4d}  -> {b[0]*ANN/1000:6.1f} kEUR/MW/yr")
        m2 = value(M, step, 0, cost, "p50")
        print(f"  model P50 only         {m2[0]:8.0f}  acts {m2[1]:4d} hits {m2[2]:4d}")

# Imbalance exposure view: a BRP whose own imbalance is e, settled at the imbalance price. Expected cost of 1 MWh imbalance
# = E|spread| when the sign is unknown. Knowing the direction lets you trade/adjust the side that costs.
x = M[M.step == 5]
print("\nMean |spread| (expected imbalance cost per MWh of uncorrected imbalance):", round(x.spread.abs().mean(), 1))
print("Mean spread when model says P(up)>=0.7:", round(x.loc[x.p_up >= 0.7, "spread"].mean(), 1), "n", int((x.p_up >= 0.7).sum()),
      "| when P(down)>=0.8:", round(x.loc[x.p_down >= 0.8, "spread"].mean(), 1), "n", int((x.p_down >= 0.8).sum()))

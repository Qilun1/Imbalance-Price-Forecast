import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams.update({"font.family": "Liberation Sans", "font.size": 12, "axes.edgecolor": "B0B0B0", "axes.spines.top": False, "axes.spines.right": False,
                 "axes.labelcolor": "#6E6E6E", "xtick.color": "#6E6E6E", "ytick.color": "#6E6E6E", "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlecolor": "#111111"})
O, O2, O3, O4, G, G2, K = "#D96C00", "#F59B00", "#F9C166", "#FDE6BF", "#B0B0B0", "#6E6E6E", "#111111"
import pathlib; U = str(pathlib.Path(__file__).resolve().parents[2])
act = pd.read_csv(f"{U}/static_data/raw/starter/actuals_validation.csv")
sub = pd.read_csv(f"{U}/static_data/work/submissions/ens_finald-val_val.csv")
m = sub.merge(act, on="delivery_start_utc").dropna(subset=["imbalance_price", "spot_price"]).reset_index(drop=True)
m["spread"] = m.imbalance_price - m.spot_price
m["err"] = (m.p50 - m.imbalance_price).abs()
out = f"{U}/docs/slides/img"
import os; os.makedirs(out, exist_ok=True)
def save(name): plt.tight_layout(); plt.savefig(f"{out}/{name}.png", dpi=200, facecolor="white"); plt.close()

# 1. Fan chart of one real origin: pick an origin with a spike in horizon and decent forecast
o = m.groupby("forecast_origin_utc")
cand = o.apply(lambda d: ((d.spread.abs() > 50).sum() >= 4) & (d.err.mean() < 45)).pipe(lambda s: s[s].index)
sel = None
for c in cand:
    d = m[m.forecast_origin_utc == c]
    if d.p_spike_high.max() > 0.35 or d.p_spike_low.max() > 0.35: sel = c; break
if sel is None: sel = cand[len(cand)//2]
d = m[m.forecast_origin_utc == sel].sort_values("step")
t = np.arange(1, 41) * 0.25
fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.6, 5.2), gridspec_kw={"height_ratios": [3, 1.1]}, sharex=True)
a1.fill_between(t, d.p10, d.p90, color=O3, alpha=0.6, label="P10–P90 band")
a1.plot(t, d.p50, color=O, lw=2.5, label="P50")
a1.plot(t, d.spot_price, color=G2, lw=1.5, ls="--", label="Spot (known)")
a1.plot(t, d.imbalance_price, color=K, lw=1.8, marker="o", ms=3.5, label="Actual")
a1.set_ylabel("EUR/MWh"); a1.set_ylim(-40, 260); a1.legend(loc="upper left", frameon=False, ncol=4, fontsize=10)
a1.set_title(f"One forecast, {pd.Timestamp(sel).strftime('%d %b %H:%M')} UTC, 40 quarter-hours ahead")
a2.bar(t - 0.06, d.p_spike_high * 100, width=0.11, color=O, label="P(spike high)")
a2.bar(t + 0.06, d.p_spike_low * 100, width=0.11, color=O3, label="P(spike low)")
a2.plot(t, d.p_up * 100, color=K, lw=1.2, label="P(up-regulation)")
a2.set_ylim(0, 100); a2.set_ylabel("%"); a2.set_xlabel("hours after forecast origin"); a2.legend(loc="upper left", frameon=False, ncol=3, fontsize=9)
save("fan")

# 2. Bimodal spread histogram colored by direction
fig, ax = plt.subplots(figsize=(6.2, 4.2))
bins = np.arange(-250, 255, 10)
for dirn, col, lab in (("down", O3, "down-regulation"), ("up", O, "up-regulation"), ("none", G, "no regulation")):
    ax.hist(act.loc[act.direction == dirn, "imbalance_price"] - act.loc[act.direction == dirn, "spot_price"], bins=bins, color=col, alpha=0.9, label=lab, stacked=False)
ax.axvline(-50, color=K, ls=":", lw=1); ax.axvline(50, color=K, ls=":", lw=1); ax.axvline(0, color=G2, lw=1)
ax.set_xlabel("imbalance price − spot, EUR/MWh (clipped ±250)"); ax.set_ylabel("quarter-hours"); ax.set_ylim(0, 480); ax.legend(frameon=False, loc="upper left")
ax.set_title("The spread is bimodal, the regulation direction picks the side")
save("hist")

# 3. Error decomposition
b = pd.cut(m.spread.abs(), [0, 10, 25, 50, 100, 200, 1e9], labels=["0–10", "10–25", "25–50", "50–100", "100–200", ">200"], include_lowest=True)
t2 = pd.DataFrame({"b": b, "err": m.err}).groupby("b", observed=True)["err"].agg(["count", "sum"])
rows, mae = t2["count"] / len(m) * 100, t2["sum"] / len(m)
fig, ax = plt.subplots(figsize=(6.2, 4.2))
x = np.arange(len(t2)); w = 0.38
ax.bar(x - w/2, rows, w, color=G, label="share of quarter-hours, %")
ax.bar(x + w/2, mae / mae.sum() * 100, w, color=O, label="share of P50 error (MAE), %")
for i in range(len(x)):
    ax.text(x[i] - w/2, rows.iloc[i] + 1, f"{rows.iloc[i]:.0f}", ha="center", fontsize=10, color=G2)
    ax.text(x[i] + w/2, (mae / mae.sum() * 100).iloc[i] + 1, f"{(mae/mae.sum()*100).iloc[i]:.0f}", ha="center", fontsize=10, color=O)
ax.set_xticks(x); ax.set_xticklabels(t2.index); ax.set_xlabel("|imbalance price − spot|, EUR/MWh"); ax.set_ylabel("%")
ax.set_ylim(0, 40); ax.legend(frameon=False, loc="upper left"); ax.set_title("25 % of quarter-hours carry 72 % of the P50 error")
save("decomp")

# 4. Reliability diagrams: spike high, spike low, p_up
def rel(ax, p, yobs, title, col):
    edges = np.linspace(0, 1, 11); idx = np.clip(np.digitize(p, edges) - 1, 0, 9)
    xs, ys, ns = [], [], []
    for i in range(10):
        s = idx == i
        if s.sum() >= 30: xs.append(p[s].mean()); ys.append(yobs[s].mean()); ns.append(s.sum())
    ax.plot([0, 100], [0, 100], color=G, ls="--", lw=1)
    ax.plot(np.array(xs) * 100, np.array(ys) * 100, color=col, marker="o", lw=2, ms=6)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.set_title(title); ax.set_xlabel("forecast probability, %"); ax.set_ylabel("observed frequency, %")
fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.6))
rel(axs[0], m.p_spike_high.values, (m.spread > 50).values.astype(float), "Spike high", O)
rel(axs[1], m.p_spike_low.values, (m.spread < -50).values.astype(float), "Spike low", O2)
rel(axs[2], m.p_up.values, (m.direction == "up").values.astype(float), "Up-regulation", K)
save("reliability")

# 5. Coverage and MAE by step, model vs baseline
base = pd.read_csv(f"{U}/static_data/work/submissions/baseline-val_val.csv").merge(act, on="delivery_start_utc").dropna(subset=["imbalance_price"])
m["hr"] = (m.step - 1) // 4 + 1; base["hr"] = (base.step - 1) // 4 + 1
cov = m.groupby("hr").apply(lambda d: ((d.imbalance_price >= d.p10) & (d.imbalance_price <= d.p90)).mean())
covb = base.groupby("hr").apply(lambda d: ((d.imbalance_price >= d.p10) & (d.imbalance_price <= d.p90)).mean())
maes = m.groupby("hr").err.mean(); maeb = base.groupby("hr").apply(lambda d: (d.p50 - d.imbalance_price).abs().mean())
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 3.6))
a1.plot(maes.index, maes.values, color=O, lw=2.5, marker="o", label="model"); a1.plot(maeb.index, maeb.values, color=G, lw=2, marker="o", label="baseline")
a1.axhline(46.6, color=O3, lw=1.5, ls="--"); a1.text(5.5, 48, "P50 = spot", color=O2, fontsize=10, ha="center")
a1.set_ylim(30, 72); a1.set_xlabel("hours ahead"); a1.set_ylabel("MAE, EUR/MWh"); a1.set_title("P50 error"); a1.legend(frameon=False, loc="lower right")
a2.plot(cov.index, cov.values * 100, color=O, lw=2.5, marker="o", label="model"); a2.plot(covb.index, covb.values * 100, color=G, lw=2, marker="o", label="baseline")
a2.axhline(80, color=K, lw=1, ls=":"); a2.text(1, 81.5, "target 80 %", fontsize=10)
a2.set_ylim(60, 90); a2.set_xlabel("hours ahead"); a2.set_ylabel("actuals inside band, %"); a2.set_title("P10–P90 coverage"); a2.legend(frameon=False, loc="lower left")
save("bystep")

# 6. SHAP stacked bars
groups = ["Physical forecasts", "Market state now", "Spot", "Cross-border", "Observed wind error", "Calendar"]
heads = ["Direction", "Up price 0–2 h", "Down price 0–2 h", "Up price 2–10 h", "Down price 2–10 h"]
V = np.array([[48, 17, 6, 36, 16], [19, 49, 29, 23, 10], [19, 17, 57, 20, 63], [5, 5, 6, 5, 8], [3, 9, 2, 7, 2], [6, 2, 1, 9, 1]], float)
cols = [O, O2, K, G, O3, G2]
fig, ax = plt.subplots(figsize=(8.6, 3.9))
left = np.zeros(5)
for g, c, v in zip(groups, cols, V):
    ax.barh(heads, v, left=left, color=c, label=g, height=0.65)
    for i, (l, x) in enumerate(zip(left, v)):
        if x >= 12: ax.text(l + x/2, i, f"{x:.0f}", ha="center", va="center", color="white" if c in (O, K, G2) else K, fontsize=10, fontweight="bold")
    left += v
ax.invert_yaxis(); ax.set_xlim(0, 100); ax.set_xlabel("share of |SHAP|, %"); ax.legend(frameon=False, ncol=3, fontsize=9, loc="lower center", bbox_to_anchor=(0.5, 1.0))
save("shap")

# 7. Availability lags
fig, ax = plt.subplots(figsize=(6.0, 3.6))
names = ["Real-time grid state\n(Fingrid 198, 177, 194, …)", "Measured wind (75)", "Other measured series", "MET Nordic 2.5 km", "ECMWF IFS 9 km"]
lag = [15, 60, 60, 120, 480]; meas = [4, None, None, 34, 408]
ax.barh(names, lag, color=[O, O3, G, O3, O3], height=0.6)
for i, (l, mm) in enumerate(zip(lag, meas)):
    ax.text(l + 8, i, f"{l} min" if l < 120 else f"{l//60} h", va="center", fontsize=11, color=K)
    if mm: ax.plot([mm], [i], marker="|", color=K, ms=16, mew=2)
ax.invert_yaxis(); ax.set_xscale("log"); ax.set_xlim(3, 1500); ax.set_xlabel("lag before use (log); | = measured publication delay"); ax.set_title("Rule lag vs. measured publication delay")
save("lags")

# 8. Classifier: hit vs false alarm
ev = ["Spike low", "Extreme > 170", "Spike high", "Direction flip", "Up episode"]
hit = [96, 78, 71, 29, 19]; far = [43, 34, 51, 33, 37]; base_r = [28, 25, 26, 41, 40]
fig, ax = plt.subplots(figsize=(6.2, 3.9)); x = np.arange(5); w = 0.27
ax.bar(x - w, hit, w, color=O, label="hit rate, % of events")
ax.bar(x, far, w, color=G, label="false alarms, % of alerts")
ax.bar(x + w, base_r, w, color=O4, edgecolor=O3, label="base rate, % of windows")
for i in range(5):
    ax.text(x[i] - w, hit[i] + 2, f"{hit[i]}", ha="center", fontsize=10, color=O, fontweight="bold")
ax.set_xticks(x); ax.set_xticklabels(ev, fontsize=10); ax.set_ylim(0, 110); ax.set_ylabel("%"); ax.legend(frameon=False, fontsize=9, loc="upper right")
ax.set_title("Event classifier, validation")
save("classifier")

# 9. Spike probability by hour of day vs observed
m["hour"] = (pd.to_datetime(m.delivery_start_utc) + pd.Timedelta(hours=2)).dt.hour
h = m.groupby("hour").agg(ph=("p_spike_high", "mean"), oh=("spread", lambda s: (s > 50).mean()), pl=("p_spike_low", "mean"), ol=("spread", lambda s: (s < -50).mean()))
fig, ax = plt.subplots(figsize=(6.2, 3.6))
ax.plot(h.index, h.oh * 100, color=O, lw=2.5, label="piikki ylös, toteuma"); ax.plot(h.index, h.ph * 100, color=O, lw=1.5, ls="--", label="piikki ylös, ennuste")
ax.plot(h.index, h.ol * 100, color=K, lw=2.5, label="piikki alas, toteuma"); ax.plot(h.index, h.pl * 100, color=K, lw=1.5, ls="--", label="piikki alas, ennuste")
ax.set_xlabel("tunti (Suomen aika)"); ax.set_ylabel("% varteista"); ax.set_xticks(range(0, 24, 3)); ax.legend(frameon=False, fontsize=9, ncol=2); ax.set_title("Piikit vuorokaudenajan mukaan: ennuste seuraa toteumaa")
save("hourly")
print("done", sel)

# 10. Economic value curve
M2 = m.copy()
Bv = pd.read_csv(f"{U}/static_data/work/submissions/baseline-val_val.csv").merge(act, on="delivery_start_utc").dropna(subset=["imbalance_price","spot_price"]); Bv["spread"] = Bv.imbalance_price - Bv.spot_price
ANN = 13
def val(x, cost, mode, thr=0.3):
    if mode == "prob": up, dn = x.p_spike_high >= thr, x.p_spike_low >= thr
    elif mode == "p50": up, dn = x.p50 - x.spot_price > 50, x.p50 - x.spot_price < -50
    else: up, dn = x.spread > cost, -x.spread > cost
    return (np.where(up, x.spread - cost, 0) + np.where(dn, -x.spread - cost, 0)).sum() * 0.25 * ANN / 1000
costs = np.arange(0, 45, 5)
fig, ax = plt.subplots(figsize=(6.6, 4.0))
x1 = M2[M2.step == 5]; b1 = Bv[Bv.step == 5]; x4 = M2[M2.step == 17]
ax.plot(costs, [val(x1, c, "oracle") for c in costs], color=K, lw=2, ls=":", label="perfect foresight")
ax.plot(costs, [val(x1, c, "prob") for c in costs], color=O, lw=3, marker="o", label="our model, 1 h ahead")
ax.plot(costs, [val(x4, c, "prob") for c in costs], color=O3, lw=2, marker="o", label="our model, 4 h ahead")
ax.plot(costs, [val(b1, c, "p50") for c in costs], color=G, lw=2, marker="o", label="persistence rule (baseline)")
ax.axhline(0, color=G2, lw=0.8); ax.set_xlabel("activation cost of the flexible MW, EUR/MWh"); ax.set_ylabel("kEUR per MW per year")
ax.set_title("Value of 1 MW of flexibility dispatched on the forecast"); ax.legend(frameon=False, fontsize=9)
save("value")

"""Model diagnostics (labelled diagnostics; official scores come only from score.py).

Writes PNG figures to static_data/work/diagnostics/ (gitignored):
  learning_curves.png     loss per boosting round, train vs validation, every output, per feature set
  data_size_curve.png     validation MAE / direction Brier vs weeks of training history
  shap_top_<model>.png    mean |SHAP| of the top features for the P50 spread, up and spike models
  shap_families.png       share of |SHAP| by feature family and lead hour (P50 and direction)
  calibration.png         reliability of p_up, p_spike_high, p_spike_low and P10-P90 coverage by hour

No figure shows spot prices (Nord Pool licence). Validation rows are the organiser's validation
period; models are the "-val" bundles trained on data published before it.
"""
from __future__ import annotations

import warnings

import lightgbm as lgb
warnings.filterwarnings("ignore", message=".*eval_set.*is deprecated")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from imbalance import forecasts  # noqa: E402
from imbalance.contract import SPIKE_MARGIN, VALIDATION_FIRST_ORIGIN  # noqa: E402
from imbalance.model import DEFAULT_CLF, DEFAULT_REG, QUANTILES, Bundle  # noqa: E402
from imbalance.paths import CONFIGS_DIR, STARTER_DATA_DIR, WORK_DIR  # noqa: E402
from tools.training.feature_table import load_feature_table  # noqa: E402

OUT = WORK_DIR / "diagnostics"
# reference palette (dataviz skill): slot 1 blue, slot 2 orange; neutral gray for the baseline/reference
COL = {"v1": "#2a78d6", "v2": "#eb6834", "ref": "#8a8984"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
# one fixed colour per feature family, in categorical slot order, used by every SHAP chart
FAMILIES = ["Spot / day-ahead price", "Weather (NWP)", "Fingrid day-ahead forecasts", "Imbalance price lags",
            "Balancing state (mFRR/aFRR)", "Neighbours and flows", "Consumption / production",
            "Lead time and calendar"]
FAMILY_COLOR = dict(zip(FAMILIES, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6",
                                   "#e34948"]))
FAMILY_COLOR["Other"] = "#8a8984"


def style():
    plt.rcParams.update({
        "figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
        "axes.titlecolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold", "axes.labelsize": 9,
        "xtick.color": INK2, "ytick.color": INK2, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False, "legend.fontsize": 8, "lines.linewidth": 2,
        "font.family": "DejaVu Sans",
    })


def feature_family(name: str) -> str:
    if name.startswith("nwp_"):
        return "Weather (NWP)"
    if name.startswith(("spot", "spot_")) or name in ("spot",):
        return "Spot / day-ahead price"
    if name.startswith(("spread_", "imb_")):
        return "Imbalance price lags"
    if name.startswith(("dir_", "mfrr_", "afrr_")):
        return "Balancing state (mFRR/aFRR)"
    if name in ("wind_fc", "cons_fc", "solar_fc", "wind_fc_ramp", "resid_load_fc", "wind_fc_change_vs_lag",
                "cons_fc_vs_last_cons", "wind_fc_at_lag"):
        return "Fingrid day-ahead forecasts"
    if name.startswith(("se1_", "se3_", "ee_", "no4_", "net_export", "cap_", "se3imb")):
        return "Neighbours and flows"
    if name.startswith(("cons_", "net_pos", "prod_")):
        return "Consumption / production"
    if name in ("step", "lead_min", "data_age_min", "hour_local", "weekday", "holiday", "quarter"):
        return "Lead time and calendar"
    return "Other"


def _split(feature_set: str):
    t = load_feature_table(feature_set).dropna(subset=["y_spread", "y_dir"])
    train = t[t["y_target_fu"] <= VALIDATION_FIRST_ORIGIN]
    val = t[t["forecast_origin_utc"] >= VALIDATION_FIRST_ORIGIN]
    val = val[val["delivery_start_utc"] <= pd.Timestamp("2026-10-04T20:45:00Z")]
    return train, val


def _targets(df):
    return {"q10": df["y_spread"], "q50": df["y_spread"], "q90": df["y_spread"],
            "up": (df["y_dir"] == 1).astype(int), "spike_high": (df["y_spread"] > SPIKE_MARGIN).astype(int),
            "spike_low": (df["y_spread"] < -SPIKE_MARGIN).astype(int)}


def learning_curves(sets=("v1", "v2")):
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    titles = {"q10": "P10 spread (pinball)", "q50": "P50 spread (pinball)", "q90": "P90 spread (pinball)",
              "up": "Up-regulation (log loss)", "spike_high": "High spike (log loss)", "spike_low": "Low spike (log loss)"}
    for fs in sets:
        train, val = _split(fs)
        cfg = yaml.safe_load((CONFIGS_DIR / f"lgbm_{fs}.yaml").read_text())
        cols = [c for c in train.columns if not c.startswith("y_") and c not in
                ("forecast_origin_utc", "delivery_start_utc", "data_cutoff_utc")]
        ytr, yva = _targets(train), _targets(val)
        for ax, key in zip(axes.flat, titles):
            hist = {}
            if key in QUANTILES:
                p = {**DEFAULT_REG, **cfg.get("regressor", {})}
                m = lgb.LGBMRegressor(objective="quantile", alpha=QUANTILES[key], **p)
                metric = "quantile"
            else:
                p = {**DEFAULT_CLF, **cfg.get("classifier", {})}
                m = lgb.LGBMClassifier(**p)
                metric = "binary_logloss"
            m.fit(train[cols], ytr[key], eval_set=[(train[cols], ytr[key]), (val[cols], yva[key])],
                  eval_names=["train", "val"], eval_metric=metric, callbacks=[lgb.record_evaluation(hist)])
            mk = metric if metric in hist["val"] else list(hist["val"])[0]
            it = np.arange(1, len(hist["val"][mk]) + 1)
            ax.plot(it, hist["train"][mk], color=COL[fs], linestyle=(0, (4, 3)), linewidth=1.5, label=f"{fs} train")
            ax.plot(it, hist["val"][mk], color=COL[fs], label=f"{fs} validation")
            best = int(np.argmin(hist["val"][mk])) + 1
            ax.plot([best], [hist["val"][mk][best - 1]], "o", color=COL[fs], markersize=6,
                    markeredgecolor=SURF, markeredgewidth=2)
            ax.set_title(titles[key]); ax.set_xlabel("Boosting rounds")
    axes.flat[0].legend(loc="upper right")
    fig.suptitle("Learning curves: dashed = training, solid = validation; dot = best validation round",
                 color=INK, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "learning_curves.png", dpi=140)
    plt.close(fig)


def data_size_curve(sets=("v1", "v2"), weeks=(2, 4, 6, 8, 10, 12, 14)):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for fs in sets:
        train, val = _split(fs)
        cols = [c for c in train.columns if not c.startswith("y_") and c not in
                ("forecast_origin_utc", "delivery_start_utc", "data_cutoff_utc")]
        cfg = yaml.safe_load((CONFIGS_DIR / f"lgbm_{fs}.yaml").read_text())
        mae, bri = [], []
        y_dir = val["y_dir"].to_numpy()
        for w in weeks:
            tr = train[train["forecast_origin_utc"] >= VALIDATION_FIRST_ORIGIN - pd.Timedelta(weeks=w)]
            q = lgb.LGBMRegressor(objective="quantile", alpha=0.5, **{**DEFAULT_REG, **cfg.get("regressor", {})})
            q.fit(tr[cols], tr["y_spread"])
            mae.append(np.mean(np.abs(q.predict(val[cols]) - val["y_spread"])))
            c = lgb.LGBMClassifier(**{**DEFAULT_CLF, **cfg.get("classifier", {})}).fit(tr[cols], (tr["y_dir"] == 1).astype(int))
            p_none = float(np.clip((tr["y_dir"] == 0).mean(), 0.001, 0.05))
            pu = (1 - p_none) * c.predict_proba(val[cols])[:, 1]
            pdn = 1 - pu - p_none
            bri.append(np.mean((pu - (y_dir == 1)) ** 2 + (pdn - (y_dir == -1)) ** 2 + (p_none - (y_dir == 0)) ** 2))
        axes[0].plot(weeks, mae, "-o", color=COL[fs], markersize=6, markeredgecolor=SURF, markeredgewidth=2, label=fs)
        axes[1].plot(weeks, bri, "-o", color=COL[fs], markersize=6, markeredgecolor=SURF, markeredgewidth=2, label=fs)
    axes[0].set_title("Validation MAE of P50 (EUR/MWh)"); axes[1].set_title("Validation direction Brier")
    for ax in axes:
        ax.set_xlabel("Weeks of training history before 7 Sep")
    axes[0].legend()
    fig.suptitle("Does more history help? (diagnostic, own recomputation)", color=INK, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "data_size_curve.png", dpi=140)
    plt.close(fig)


def _shap(bundle: Bundle, X: pd.DataFrame, key: str) -> pd.DataFrame:
    c = bundle.boosters[key].predict(X[bundle.features], pred_contrib=True)[:, :-1]
    return pd.DataFrame(c, columns=bundle.features, index=X.index)


def _ensure_val(name: str) -> None:
    """Train the -val model and infer the validation period if this clone does not have it yet
    (backend/artifacts is gitignored, so a fresh clone has no models)."""
    import argparse
    from imbalance.paths import ARTIFACTS_DIR
    from tools import cli
    base = name.removesuffix("-val")
    fs = "v2" if "v2" in base else "v1"
    if not (ARTIFACTS_DIR / name / "meta.json").exists():
        print(f"{name} missing: training it (validation mode)")
        cli.cmd_train(argparse.Namespace(config=str(CONFIGS_DIR / f"{base}.yaml"), mode="val"))
    if forecasts.read(name).empty:
        print(f"{name}: no validation forecasts yet, running inference")
        cli.cmd_infer(argparse.Namespace(model=name, period="val", set=fs))


def shap_plots(models=("lgbm_v1-val", "lgbm_v2-val"), top=15):
    fam_frames = {}
    for name in models:
        _ensure_val(name)
        b = Bundle.load(name)
        _, val = _split(b.meta.get("feature_set", "v1"))
        X = val.sample(min(len(val), 12000), random_state=0)
        fig, axes = plt.subplots(1, 3, figsize=(15, 5.5))
        for ax, key, title in zip(axes, ["q50", "up", "spike_high"],
                                  ["P50 spread (EUR/MWh)", "Up-regulation (log-odds)", "High spike (log-odds)"]):
            s = _shap(b, X, key).abs().mean().sort_values(ascending=True).tail(top)
            colors = [FAMILY_COLOR[feature_family(f)] for f in s.index]
            ax.barh(range(len(s)), s.values, color=colors, height=0.7)
            ax.set_yticks(range(len(s))); ax.set_yticklabels(s.index, fontsize=8)
            ax.set_title(title); ax.set_xlabel("mean |SHAP|"); ax.grid(axis="y", visible=False)
        present = [f for f in FAMILIES + ["Other"] if any(feature_family(x) == f for x in b.features)]
        handles = [plt.Rectangle((0, 0), 1, 1, color=FAMILY_COLOR[f]) for f in present]
        fig.legend(handles, present, loc="lower center", ncol=5, fontsize=8)
        fig.suptitle(f"What {name} uses: top {top} features by mean |SHAP| on validation", color=INK, fontsize=12,
                     x=0.01, ha="left")
        fig.tight_layout(rect=(0, 0.07, 1, 1))
        fig.savefig(OUT / f"shap_top_{name}.png", dpi=140)
        plt.close(fig)
        fam_frames[name] = (b, X)

    # family share by lead hour (last model, normally v2)
    name = models[-1]
    b, X = fam_frames[name]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, key, title in zip(axes, ["q50", "up"], ["P50 spread", "Up-regulation probability"]):
        s = _shap(b, X, key).abs()
        s["hour"] = ((X["step"] - 1) // 4 + 1).to_numpy()
        g = s.groupby("hour").mean()
        fam = g.T.groupby(feature_family).sum().T
        fam = fam.div(fam.sum(axis=1), axis=0)
        order = [f for f in FAMILIES + ["Other"] if f in fam.columns]
        bottom = np.zeros(len(fam))
        for f in order:
            ax.bar(fam.index, fam[f], bottom=bottom, color=FAMILY_COLOR[f], width=0.75,
                   edgecolor=SURF, linewidth=1.5, label=f)
            bottom += fam[f].to_numpy()
        ax.set_title(f"{title}: share of |SHAP| by family"); ax.set_xlabel("Lead hour"); ax.set_xticks(fam.index)
        ax.set_ylim(0, 1); ax.grid(axis="x", visible=False)
    h, lab = axes[1].get_legend_handles_labels()
    axes[1].legend(h[::-1], lab[::-1], loc="center left", bbox_to_anchor=(1.01, 0.5))
    fig.suptitle(f"How {name}'s drivers shift with lead time (validation)", color=INK, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "shap_families.png", dpi=140)
    plt.close(fig)


def calibration(models=("lgbm_v1-val", "lgbm_v2-val")):
    act = pd.read_csv(STARTER_DATA_DIR / "actuals_validation.csv")
    fig, axes = plt.subplots(1, 4, figsize=(17, 4.2))
    for name in models:
        _ensure_val(name)
        fs = "v2" if "v2" in name else "v1"
        fc = forecasts.read(name)
        fc["delivery_start_utc"] = fc["delivery_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        d = fc.merge(act, on="delivery_start_utc").dropna(subset=["imbalance_price"])
        y, sp = d["imbalance_price"], d["spot_price"]          # used in memory only, never plotted
        for ax, p, obs, title in [
            (axes[0], d["p_up"], d["direction"] == "up", "p_up"),
            (axes[1], d["p_spike_high"], y > sp + SPIKE_MARGIN, "p_spike_high"),
            (axes[2], d["p_spike_low"], y < sp - SPIKE_MARGIN, "p_spike_low"),
        ]:
            bins = np.linspace(0, 1, 11)
            idx = np.clip(np.digitize(p, bins) - 1, 0, 9)
            g = pd.DataFrame({"b": idx, "p": p, "o": obs.astype(float)}).groupby("b").agg(p=("p", "mean"), o=("o", "mean"), n=("o", "size"))
            g = g[g["n"] >= 30]
            ax.plot(g["p"], g["o"], "-o", color=COL[fs], markersize=6, markeredgecolor=SURF, markeredgewidth=2, label=fs)
            ax.set_title(f"Reliability: {title}"); ax.set_xlabel("Forecast probability"); ax.set_ylabel("Observed frequency")
        d["hour"] = (d["step"] - 1) // 4 + 1
        cov = d.assign(inside=(y >= d["p10"]) & (y <= d["p90"])).groupby("hour")["inside"].mean()
        axes[3].plot(cov.index, cov.values, "-o", color=COL[fs], markersize=6, markeredgecolor=SURF, markeredgewidth=2, label=fs)
    for ax in axes[:3]:
        ax.plot([0, 1], [0, 1], color=COL["ref"], linewidth=1, linestyle=(0, (3, 3)))
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    axes[3].axhline(0.8, color=COL["ref"], linewidth=1, linestyle=(0, (3, 3)))
    axes[3].set_title("P10-P90 coverage by lead hour"); axes[3].set_xlabel("Lead hour"); axes[3].set_ylim(0.6, 0.9)
    axes[0].legend(loc="upper left")
    fig.suptitle("Calibration on validation (dashed = perfect / 80 % target)", color=INK, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "calibration.png", dpi=140)
    plt.close(fig)


def run(which=("learning", "datasize", "shap", "calibration")):
    style()
    OUT.mkdir(parents=True, exist_ok=True)
    if "learning" in which:
        learning_curves(); print("learning_curves.png")
    if "datasize" in which:
        data_size_curve(); print("data_size_curve.png")
    if "shap" in which:
        shap_plots(); print("shap_top_*.png, shap_families.png")
    if "calibration" in which:
        calibration(); print("calibration.png")
    print(f"-> {OUT}")

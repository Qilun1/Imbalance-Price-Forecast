"""Event classifiers: P(event in window | inputs at the origin), with an uncertainty interval.

One classifier per event, the windows pooled (window_idx is an input). Each event uses the model
family that won on validation (tools/training/alert_train.py --evaluate):
  lgbm    regularised LightGBM on every input
  logreg  L2 logistic regression on every input (median-imputed, standardised)
  mlp     small MLP (2 x 64, ReLU, weight decay, early stopping) on the same inputs
  rule    logistic regression on the base forecast's own summary for that event: the honest baseline

Calibration is cross-fitted Venn-Abers (Vovk & Petej 2014): out-of-fold scores from time-blocked folds
(with an embargo, since windows reach 10 h ahead) fit two isotonic regressions per score, giving a
probability interval [p_lo, p_hi]. p = p_hi / (1 - p_lo + p_hi). A wide interval means few similar
cases in training.

A bundle lives in backend/artifacts/<name>/: <event>.txt (LightGBM boosters) and meta.json (family,
inputs, calibration grid, linear/MLP weights, base rates and default thresholds), the only formats
AGENTS.md allows us to commit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier

from .events import EVENT_IDS, WINDOWS
from .paths import ARTIFACTS_DIR

FAMILIES = ("lgbm", "logreg", "mlp", "rule")
LGBM_PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=100, subsample=0.8,
                   subsample_freq=1, colsample_bytree=0.5, reg_lambda=1.0, verbose=-1, random_state=0)
# The base forecast's own summary per event, for the rule baseline (plus window_idx).
RULE_INPUTS = {
    "spike_high": ["b_union_spike_high", "b_max_p_spike_high"],
    "spike_low": ["b_union_spike_low", "b_max_p_spike_low"],
    "up_episode": ["b_p_up_mean", "b_p_up_max"],
    "direction_flip": ["b_p_up_mean", "f_dir_last"],
    "extreme_price": ["b_max_p90", "b_p50_max"],
    "deep_negative": ["b_min_p10", "b_p50_min"],
    "large_up_activation": ["b_p_up_max", "b_p_up_mean"],
    "large_down_activation": ["b_p_up_min", "b_p_up_mean"],
    "forecast_miss": ["b_max_width", "gap_p50_max"],
}
DEFAULT_THRESHOLD_FACTOR = 1.5      # default threshold = 1.5 x training base rate (cost-loss ratio above
DEFAULT_THRESHOLD_CAP = 0.6         # climatology, Roulston & Smith), capped; users can change it
EMBARGO = pd.Timedelta(hours=12)    # gap between a fold's training and held-out origins
N_FOLDS = 4

DRIVER_FAMILIES = [
    ("window_", "How far ahead"), ("gap_", "Disagreement between models"), ("rev_", "Change since the previous forecast"),
    ("b_", "Price forecast"), ("nwp_temp", "Temperature"), ("mfrr", "Recent balancing"),
    ("afrr", "Recent balancing"), ("_imb_mean4", "Neighbour imbalance prices"),
    ("se3imb", "Neighbour imbalance prices"), ("wind", "Wind"), ("nwp", "Wind"),
    ("spot", "Spot price shape"), ("flow", "Cross-border flows"), ("export", "Cross-border flows"),
    ("cap_", "Cross-border flows"), ("imb_", "Recent balancing"), ("spread", "Recent balancing"),
    ("dir_", "Recent balancing"), ("data_age", "Data freshness"),
    ("lead_min", "Data freshness"), ("cons", "Load and production"), ("prod", "Load and production"),
    ("net_pos", "Load and production"), ("resid_load", "Load and production"), ("solar", "Load and production"),
    ("hour", "Time of day"), ("weekday", "Time of day"), ("holiday", "Time of day"), ("quarter", "Time of day"),
    ("origin_", "Time of day"),
]


def driver_family(column: str) -> str:
    name = column
    for prefix in ("fmax_", "fmin_", "f_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    for key, family in DRIVER_FAMILIES:
        # Keys ending in "_" are prefixes; the others match anywhere in the name.
        if (name.startswith(key) if key.endswith("_") else key in name):
            return family
    return "Other"


# ---------------------------------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------------------------------
@dataclass
class VennAbers:
    """Inductive Venn-Abers on a grid of scores (interpolated between grid points)."""
    grid: np.ndarray
    p0: np.ndarray
    p1: np.ndarray

    @classmethod
    def fit(cls, scores: np.ndarray, y: np.ndarray, n_grid: int = 200) -> "VennAbers":
        scores, y = np.asarray(scores, float), np.asarray(y, float)
        grid = np.unique(np.quantile(scores, np.linspace(0, 1, n_grid)))
        p0, p1 = np.empty(len(grid)), np.empty(len(grid))
        for i, g in enumerate(grid):
            for label, out in ((0.0, p0), (1.0, p1)):
                iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip")
                iso.fit(np.r_[scores, g], np.r_[y, label])
                out[i] = iso.predict([g])[0]
        return cls(grid, p0, p1)

    def predict(self, scores: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        lo = np.interp(scores, self.grid, self.p0)
        hi = np.interp(scores, self.grid, self.p1)
        return hi / (1 - lo + hi), lo, hi

    def to_json(self) -> dict:
        return {"grid": self.grid.tolist(), "p0": self.p0.tolist(), "p1": self.p1.tolist()}

    @classmethod
    def from_json(cls, d: dict) -> "VennAbers":
        return cls(np.array(d["grid"]), np.array(d["p0"]), np.array(d["p1"]))


# ---------------------------------------------------------------------------------------------------
# Model families
# ---------------------------------------------------------------------------------------------------
@dataclass
class Scorer:
    """A fitted model of one family that turns inputs into an uncalibrated score in [0, 1]."""
    family: str
    inputs: list[str]
    booster: lgb.Booster | None = None
    linear: dict = field(default_factory=dict)      # medians, mean, scale, layers (weights and biases)

    @classmethod
    def fit(cls, family: str, X: pd.DataFrame, y: np.ndarray, event: str) -> "Scorer":
        inputs = (RULE_INPUTS[event] + ["window_idx"]) if family == "rule" else list(X.columns)
        if family == "lgbm":
            model = lgb.LGBMClassifier(**LGBM_PARAMS).fit(X[inputs], y)
            return cls(family, inputs, booster=model.booster_)
        A = X[inputs].to_numpy(float)
        med = np.nanmedian(A, axis=0)
        med = np.where(np.isnan(med), 0.0, med)
        A = np.where(np.isnan(A), med, A)
        mean, scale = A.mean(axis=0), A.std(axis=0)
        scale = np.where(scale > 0, scale, 1.0)
        Z = (A - mean) / scale
        if family == "mlp":
            m = MLPClassifier(hidden_layer_sizes=(64, 64), alpha=1e-2, early_stopping=True, validation_fraction=0.15,
                              max_iter=300, random_state=0).fit(Z, y)
            layers = [{"w": w.tolist(), "b": b.tolist()} for w, b in zip(m.coefs_, m.intercepts_)]
        else:
            m = LogisticRegression(C=0.1 if family == "logreg" else 1.0, max_iter=5000).fit(Z, y)
            layers = [{"w": m.coef_.T.tolist(), "b": m.intercept_.tolist()}]
        return cls(family, inputs, linear={"median": med.tolist(), "mean": mean.tolist(), "scale": scale.tolist(),
                                           "layers": layers})

    def _z(self, X: pd.DataFrame) -> np.ndarray:
        A = X[self.inputs].to_numpy(float)
        A = np.where(np.isnan(A), np.array(self.linear["median"]), A)
        return (A - np.array(self.linear["mean"])) / np.array(self.linear["scale"])

    def score(self, X: pd.DataFrame) -> np.ndarray:
        if self.booster is not None:
            return self.booster.predict(X[self.inputs])
        h = self._z(X)
        layers = self.linear["layers"]
        for i, layer in enumerate(layers):
            h = h @ np.array(layer["w"]) + np.array(layer["b"])
            if i < len(layers) - 1:
                h = np.maximum(h, 0.0)
        return 1 / (1 + np.exp(-h[:, 0]))

    def contributions(self, X: pd.DataFrame) -> pd.DataFrame | None:
        """Per-input contribution to the log-odds (TreeSHAP for LightGBM, coefficient x value for the
        linear families); None for the MLP."""
        if self.booster is not None:
            c = self.booster.predict(X[self.inputs], pred_contrib=True)[:, :-1]
        elif self.family in ("logreg", "rule"):
            c = self._z(X) * np.array(self.linear["layers"][0]["w"])[:, 0]
        else:
            return None
        return pd.DataFrame(c, columns=self.inputs, index=X.index)


def time_folds(origins: pd.Series, n_folds: int = N_FOLDS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Contiguous blocks of origins; each fold's training rows exclude origins within EMBARGO of its block."""
    unique = np.sort(origins.unique())
    out = []
    for block in np.array_split(unique, n_folds):
        lo, hi = block[0], block[-1]
        held = origins.between(lo, hi).to_numpy()
        train = ((origins < lo - EMBARGO) | (origins > hi + EMBARGO)).to_numpy()
        out.append((train, held))
    return out


@dataclass
class EventModel:
    event: str
    scorer: Scorer
    calibration: VennAbers
    base_rate: dict[str, float]
    threshold: dict[str, float]

    @classmethod
    def fit(cls, family: str, X: pd.DataFrame, y: np.ndarray, origins: pd.Series, windows: pd.Series,
            event: str) -> "EventModel":
        oof = np.full(len(y), np.nan)
        for train, held in time_folds(origins):
            if y[train].min() == y[train].max():
                continue
            oof[held] = Scorer.fit(family, X[train], y[train], event).score(X[held])
        ok = ~np.isnan(oof)
        calibration = VennAbers.fit(oof[ok], y[ok])
        rate = pd.Series(y).groupby(windows.to_numpy()).mean()
        base_rate = {w: float(rate.get(w, np.nan)) for w in WINDOWS}
        threshold = {w: float(min(DEFAULT_THRESHOLD_CAP, DEFAULT_THRESHOLD_FACTOR * r)) for w, r in base_rate.items()}
        return cls(event, Scorer.fit(family, X, y, event), calibration, base_rate, threshold)

    def predict(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.calibration.predict(self.scorer.score(X))


@dataclass
class AlertBundle:
    name: str
    inputs: list[str]
    models: dict[str, EventModel]
    meta: dict = field(default_factory=dict)

    @classmethod
    def train(cls, name: str, table: pd.DataFrame, inputs: list[str], families: dict[str, str],
              label_of: dict[str, str], extra_meta: dict | None = None) -> "AlertBundle":
        models = {}
        for event in EVENT_IDS:
            rows = table[table[label_of[event]].notna()].reset_index(drop=True)
            y = rows[label_of[event]].to_numpy(int)
            models[event] = EventModel.fit(families[event], rows[inputs], y, rows["forecast_origin_utc"],
                                           rows["window"], event)
            print(f"  {event:22s} {families[event]:6s} rows {len(rows):5d} positives {y.mean():.3f}")
        meta = {"name": name, "trained_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "last_origin_utc": table["forecast_origin_utc"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
                **(extra_meta or {})}
        return cls(name, inputs, models, meta)

    def predict(self, X: pd.DataFrame, n_drivers: int = 3) -> pd.DataFrame:
        """Long table: forecast_origin_utc, window, event, p, p_lo, p_hi, base_rate, lift, threshold, drivers."""
        frames = []
        for event, m in self.models.items():
            p, lo, hi = m.predict(X)
            base = X["window"].map(m.base_rate).to_numpy(float)
            frame = pd.DataFrame({"forecast_origin_utc": X["forecast_origin_utc"].to_numpy(),
                                  "window": X["window"].to_numpy(), "event": event, "p": p, "p_lo": lo, "p_hi": hi,
                                  "base_rate": base, "lift": p / np.maximum(base, 1e-6),
                                  "threshold": X["window"].map(m.threshold).to_numpy(float)})
            frame["drivers"] = self._drivers(m.scorer, X, n_drivers)
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _drivers(scorer: Scorer, X: pd.DataFrame, n: int) -> list[str]:
        """Families whose inputs push the probability up the most (correlated inputs are summed by family)."""
        contrib = scorer.contributions(X)
        if contrib is None:
            return [""] * len(X)
        by_family = contrib.T.groupby([driver_family(c) for c in contrib.columns]).sum().T
        names = by_family.columns.to_numpy()
        values = by_family.to_numpy()
        out = []
        for row in values:
            top = [names[i] for i in np.argsort(-row)[:n] if row[i] > 0]
            out.append(";".join(top))
        return out

    # ---------- persistence ----------
    def save(self, root: Path = ARTIFACTS_DIR) -> Path:
        d = root / self.name
        d.mkdir(parents=True, exist_ok=True)
        events = {}
        for event, m in self.models.items():
            if m.scorer.booster is not None:
                m.scorer.booster.save_model(str(d / f"{event}.txt"))
            events[event] = {"family": m.scorer.family, "inputs": m.scorer.inputs, "linear": m.scorer.linear,
                             "calibration": m.calibration.to_json(), "base_rate": m.base_rate,
                             "threshold": m.threshold}
        (d / "meta.json").write_text(json.dumps({**self.meta, "inputs": self.inputs, "events": events}, indent=1))
        return d

    @classmethod
    def load(cls, name: str, root: Path = ARTIFACTS_DIR) -> "AlertBundle":
        d = root / name
        meta = json.loads((d / "meta.json").read_text())
        events = meta.pop("events")
        inputs = meta.pop("inputs")
        models = {}
        for event, e in events.items():
            booster = lgb.Booster(model_file=str(d / f"{event}.txt")) if e["family"] == "lgbm" else None
            scorer = Scorer(e["family"], e["inputs"], booster=booster, linear=e["linear"])
            models[event] = EventModel(event, scorer, VennAbers.from_json(e["calibration"]), e["base_rate"],
                                       e["threshold"])
        return cls(name, inputs, models, meta)

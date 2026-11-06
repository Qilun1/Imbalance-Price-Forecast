"""Model bundle: train, save, load and predict all submission outputs.

A bundle lives in backend/artifacts/<name>/:
  meta.json          config, feature list, training cutoff, calibration constants
  <output>.txt       one LightGBM booster per output (q10, q50, q90, up, spike_high, spike_low)

predict() returns the eight forecast columns plus top_drivers, already consistent with the
organiser's rules (p10 <= p50 <= p90, direction sums to 1, spike sum <= 1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .contract import SPIKE_MARGIN
from .features import feature_columns
from .paths import ARTIFACTS_DIR

QUANTILES = {"q10": 0.1, "q50": 0.5, "q90": 0.9}
CLASSIFIERS = ("up", "spike_high", "spike_low")

DEFAULT_REG = dict(n_estimators=500, learning_rate=0.03, num_leaves=31, min_child_samples=200,
                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
DEFAULT_CLF = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=200,
                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)


@dataclass
class Bundle:
    name: str
    features: list[str]
    meta: dict = field(default_factory=dict)
    boosters: dict[str, lgb.Booster] = field(default_factory=dict)

    # ---------- training ----------
    @classmethod
    def train(cls, name: str, train_df: pd.DataFrame, config: dict) -> "Bundle":
        cols = config.get("features") or feature_columns(train_df)
        reg = {**DEFAULT_REG, **config.get("regressor", {})}
        clf = {**DEFAULT_CLF, **config.get("classifier", {})}
        X = train_df[cols]
        b = cls(name=name, features=cols)
        for key, q in QUANTILES.items():
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, **reg).fit(X, train_df["y_spread"])
            b.boosters[key] = m.booster_
        targets = {
            "up": (train_df["y_dir"] == 1).astype(int),
            "spike_high": (train_df["y_spread"] > SPIKE_MARGIN).astype(int),
            "spike_low": (train_df["y_spread"] < -SPIKE_MARGIN).astype(int),
        }
        for key, y in targets.items():
            b.boosters[key] = lgb.LGBMClassifier(**clf).fit(X, y).booster_
        b.meta = {
            "name": name,
            "feature_set": config.get("feature_set", "v1"),
            "widen": float(config.get("widen", 1.0)),
            "p_none": float(np.clip((train_df["y_dir"] == 0).mean(), 0.001, 0.05)),
            "train_rows": int(len(train_df)),
            "train_last_delivery_utc": train_df["delivery_start_utc"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "trained_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "config": config,
        }
        return b

    # ---------- inference ----------
    def predict(self, df: pd.DataFrame, n_drivers: int = 3) -> pd.DataFrame:
        X = df[self.features]
        spot = df["spot"].to_numpy()
        q = np.column_stack([self.boosters[k].predict(X) for k in QUANTILES])
        q = np.sort(q, axis=1)
        w = self.meta.get("widen", 1.0)
        mid = q[:, 1]
        out = pd.DataFrame(index=df.index)
        out["p10"] = spot + mid - w * (mid - q[:, 0])
        out["p50"] = spot + mid
        out["p90"] = spot + mid + w * (q[:, 2] - mid)

        p_none = self.meta["p_none"]
        up = self.boosters["up"].predict(X)
        out["p_up"] = (1 - p_none) * up
        out["p_none"] = p_none
        out["p_down"] = 1 - out["p_up"] - out["p_none"]

        hi, lo = self.boosters["spike_high"].predict(X), self.boosters["spike_low"].predict(X)
        scale = np.where(hi + lo > 0.999, 0.999 / np.maximum(hi + lo, 1e-12), 1.0)
        out["p_spike_high"], out["p_spike_low"] = hi * scale, lo * scale
        out["top_drivers"] = self.drivers(X, n_drivers)
        return out[["p10", "p50", "p90", "p_up", "p_down", "p_none", "p_spike_high", "p_spike_low",
                    "top_drivers"]]

    def drivers(self, X: pd.DataFrame, n: int) -> pd.Series:
        """Features with the largest absolute SHAP contribution to the P50 spread, per row."""
        contrib = self.boosters["q50"].predict(X, pred_contrib=True)[:, :-1]
        top = np.argsort(-np.abs(contrib), axis=1)[:, :n]
        names = np.array(self.features)
        return pd.Series([";".join(names[r]) for r in top], index=X.index)

    # ---------- persistence ----------
    def save(self, root: Path = ARTIFACTS_DIR) -> Path:
        d = root / self.name
        d.mkdir(parents=True, exist_ok=True)
        for k, b in self.boosters.items():
            b.save_model(str(d / f"{k}.txt"))
        (d / "meta.json").write_text(json.dumps({**self.meta, "features": self.features}, indent=2, default=str))
        return d

    @classmethod
    def load(cls, name: str, root: Path = ARTIFACTS_DIR) -> "Bundle":
        d = root / name
        meta = json.loads((d / "meta.json").read_text())
        b = cls(name=name, features=meta.pop("features"), meta=meta)
        for k in [*QUANTILES, *CLASSIFIERS]:
            b.boosters[k] = lgb.Booster(model_file=str(d / f"{k}.txt"))
        return b


def list_models(root: Path = ARTIFACTS_DIR) -> list[str]:
    return sorted(p.name for p in root.glob("*") if (p / "meta.json").exists())

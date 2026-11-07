"""Structural mixture model: P(direction) x P(spread | direction).

The imbalance price is a deterministic function of the regulation direction and the balancing energy
prices (tools/eval/rebuild_price.py reproduces 99.6 % of post-June quarter-hours). The spread
(imbalance - spot) is therefore a two-mode mixture: about +mFRR-up premium when the system is
up-regulated, about -mFRR-down discount when it is down-regulated. A single quantile model smooths
over the two modes (its p50 never reaches beyond +-50 EUR/MWh, while 25 % of validation quarter-hours
do). This model keeps the structure explicit:

- direction head:  P(up) (binary classifier on y_dir == 1), p_none = training share of "none";
- conditional heads: quantile regressors of the spread at LEVELS, trained only on up-regulated rows
  and only on down-regulated rows;
- optional lead-time blocks (e.g. steps 1-8 and 9-40): separate heads per block, because the first
  two hours are driven by the market state at the origin and later hours by forecasts;
- the mixture  F(x) = p_up F_up(x) + p_down F_down(x) + p_none 1[x >= 0]  gives p10/p50/p90 and
  the spike probabilities P(spread > +50) and P(spread < -50) directly.

Same features, same availability-masked feature tables and same training cutoffs as model.Bundle.
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
from .model import DEFAULT_CLF, DEFAULT_REG
from .paths import ARTIFACTS_DIR

LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
GRID = np.linspace(0.005, 0.995, 100)          # quantile levels used to sample each conditional


def _key(side: str, block: int, q: float) -> str:
    return f"{side}_b{block}_q{int(round(q * 100)):02d}"


def _quantile_fn(knots: np.ndarray, levels=LEVELS, grid=GRID) -> np.ndarray:
    """Conditional quantile function on GRID from sorted knots (n x len(levels)): linear between
    knots, linear extrapolation of the outer segments into the tails."""
    lv = np.asarray(levels)
    out = np.empty((knots.shape[0], len(grid)))
    for j, u in enumerate(grid):
        k = np.clip(np.searchsorted(lv, u) - 1, 0, len(lv) - 2)
        w = (u - lv[k]) / (lv[k + 1] - lv[k])
        out[:, j] = knots[:, k] + w * (knots[:, k + 1] - knots[:, k])
    return out


def mixture(p_up, p_down, p_none, v_up, v_down):
    """Weighted samples of the mixture per row: values (n x m) sorted, cumulative weights (n x m)."""
    n, g = v_up.shape
    vals = np.concatenate([v_up, v_down, np.zeros((n, 1))], axis=1)
    w = np.concatenate([np.repeat(p_up[:, None] / g, g, 1), np.repeat(p_down[:, None] / g, g, 1),
                        p_none[:, None]], axis=1)
    o = np.argsort(vals, axis=1)
    vals, w = np.take_along_axis(vals, o, 1), np.take_along_axis(w, o, 1)
    return vals, np.cumsum(w, axis=1) / w.sum(axis=1, keepdims=True)


def mixture_quantile(vals, cw, tau: float) -> np.ndarray:
    i = (cw < tau).sum(axis=1)
    i = np.clip(i, 0, vals.shape[1] - 1)
    return vals[np.arange(len(vals)), i]


@dataclass
class MixBundle:
    name: str
    features: list[str]
    meta: dict = field(default_factory=dict)
    boosters: dict[str, lgb.Booster] = field(default_factory=dict)

    @staticmethod
    def blocks(config: dict) -> list[tuple[int, int]]:
        return [tuple(b) for b in config.get("blocks", [[1, 40]])]

    # ---------- training ----------
    @classmethod
    def train(cls, name: str, df: pd.DataFrame, config: dict) -> "MixBundle":
        cols = config.get("features") or feature_columns(df)
        reg = {**DEFAULT_REG, **config.get("regressor", {})}
        clf = {**DEFAULT_CLF, **config.get("classifier", {})}
        b = cls(name=name, features=cols)
        X = df[cols]
        b.boosters["up"] = lgb.LGBMClassifier(**clf).fit(X, (df["y_dir"] == 1).astype(int)).booster_
        for key, y in (("spike_high", df["y_spread"] > SPIKE_MARGIN), ("spike_low", df["y_spread"] < -SPIKE_MARGIN)):
            b.boosters[key] = lgb.LGBMClassifier(**clf).fit(X, y.astype(int)).booster_
        counts = {}
        for bi, (s0, s1) in enumerate(cls.blocks(config)):
            in_block = df["step"].between(s0, s1)
            for side, mask in (("up", df["y_dir"] == 1), ("down", df["y_dir"] == -1)):
                rows = df[in_block & mask]
                counts[f"{side}_b{bi}"] = int(len(rows))
                for q in LEVELS:
                    m = lgb.LGBMRegressor(objective="quantile", alpha=q, **reg).fit(rows[cols], rows["y_spread"])
                    b.boosters[_key(side, bi, q)] = m.booster_
        b.meta = {
            "name": name, "kind": "mixture", "feature_set": config.get("feature_set", "v1"),
            "blocks": cls.blocks(config), "spikes": config.get("spikes", "mixture"),
            "widen": float(config.get("widen", 1.0)),
            "p_none": float(np.clip((df["y_dir"] == 0).mean(), 0.001, 0.05)),
            "train_rows": int(len(df)), "rows_per_head": counts,
            "train_last_delivery_utc": df["delivery_start_utc"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "trained_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "config": config,
        }
        return b

    # ---------- inference ----------
    def predict(self, df: pd.DataFrame, n_drivers: int = 3) -> pd.DataFrame:
        X = df[self.features]
        spot = df["spot"].to_numpy(float)
        n = len(df)
        p_none = self.meta["p_none"]
        p_up = (1 - p_none) * self.boosters["up"].predict(X)
        p_down = 1 - p_none - p_up
        v_up, v_dn = np.full((n, len(GRID)), np.nan), np.full((n, len(GRID)), np.nan)
        step = df["step"].to_numpy()
        for bi, (s0, s1) in enumerate(self.meta["blocks"]):
            m = (step >= s0) & (step <= s1)
            if not m.any():
                continue
            for side, target in (("up", v_up), ("down", v_dn)):
                knots = np.sort(np.column_stack([self.boosters[_key(side, bi, q)].predict(X[m]) for q in LEVELS]), axis=1)
                target[m] = _quantile_fn(knots)
        vals, cw = mixture(p_up, p_down, np.full(n, p_none), v_up, v_dn)
        q10, q50, q90 = (mixture_quantile(vals, cw, t) for t in (0.1, 0.5, 0.9))
        w = self.meta.get("widen", 1.0)
        out = pd.DataFrame(index=df.index)
        out["p10"] = spot + q50 - w * (q50 - q10)
        out["p50"] = spot + q50
        out["p90"] = spot + q50 + w * (q90 - q50)
        out["p_up"], out["p_none"] = p_up, p_none
        out["p_down"] = 1 - out["p_up"] - out["p_none"]
        # spike probabilities: from the mixture, from the dedicated classifiers, or their mean
        wsum = np.diff(np.concatenate([np.zeros((n, 1)), cw], axis=1), axis=1)
        hi_m, lo_m = (wsum * (vals > SPIKE_MARGIN)).sum(1), (wsum * (vals < -SPIKE_MARGIN)).sum(1)
        hi_c, lo_c = self.boosters["spike_high"].predict(X), self.boosters["spike_low"].predict(X)
        mode = self.meta.get("spikes", "mixture")
        hi, lo = {"mixture": (hi_m, lo_m), "classifier": (hi_c, lo_c),
                  "mean": ((hi_m + hi_c) / 2, (lo_m + lo_c) / 2)}[mode]
        sc = np.where(hi + lo > 0.999, 0.999 / np.maximum(hi + lo, 1e-12), 1.0)
        out["p_spike_high"], out["p_spike_low"] = np.clip(hi * sc, 0, 1), np.clip(lo * sc, 0, 1)
        contrib = self.boosters["up"].predict(X, pred_contrib=True)[:, :-1]      # drivers of the direction
        top = np.argsort(-np.abs(contrib), axis=1)[:, :n_drivers]
        names = np.array(self.features)
        out["top_drivers"] = [";".join(names[r]) for r in top]
        return out[["p10", "p50", "p90", "p_up", "p_down", "p_none", "p_spike_high", "p_spike_low", "top_drivers"]]

    # ---------- persistence ----------
    def save(self, root: Path = ARTIFACTS_DIR) -> Path:
        d = root / self.name
        d.mkdir(parents=True, exist_ok=True)
        for k, b in self.boosters.items():
            b.save_model(str(d / f"{k}.txt"))
        (d / "meta.json").write_text(json.dumps({**self.meta, "features": self.features}, indent=2, default=str))
        return d

    @classmethod
    def load(cls, name: str, root: Path = ARTIFACTS_DIR) -> "MixBundle":
        d = root / name
        meta = json.loads((d / "meta.json").read_text())
        b = cls(name=name, features=meta.pop("features"), meta=meta)
        b.meta["blocks"] = [tuple(x) for x in b.meta["blocks"]]
        for f in d.glob("*.txt"):
            b.boosters[f.stem] = lgb.Booster(model_file=str(f))
        return b

"""NOT ADOPTED (diagnostic kept for the record). Stage-1 volume head: forecast of the net activated mFRR volume (MW) per delivery quarter-hour.

Why: the regulation direction is the sign of the system imbalance. A classifier on 0/1 direction
discards how far the system is from balance. A regression on net activated mFRR
(Fingrid 375 up plus 376 down; the down series is stored as negative MW, both in the organiser
package) keeps that size. Its prediction is
then an extra input (`vol_hat`) to the mixture model's direction head and conditional price heads
(stacking).

Target: y_vol = truth(fi_mfrr_up_activated) + truth(fi_mfrr_down_activated) (down <= 0) at the delivery
quarter-hour, read with Store.truth exactly like y_spread (targets only, never features). Its
availability time y_vol_fu is the later of the two series' first_usable_origin_utc; training rows
need both y_target_fu (imbalance price) and y_vol_fu inside the training cutoff.

Leakage control of the stacking:
- TRAINING rows of the second stage get OUT-OF-FOLD predictions: training origins are split into
  K contiguous time blocks; the model for block k is trained on all other blocks except a GAP_DAYS
  buffer on both sides of block k (so no 10 h horizon or target window overlaps the held-out block),
  then predicts block k.
- VALIDATION / TEST rows get the prediction of a model trained on all training rows of the same
  version (val version: targets usable before the first validation origin; final: up to the
  training cutoff). That model never sees a target after its cutoff.
- Features come only from the availability-masked feature tables (load_feature_table), unchanged.

Result (validation, 7 Nov 2026): the out-of-fold volume forecast correlates 0.30-0.35 with the
realised net mFRR. Added to the direction head it changes binary Brier of P(up) from 0.1967 to
0.1971 (v4) and 0.1985 to 0.1972 (v4m): noise. The regressor sees the same features as the
direction classifier, so stacking adds no new information. Not used by any submitted model.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from .features import feature_columns, load_store

UP, DOWN = "fi_mfrr_up_activated", "fi_mfrr_down_activated"
K_FOLDS = 5
GAP_DAYS = 1
VOL_PARAMS = dict(objective="regression", n_estimators=200, learning_rate=0.03, num_leaves=31,
                  min_child_samples=200, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)


def add_volume_target(table: pd.DataFrame) -> pd.DataFrame:
    """y_vol (MW, + = net up-regulation) and y_vol_fu for every row of a feature table."""
    st = load_store()
    idx = st.index_of(table["delivery_start_utc"])
    out = table.copy()
    out["y_vol"] = st.truth(UP, idx) + st.truth(DOWN, idx)     # down is stored as negative MW
    safe = np.clip(idx, 0, len(st.grid) - 1)
    fu = np.maximum(st.fu[UP][safe], st.fu[DOWN][safe])
    out["y_vol_fu"] = pd.to_datetime(np.where(fu == np.iinfo(np.int64).max, np.datetime64("NaT"), fu.astype("datetime64[ns]")), utc=True)
    return out


def _cols(table: pd.DataFrame) -> list[str]:
    return [c for c in feature_columns(table) if c not in ("y_vol", "y_vol_fu", "vol_hat")]


def _fit(rows: pd.DataFrame, cols: list[str]) -> lgb.Booster:
    r = rows.dropna(subset=["y_vol"])
    return lgb.LGBMRegressor(**VOL_PARAMS).fit(r[cols], r["y_vol"]).booster_


def oof_predict(train: pd.DataFrame, cols: list[str], k: int = K_FOLDS, gap_days: int = GAP_DAYS) -> np.ndarray:
    """Out-of-fold vol_hat for the training rows (contiguous origin blocks with a gap)."""
    origins = np.sort(train["forecast_origin_utc"].unique())
    blocks = np.array_split(origins, k)
    gap = pd.Timedelta(days=gap_days)
    pred = np.full(len(train), np.nan)
    o = train["forecast_origin_utc"]
    for b in blocks:
        lo, hi = pd.Timestamp(b[0]), pd.Timestamp(b[-1])
        held = o.between(lo, hi).to_numpy()
        fit_rows = ~o.between(lo - gap, hi + gap).to_numpy()
        m = _fit(train[fit_rows], cols)
        pred[held] = m.predict(train.loc[held, cols])
    return pred


def stack(table: pd.DataFrame, train_mask: np.ndarray, predict_mask: np.ndarray) -> tuple[pd.DataFrame, lgb.Booster]:
    """Return table with `vol_hat`: OOF on train_mask rows, full-train model on predict_mask rows.
    Rows in neither mask get NaN. Also returns the full-train volume model (saved with the bundle)."""
    cols = _cols(table)
    out = table.copy()
    out["vol_hat"] = np.nan
    train = table[train_mask]
    out.loc[train_mask, "vol_hat"] = oof_predict(train, cols)
    full = _fit(train, cols)
    out.loc[predict_mask, "vol_hat"] = full.predict(table.loc[predict_mask, cols])
    return out, full

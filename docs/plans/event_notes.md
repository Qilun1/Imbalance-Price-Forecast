# Plan: learned event notes for traders and plant operators

Status: steps 1–4 done (7 Nov 2026): labels, out-of-sample inputs with a leakage check, trained
classifiers (`alerts-val`, `alerts`), inference into `event_probs` and `GET /api/notes`. Step 5
(frontend views) is next. Run it with `uv run python -m tools.cli alerts all`.

## Goal

At every forecast origin, after the price forecast has run, estimate the probability that something
worth noting happens in the next 10 hours, separately for a **trader** and a **plant operator**, with
the uncertainty of that probability attached. The dashboard gets two views built from the same
event probabilities.

What this is not:
- It does not change `forecast_backtest.csv`. The submission keeps coming from the base models, so
  there is no format risk (AGENTS.md rule 2).
- It does not replace `backend/api/alerts.py`. Those rule-based alerts describe the forecast (it
  moved, it is wide, models disagree). The new notes estimate the probability of **real-world
  events**, learned from what actually happened. Both appear in the views.
- Notes say what to check, not what to do, as the existing alerts already do. The brief limits the
  first phase to suggestions to review: open data cannot tell what capacity is free.

## 1. Events (labels)

Labels come from realised organiser series only, through `Store.truth` (targets only). Each label is
"did the event happen in this window", for each (origin, window) pair.

**Windows** (the horizon is 40 quarter-hours = 10 h):

| Window | Steps | Meaning |
|---|---|---|
| `now` | 1–8 | 0–2 h, act fast |
| `soon` | 9–20 | 2–5 h |
| `later` | 21–40 | 5–10 h |

**Events** (thresholds set on training data only; robust quantiles where a level is needed):

| id | Definition (within the window) | Trader | Operator |
|---|---|---|---|
| `spike_high` | ≥ 2 quarters with imbalance − spot > +50 | ✓ | ✓ |
| `spike_low` | ≥ 2 quarters with imbalance − spot < −50 | ✓ | ✓ |
| `up_episode` | ≥ 4 consecutive quarters with direction = up | ✓ | ✓ |
| `direction_flip` | dominant direction differs from the last observed one for ≥ 4 quarters | ✓ | |
| `deep_negative` | ≥ 4 consecutive quarters with imbalance price < −10 (training P5; the price is negative in 30 % of quarters, so "< 0" alone is not noteworthy) | | ✓ |
| `extreme_price` | ≥ 1 quarter with imbalance price > 170 (training P97.5) | ✓ | ✓ |
| `large_up_activation` | mFRR up activated volume > training P95 in ≥ 2 quarters | | ✓ |
| `large_down_activation` | mFRR down activated volume > training P95 in ≥ 2 quarters | | ✓ |
| `forecast_miss` | ≥ 2 quarters with \|imbalance − p50\| > 100 (the base forecast will be badly wrong) | ✓ | |

The definitions live in `backend/imbalance/events.py`. Their rates per (origin, window) on training
data before validation are printed by `tools/training/event_rates.py` (not committed: spike rates
are derived from the licensed spot price, AGENTS.md rules 0 and 6).

**Operator = a CHP plant with electric boilers** (team decision, 7 Nov 2026). Both assets can move
power in either direction, so the operator's notes point to what to check:

| Event | What the operator checks |
|---|---|
| `spike_high`, `extreme_price`, `up_episode`, `large_up_activation` | Headroom to raise CHP electricity output, or to turn electric boilers down (both act as up-regulation); heat storage level |
| `spike_low`, `deep_negative`, `large_down_activation` | Whether the electric boilers can take load and the CHP can turn down (down-regulation); room in heat storage |

The spike definition and its ±50 margin match the official scoring and are not changed. The
`forecast_miss` event predicts how far the forecast will miss, which is the most direct "don't
trust the line" signal a trader can get.

## 2. Model

**Inputs per (origin, window):**
1. Origin-level features from the existing feature table (lags, flows, neighbour prices, observed
   wind error, history head).
2. Window aggregates of delivery-level features: max, min and mean of spot, wind-forecast ramp,
   residual load and capacity over the window's quarters.
3. Aggregates of the base forecast over the window: max `p_spike_*`, mean and max `p_up`, max
   P90 − P10 width, p50 range, the change since the previous origin, and the gap to the challenger
   model.
4. The window id and calendar fields (hour, weekday, holiday, DST day).

Everything is read through the availability-masked `Store` / feature table, so the existing leakage
guarantees carry over. Base-forecast inputs (3) must be **out-of-sample**. They are produced the way
`tools/training/hist_heads.py` already does it: an expanding window over monthly segments, where
each segment is predicted by a base model trained only on targets realised before the segment
started. June has no out-of-sample forecasts, so the alert training starts in July.

**Classifier:** chosen per event on validation Brier score from a small set of candidates, all fed
the same rows (the windows pooled, with the window id as a feature):

| Candidate | Why it is in the set |
|---|---|
| Logistic regression on about 10 aggregates | A floor; robust when positives are few |
| LightGBM, heavily regularised | Default: strong on small tabular data, handles NaN (sparse aFRR) natively, exact TreeSHAP for the drivers, the same stack as the base engine |
| TabPFN v2 | A pretrained tabular foundation model built for datasets of up to ~10k rows, our size. **The licence must be checked before use** (AGENTS.md rule 6) |
| Small MLP (2×64, dropout, weight decay, imputation + scaling) | A control, so the choice is evidence-based. Expected to lose here; kept only if it wins on validation |

There are only about 2,200 hourly origins, and they are strongly autocorrelated, so the effective
sample is small. The selection is done on validation only, never on test.

**Uncertainty, three layers, all shown:**
1. *Calibrated probability:* Venn–Abers calibration, fitted on a time-held-out fold. It gives a
   probability interval `[p_lo, p_hi]` with a validity guarantee instead of one number. A wide
   interval means "few similar cases in training".
2. *Lift vs normal:* the probability divided by the climatological base rate for that window and
   hour, so "35 %" reads as "3× more likely than usual".
3. *Confidence tier* (high / medium / low): set from the interval width, the input data age
   (`data_age_min`, the stale flag) and whether the base models disagree. It drives the badge on the
   card.

**Decision thresholds per persona:** the cost–loss model. A note fires when `p ≥ C/L`, where C/L is
the persona's cost-to-loss ratio for that event. The defaults are chosen on validation to maximise
relative economic value, nudged upward to limit false alarms ("boy who cried wolf", Roulston and
Smith). They live in `events.py`.

**User-set thresholds:** `/notes` returns every event's probability together with its default
threshold and a `fires` flag. The dashboard has a per-event (and per-persona "sensitivity")
threshold control that refilters on the client, and remembers the choice per viewer. An optional
`threshold.<event>=` query parameter applies the same override on the server, for other consumers.
A changed threshold changes only which notes are shown, never the probabilities.

**Drivers:** TreeSHAP of the alert model per note, mapped through `labels.py`. Correlated features
make single SHAP values unreliable, so the attributions are grouped by family (wind, spot shape,
flows, recent imbalance) before showing the top 2–3.

**Honest baselines the model must beat on validation** (Brier score):
- (a) climatology by window and hour;
- (b) a rule on the base model alone, e.g. `1 − ∏(1 − p_spike_high)` over the window, with the
  same calibration.

If the learned model does not beat (b) for an event, (b) is shipped for that event.

## 3. Periods (AGENTS.md rule 4)

| Variant | Alert training labels | Base forecasts used | Evaluated on |
|---|---|---|---|
| `alerts-val` | delivery ≤ 6 Sep 20:45 UTC | out-of-sample segments → then the `*-val` models | validation 7 Sep–4 Oct |
| `alerts` | delivery ≤ 4 Oct 20:45 UTC | out-of-sample segments → then the final models | inference only on test origins |

(origin, window) rows whose window extends past the label cutoff are dropped. Test-period data is
never used for training, thresholds, calibration or model choice.

## 4. Evaluation (diagnostics, labelled as such; they do not replace `score.py`)

Per event × window, on validation:
- Brier score and Brier skill score vs climatology, PR-AUC (events are imbalanced), log loss;
- reliability diagram, and the coverage of the Venn–Abers intervals;
- at the persona thresholds: hit rate, false-alarm ratio and alerts per day;
- a relative economic value curve over C/L (ECMWF / CAWCR method).

The report is written to `static_data/work/alerts/` (gitignored, AGENTS.md rule 0).

## 5. Code layout

| File | Role |
|---|---|
| `backend/imbalance/events.py` | Windows, event label functions, persona → events mapping and C/L defaults (single source of truth) |
| `backend/imbalance/alert_features.py` | (origin, window) feature rows from the feature table and base forecasts |
| `backend/imbalance/alert_model.py` | `AlertBundle`: train, Venn–Abers calibration, predict with interval/lift/tier/drivers, save/load to `backend/artifacts/alerts*/` |
| `tools/training/alert_train.py` | Out-of-sample base forecasts, training of both variants, evaluation report |
| `tools/eval/alert_leakage.py` | Rebuild alert features from a store truncated at the origin and require equality (the same pattern as `leakage.py`) |
| `backend/imbalance/inference.py` | After the base forecast, write event probabilities to an `event_probs` table in `forecasts.duckdb` |
| `backend/api/notes.py`, `routes/notes.py` | `GET /notes?persona=trader\|operator&as_of=`: cards with event, window, p, [p_lo, p_hi], lift, tier, drivers, what to check |
| `backend/tests/test_events.py`, `test_alert_*.py` | Labels on synthetic series, probability ranges, the availability check, persona mapping, an API contract test |
| `tools/cli.py` | `alerts-train`, `alerts-infer`, `alerts-leakage` subcommands |

The frontend (two views) is a follow-up once `/notes` returns real data. The mock repository gets
mock notes so the frontend work can start in parallel.

Worktree note: the gitignored data (`static_data/`, `backend/infer_data/`, `backend/artifacts/`)
exists only in the main checkout. The worktree reads it via `IMBALANCE_REPO_ROOT` or symlinks, to be
decided in step 1.

## 6. Steps

1. Data access in the worktree; `events.py` with labels and tests; event base rates per window on
   training data (a sanity check of the definitions).
2. Out-of-sample base forecasts (expanding window) and `alert_features.py`, plus `alert_leakage.py`
   passing.
3. `AlertBundle`, the `alerts-val` variant, the evaluation report vs baselines (a) and (b). **Review
   point:** drop or merge events that have no skill.
4. The final `alerts` variant, inference into `event_probs`, the `/notes` API with mock data, and
   tests.
5. Frontend trader and operator views.

## 6b. Outcome of the model comparison (step 3)

Validation diagnostics are written to `static_data/work/alerts/eval_validation.csv` (gitignored; scores
are data, AGENTS.md rule 0). In short:
- The MLP was the weakest or near-weakest family on every event, as the tabular-data literature predicts.
  It is not used.
- LightGBM clearly beat the calibrated rule baseline for `spike_high`, `direction_flip` and
  `deep_negative`. For the other events the rule on the base forecast's own probabilities was as
  good or better, so the rule is used there (`tools/training/configs/alerts.yaml`).
- `large_up_activation` and `deep_negative` have little validation skill and are hidden from `/notes`
  by default (`include_low_skill=true` shows them, flagged).
- Venn–Abers intervals are narrow for most rows (around 5,000 calibration rows), and wide in sparse
  score regions. The confidence-tier bars were read from validation origins only.
- TabPFN was not tried: TabPFN-2.5+ weights are non-commercial. The TabPFN-2 weights (Apache 2.0 with
  attribution) remain an option, but need PyTorch.
- `forecast_miss` is hidden from `/notes` by default (team decision, 7 Nov 2026; `hidden_events` in
  `configs/alerts.yaml`): it predicts misses of the `lgbm_v4s` P50, not of the forecast the dashboard
  shows. The after-the-fact test diagnostic (`tools/eval/alert_test_report.py`) also showed its skill
  fading. Its model, calibration and threshold are unchanged, and `include_low_skill=true` still returns it.

## 6c. Do the confidence signals mean anything? (validation only)

`uv run python -m tools.eval.alert_confidence` scores the stored `alerts-val` probabilities on validation
origins, with errors clustered by day and a day-block bootstrap (results in `static_data/work/alerts/`,
gitignored). In short:
- The tier orders calibration error as intended: ECE grows from high to medium to low, each clearly
  above what chance alone gives on that many rows.
- "Low" does not mean "little skill". Wide intervals occur where scores are high and training cases are
  few; those notes have the highest Brier skill. What is shaky is the exact percentage, and it errs
  low: in the low tier the event happened markedly more often than stated. Every tier under-predicts
  slightly on validation, a shift between the training months and September.
- In the backtest the tier rests on interval width alone: data age is constant (75 min) and the base
  models never differ by 45 EUR/MWh, so the stale and conflict reasons are untested.
- The Venn–Abers intervals are far narrower than the real uncertainty: the event rate falls inside a
  bin's mean interval in under a tenth of bins. They measure how many similar training cases exist, not
  a range for the true probability under the shift between months, and should be read as such. Their
  width still ranks calibration error (the widest tercile has the largest ECE).

## 7. Open questions for the team

- ~~Operator plant~~: CHP with electric boilers (decided).
- ~~Thresholds~~: defaults, adjustable by the user (decided).
- Should the views show test-period hit rates after the fact (a diagnostic only, never used for
  tuning)?

## References

- Balancing price and spike forecasting: [Dol et al., Dutch balancing market (SSRN)](https://papers.ssrn.com/sol3/Delivery.cfm/5393123.pdf?abstractid=5393123&mirid=1),
  [French imbalance spike detection](https://www.researchgate.net/publication/352836562),
  [Irish balancing market](https://arxiv.org/pdf/2402.06714),
  [review of probabilistic price forecasting](https://arxiv.org/pdf/2511.05523),
  [NEM spike thresholds from robust quantiles](https://arxiv.org/pdf/2311.07289).
- Finnish market rules: [Fingrid imbalance price from 1 Jun 2026](https://www.fingrid.fi/globalassets/dokumentit/fi/sahkomarkkinat/tasesahko/imbalance-price-in-finland-1.6.2026.pdf),
  [one-price system](https://www.fingrid.fi/en/electricity-market/balance-service/description-of-balance-model/one-price-system/).
- Uncertainty: [Angelopoulos and Bates, conformal prediction](https://arxiv.org/abs/2107.07511),
  [Vovk and Petej, Venn–Abers predictors](https://arxiv.org/abs/1211.0025),
  [Gibbs and Candès, adaptive conformal inference under distribution shift](https://arxiv.org/abs/2106.00170),
  [conformal early classification of alarm floods (IEEE Access)](https://doaj.org/article/0ddec154ade64ea6b34523f77a990cb5).
- Warning thresholds and value: [Roulston and Smith, "The boy who cried wolf"](https://www.lse.ac.uk/CATS/Assets/PDFs/Publications/Papers/2004/Roulston-and-Smith-searchable-The-boy-who-cried-wolf.pdf),
  [ECMWF "Decisions, decisions"](https://www.ecmwf.int/sites/default/files/elibrary/2014/17333-decisions-decisions.pdf),
  [CAWCR relative value](https://cawcr.gov.au/projects/verification/value/relativevalue_more.html).
- Model choice: [Grinsztajn et al., why tree-based models still beat deep learning on tabular data](https://arxiv.org/abs/2207.08815),
  [Shwartz-Ziv and Armon, tabular data: deep learning is not all you need](https://arxiv.org/abs/2106.03253),
  [Hollmann et al., TabPFN (Nature 2025)](https://www.nature.com/articles/s41586-024-08328-6).
- Explanations: [SHAP with correlated energy features (KIT)](https://publikationen.bibliothek.kit.edu/1000192183/179290640).

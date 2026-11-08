# Volta: evaluation report for the 10-hour Finnish imbalance price forecast

Team KODA, Since AI 2026, Turku Energia challenge.

**At a glance**

| | |
|---|---|
| Validation metrics vs. the organiser's baseline | MAE -38 %, pinball -53 %, coverage 0.82 (target 0.80), spike Brier -23 %, direction Brier -15 %; better in 100 % of bootstrap resamples |
| Reasoning chain | The price is a rule (rebuilt 99.6 %); only the regulation direction and the balancing price are uncertain; so: direction first, then price given direction, one distribution for P50, band and spike risk |
| Factors affecting the forecast | Direction follows physical forecasts (48 % of SHAP); the near-term up price follows the market state (49 %); the down price follows spot (57-63 %); real-time grid state adds -5 % direction Brier in the first hour |
| Data and availability | Organiser package + Fingrid measured wind and real-time grid state + two NWP sources, all behind one availability mask; leakage check PASS on 350 origins |
| What it enables | 1 MW of flexibility dispatched on the probabilities earns about 15 kEUR/yr (persistence rule 10, perfect foresight 51); a panel that says what to check and how likely it is |

Submission `ens_finald`
(`forecast_backtest.csv`, 673 origins x 40 steps = 26,920 rows; `validate_submission.py` 0 errors,
0 warnings). All scores are from the organiser's `score.py` on the validation period 7 Sep - 4 Oct
2026 (26,700 scored rows), from models trained only on targets usable before the first validation
origin. The sections below cover the three items the brief asks for: the **validation-period metrics** (section 1),
the **reasoning chain** (section 2: what we noticed in the data, and what that made the model) and
the **factors affecting the forecast** (section 3), then what the forecast enables (section 4). The
full account of every experiment, ablation and the reproduction commands is in
[EVALUATION_DETAILS.md](EVALUATION_DETAILS.md).

## 1. Validation-period metrics

| Level 1 metric (lower is better) | Baseline | Submission | Change |
|---|---|---|---|
| MAE of p50, EUR/MWh | 66.20 | **40.98** | -38 % |
| Mean pinball loss p10/p90 | 24.18 | **11.31** (held out) | -53 % |
| P10-P90 coverage (target 0.80) | 0.683 | 0.819 | on target |
| Mean Brier, spike high / low | 0.1132 | **0.0873** | -23 % |
| Three-class Brier, direction | 0.4509 | **0.3848** | -15 % |

Better than the baseline in 100 % of 200 day-block bootstrap resamples on all four metrics. Held out
means each validation week uses band widths fitted on the other four; nothing else is recalibrated.

By lead block (steps 1-4 / 5-8 / 9-16 / 17-40): MAE 38.0 / 39.8 / 40.7 / 41.8, pinball 10.56 / 10.92 /
11.29 / 11.51, coverage 0.83 / 0.81 / 0.82 / 0.82, spike Brier 0.078 / 0.082 / 0.086 / 0.090, direction
Brier 0.353 / 0.373 / 0.383 / 0.393. Published 15-minute imbalance models beat persistence by 12-25 %
in MAE at 1-8 quarter-hours (Belgium, arXiv 2605.17045; Austria, arXiv 2605.09061); ours by 38 %.

## 2. Reasoning chain

In one line: weather drives the gap between planned and actual production; that gap is what Fingrid
regulates; the regulation direction and the balancing energy price set the imbalance price exactly.
So we forecast the direction first, then the price given the direction, from one distribution, fed
with the earliest measurable signs of the plan error.

### 2.1 What we noticed in the data

**The price is mechanical.** From public Fingrid series we rebuild the imbalance price exactly: the
1 June 2026 volume-weighted rule reproduces 99.6 % of quarter-hours (MAE 0.01 EUR/MWh). The pricing
rule need not be learned. What has to be forecast is the regulation direction and the balancing
energy price, and both follow from the system's plan error, which weather drives.

**The spread to spot is bimodal.** Up-regulation puts the price above spot, down-regulation below.
On validation 25 % of quarter-hours are beyond +-50 EUR/MWh. A single smooth quantile model never puts
its P50 in a spike (MAE 26 on down-regulated quarter-hours, 77 on up-regulated ones).

**The error lives in the spikes, and the data sets a floor.** Decomposing the submission's MAE by the
realised |spread|:

| \|spread\|, EUR/MWh | 0-10 | 10-25 | 25-50 | 50-100 | 100-200 | > 200 |
|---|---|---|---|---|---|---|
| Share of quarter-hours | 21 % | 28 % | 26 % | 16 % | 7 % | 1.8 % |
| Share of MAE | 5 % | 8 % | 15 % | 23 % | 23 % | 26 % |

On the same rows, P50 = spot scores 46.6; an oracle that knew the realised direction 10 h ahead
(spread = that direction's median) would score 35.6; one that also knew the spike class, 25.0.
Oracles read the outcome and are upper bounds, not models. So the point forecast has little room
left (scaling it toward spot by 0.5 worsens MAE to 43.2; by 1.25 improves it only to 40.8), and the
design effort went into calibrated probabilities and the band.

### 2.2 What makes the model different

**Built the way the price forms.** Each member (`backend/imbalance/mixture.py`) is three LightGBM
parts over (origin, step) rows: a direction head P(up), P(down), P(none); quantile heads of the spread
given up-regulation; quantile heads given down-regulation (7 levels each, trained only on rows of
their own direction; separate heads for steps 1-8 and 9-40). They are mixed into one distribution

    F(x) = P(up) F_up(x) + P(down) F_down(x) + P(none) 1[x >= 0]

from which P10/P50/P90, P(spread > +50), P(spread < -50) and the direction are all read. The three
scored outputs cannot contradict each other. The conditional heads are widened x2.0 around their
medians before mixing (raw coverage was 0.67); with that, the separate spike correction the earlier
chain needed (+0.45 logit) went to zero. The target is the spread; spot is known and added back.

**Fed the freshest data the availability rule allows.** Beyond the organiser package: Fingrid measured
wind (dataset 75, usable 60 min after the quarter-hour) as the observed error against Fingrid's
day-ahead forecast; Fingrid real-time grid state (198 surplus/deficit, 177 frequency, 194 net import,
371 electric boilers, 398/399 batteries, 181/193 real-time wind and consumption; measured publication
delay 1.1-4.1 min, used with a 15 min rule) for steps 1-8 only; ECMWF IFS 9 km and MET Nordic 2.5 km
single runs via Open-Meteo (run init + 8 h and + 2 h). Short-window direction persistence and spike
clustering features (v9d) for steps 1-8.

**Eight members averaged.** Two weather sources x {default fit, second seed, last-7-weeks window,
asinh target}, each split by lead block. The 7-week member is the best single model; the average
beats the two-member chain in 100 / 97 / 92 % of resamples (MAE / pinball / direction). Band widths
are then rescaled per lead block and direction certainty (0.6x when the direction is clear, 1.1x when
it is not), fitted held out; spike probabilities are averaged 50/50 with the previous chain's.

**Calibrated.** Reliability diagrams for the spike and direction probabilities lie on the diagonal
(`docs/slides/plots.py`); coverage is 80-83 % in every lead block. No post-hoc probability calibration.

**Availability proven, not assumed.** Every feature is read through one availability-masked reader.
An independent check (`tools/eval/leakage.py`) rebuilds the features from data with every row and
NWP run not yet usable at the origin physically deleted and requires a bit-exact match: PASS on 350
random origins across training, validation and test. No target and no origin after 4 Oct 20:45 UTC
in training; calibration from validation outcomes only; `data_cutoff_utc` <= origin on all rows.

## 3. Factors affecting the forecast

Share of mean |SHAP| by feature group (member mix_v4b, validation sample), per part of the model:

| Feature group | Direction | Up price, 0-2 h | Down price, 0-2 h | Up price, 2-10 h | Down price, 2-10 h |
|---|---|---|---|---|---|
| Physical forecasts (wind, consumption, solar, NWP) | **48** | 17 | 6 | **36** | 16 |
| Market state at the origin (last prices, mFRR activations, direction run) | 19 | **49** | 29 | 23 | 10 |
| Spot (level and shape over the horizon) | 19 | 17 | **57** | 20 | **63** |
| Cross-border (SE1, SE3, EE prices and flows, FI-EE capacity) | 5 | 5 | 6 | 5 | 8 |
| Observed wind error (measured minus Fingrid forecast) | 3 | 9 | 2 | 7 | 2 |
| Calendar and lead time | 6 | 2 | 1 | 9 | 1 |

Each part learns from what physically matters to it. The **direction** follows the physical
forecasts: wind, consumption and their errors decide whether the system ends up short or long. The
**up-regulation price in the first two hours** follows the market state, because activations and
prices persist; later it follows the forecasts. The **down-regulation price** follows spot, because a
long system prices from the spot level down to the cheapest down-regulation bids. For steps 1-8 the
**real-time grid state** (surplus/deficit, frequency, net import, boilers, batteries) adds the
freshest signal: direction Brier -5 % in the first hour, in every validation week; beyond two hours
it only adds noise, hence the lead split. The per-row `top_drivers` column in the submission lists
the three largest SHAP contributions to the direction head for that origin and step.

Tested and left out because they did not help: NWP model disagreement, an imbalance-volume
forecast as an input, history back to March 2025, longer persistence windows (12-24 h), and full
post-hoc recalibration. Numbers in EVALUATION_DETAILS.md section 4.

## 4. What it enables the business to do

`tools/eval/economic_value.py` scores a fixed rule on the validation forecasts and realised prices:
one MW of flexibility (electric boiler or CHP headroom), dispatched one hour ahead when
P(spike high) >= 0.3 (raise output or cut load) or P(spike low) >= 0.3 (take load), paid the realised
spread minus an activation cost. Four weeks annualised x13.

| Activation cost, EUR/MWh | Submission, 1 h ahead | Persistence rule | Perfect foresight |
|---|---|---|---|
| 0 | 28.3 kEUR/MW/yr | 22.9 | 61.8 |
| 20 | **15.4** | 10.2 | 50.9 |
| 40 | 2.6 | -2.5 | 40.0 |

The persistence rule acts when the last known spread exceeds 50 EUR/MWh. Acting on P50 alone almost
never triggers: the probabilities are the decision variable. Every MWh of imbalance left uncorrected
costs 43 EUR/MWh on average. Caveats: four weeks, single-price settlement, no intraday alternative,
and Turku Energia's marginal costs, heat constraints and committed capacity are not public.

The dashboard and API (`/api/forecast`, `/api/alerts`, `/api/notes`) show the next 10 hours with the
band, direction, spike risk and per-row drivers (`top_drivers`), hindsight views with a movable review
point, rule-based alerts (forecast moved, band wide, models disagree, data stale) and an event
classifier that gives calibrated probabilities, with Venn-Abers intervals, of spike episodes, extreme
prices and direction flips for a trader and a plant operator. Suggestions to review, not operating
instructions.

## 5. Limitations

- Four months of summer and early-autumn training data; October has more wind and the first heating
  demand. Four validation weeks cannot be cherry-picked but are short; bootstrap checks are reported.
- The up-regulation heads see a third of the rows; their tails are the least certain part.
- Real-time series have gaps (84-91 % complete quarter-hours); the model uses the latest complete one
  and its age is a feature.
- Model, width and feature-set choices were made on validation, between few, physically motivated
  variants; validation scores are therefore slightly optimistic.

## 6. Reproduce

`README.md` has the full command sequence (ingest, features, four mixture configs x four bagging
members, lead split, ensemble, band widths, spike hedge, export, validate, leakage check);
EVALUATION_DETAILS.md section 8 lists it as well. Requires a free Fingrid API key and the organiser
package. `uv run pytest`: 134 tests.

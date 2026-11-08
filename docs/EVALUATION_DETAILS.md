# Evaluation report, full details: 10-hour Finnish imbalance price forecast

This is the long version. The short report the jury should read first is [EVALUATION.md](EVALUATION.md).

Team KODA, Since AI 2026, Turku Energia challenge. Submission: `ens_finald` (eight structural
mixture members: two weather sources x four bagging variants, each split by lead time with the
real-time grid state and short-window direction persistence for the first 2 h; bands and spike
probabilities read from one consistent mixture) with situation-dependent band widths and the spike
probabilities averaged 50/50 with the previous chain (`forecast_backtest.csv`). The file passes
`validate_submission.py` 0.1.0 with 0 errors and 0 warnings; the previous submission `ens_final`
(same chain without the persistence features) is the validated fallback.

All scores come from the organiser's `score.py` (scorer 0.1.1, schema 1.0, spike margin 50 EUR/MWh) on
the validation period, 7 Sep - 4 Oct 2026 (26,700 scored rows). The validation forecasts come from
models trained only on targets usable before the first validation origin (2026-09-06T21:00Z).
Test-period targets were never available to us, and test inputs were used only as features at test
origins.

## 1. Summary

| Level 1 metric (lower is better) | Organiser baseline | Our submission | Change |
|---|---|---|---|
| MAE of p50 (EUR/MWh) | 66.20 | **40.98** | -38 % |
| Mean pinball loss p10/p90 | 24.18 | **11.31** (held out¹) | -53 % |
| P10-P90 coverage (target about 0.80) | 0.683 | 0.819 | slightly wide |
| Mean Brier, spike high/low | 0.1132 | **0.0873** | -23 % |
| Three-class Brier, direction | 0.4509 | **0.3848** | -15 % |

Official `score.py` 0.1.1 output for the submitted chain on the validation period
(`static_data/work/report/final_val/score_summary.md`): pinball p10 6.90, p90 15.72, p50 20.49;
Brier spike high 0.0934, low 0.0812; observed high / low share 0.1213 / 0.1296; MAE ratio to
baseline 0.619. The fallback `ens_final` scores 40.99 / 11.31 / 0.819 / 0.0874 / 0.3852.

¹ The band widths are fitted on validation outcomes. This score is held out: each validation week uses
factors fitted on the other four weeks. Nothing else is recalibrated after training.

The test submission (673 origins x 40 steps = 26,920 rows) passes the organiser's
`validate_submission.py` with 0 errors and 0 warnings.

**Three things this report shows.**
1. *What we noticed in the data.* The imbalance price is mechanical: the regulation direction and the
   balancing energy prices reproduce it exactly (99.6 % of quarter-hours). What is uncertain is the
   regulation. The spread to spot is bimodal, and 72 % of the P50 error comes from the 25 % of
   quarter-hours beyond +-50 EUR/MWh. Even an oracle that knew the direction 10 h ahead would score
   MAE 35.6; below 30 needs to know which quarter-hours spike (section 3.4).
2. *What makes the model different.* It is built the way the price forms: direction first, then the
   price given each direction, mixed into one distribution from which P50, the P10-P90 band and the
   spike probabilities are all read. It is fed the freshest data the availability rule allows (grid
   state 15 min old at the origin) and its availability is proven by an independent rebuild. Published
   15-minute imbalance models beat persistence by 12-25 % in MAE; this one by 38 %, with calibrated
   probabilities (section 3.5).
3. *What it enables.* Dispatching one MW of flexibility on the spike probabilities earns about
   15 kEUR per year at a 20 EUR/MWh activation cost, 50 % more than the same rule on the persistence
   baseline; perfect foresight would earn 51 kEUR (section 6). The point forecast alone almost never
   triggers an action: the probabilities are the decision variable.

**Reasoning chain in one line:** weather drives the gap between planned and actual production. That
gap is what the TSO regulates, and the regulation direction plus the balancing energy price set the
imbalance price exactly. We therefore model the price the way it is formed: first the probability of
up- or down-regulation, then the price given each direction, mixed into one distribution. The model is
fed the earliest measurable sign of the weather error (measured wind minus the day-ahead wind
forecast) and, for the first two hours, the grid's real-time state 15 minutes before the forecast
time (Fingrid's measured surplus/deficit, frequency, flows and real-time wind and consumption errors).
The conditional price distributions are widened before mixing, so the P10-P90 band and the spike
probabilities are two readings of the same distribution; eight members (seeds, a recent-window
member, an asinh-target member, per weather source) are averaged.

## 2. Approach

**Target.** The day-ahead spot price for the whole 10 h horizon is published before every origin.
The model therefore never forecasts the price level from scratch. It forecasts the **spread**
(imbalance price - spot) for each of the 40 quarter-hours and adds the known spot back. Spikes are
defined on the same spread (> +50 or < -50 EUR/MWh), exactly as the scorer defines them.

**Price mechanism checked first.** From public Fingrid inputs we can rebuild the imbalance price
exactly (`tools/eval/rebuild_price.py`). The volume-weighted rule in force since 1 Jun 2026
reproduces 99.6 % of post-June quarter-hours exactly (MAE 0.01 EUR/MWh). After June, 30 % of
quarter-hours equal the mFRR price and 69 % lie strictly between the mFRR and aFRR prices (a
blend). The old max/min rule reproduces 99.2 % of pre-June quarter-hours (MAE 0.34). So the price is
a deterministic function of the regulation direction and the balancing energy prices. Forecasting it
means forecasting *which way* the system will be regulated and *how expensive* the marginal
balancing energy will be.

**The spread has two modes, so one smooth model is the wrong shape.** On validation, 25 % of
quarter-hours have a spread beyond +-50 EUR/MWh, but a single quantile model never put its p50 there
(0 %). Its p50 sits in the more common "down" mode and pulls toward zero. Its MAE is 26 EUR/MWh on
down-regulated quarter-hours but 77 on up-regulated ones. When the direction is uncertain (p_up
0.35-0.65, 44 % of rows) its MAE is 63; when the direction is confident (23 % of rows) it is 10.

**Model: structural mixture** (`backend/imbalance/mixture.py`). Each member has three parts, all
LightGBM over (origin, step) rows with step and lead time as features:
- **Direction head:** a binary classifier for upward regulation. p_none is the training share of "no
  regulation", and p_down = 1 - p_up - p_none.
- **Price given up-regulation:** quantile regressors of the spread at 7 levels (0.05 to 0.95), trained
  only on up-regulated rows.
- **Price given down-regulation:** the same, trained only on down-regulated rows.
- **Lead-time blocks:** separate price heads for steps 1-8 (first 2 h, driven by the market state at
  the origin) and steps 9-40 (driven by forecasts).

The mixture F(x) = p_up F_up(x) + p_down F_down(x) + p_none 1[x >= 0] gives p10/p50/p90 and the spike
probabilities P(spread > +50) and P(spread < -50) directly. The band around p50 is widened by 1.4,
because the conditional heads are overconfident (chosen per validation week on the other four weeks,
the factor is 1.3-1.5 every time). All heads use 150
trees (regressors) or 110 trees (classifiers), learning rate 0.03 and at least 200 rows per leaf;
learning curves showed early overfitting with more trees.

**Features** (76 per member, all read through the store's availability-masked reader):
- *Market state at the origin:* last usable imbalance prices and spreads (1 h and 4 h windows,
  max/min/mean/std), mFRR direction run length, activated mFRR volumes, mFRR/aFRR prices relative to
  spot, data age.
- *Cross-border:* Swedish (SE1, SE3) and Estonian imbalance prices, cross-border flows, FI-EE
  day-ahead capacity.
- *Known future:* spot for each delivery quarter-hour and its neighbours, spot relative to the
  horizon mean, Fingrid day-ahead wind, consumption and solar forecasts, residual load, calendar.
- *Weather:* national wind power from the newest usable NWP run (power curve at about 10
  capacity-weighted points built from OpenStreetMap turbines), its difference from Fingrid's wind
  forecast, run-to-run change, run age, and temperature. Member `mix_v4b` uses ECMWF IFS 9 km
  (wind-capacity-weighted temperature); `mix_v4mb` uses MET Nordic 2.5 km (population-weighted
  temperature).
- *Observed wind error* (10 features, `features.add_wind_obs`): measured wind generation (Fingrid 75)
  minus Fingrid's day-ahead wind forecast for the same past quarter-hours (last value, 1 h mean, 1 h
  trend), the same error decayed over 1, 3 and 6 h of lead time, a corrected wind forecast and a
  corrected residual load.
- *Real-time grid state* (17 features, `features.add_grid_state`, feature sets v9 / v9m): Fingrid's
  real-time surplus/deficit (198: measured net import minus the confirmed exchange program, i.e.
  Finland's area imbalance), frequency deviation (177), net import (194), electric boiler load (371),
  battery net discharge (398 - 399) and real-time wind (181) and consumption (193) minus the day-ahead
  forecasts; latest value, 1 h and 4 h means, 1 h changes. These 1-3 min series are published within
  1.1-4.1 min (measured), so they are usable 15 min after their quarter-hour ends: at a full-hour
  origin the newest reading ends 15 min before it, against 60 min for the other measured series.

**Lead-time split** (`tools/eval/step_split.py`). Per weather source, the member with the grid state
(`mix_v9b`, `mix_v9mb`) gives steps 1-8 and the member without it (`mix_v4b`, `mix_v4mb`) gives steps
9-40. K = 8 is the mixture's existing block boundary, not tuned. Each row is copied whole from the
model that produced it. Section 4.8 explains why.

**Ensemble.** The two split members differ only in their weather source. Their forecasts are averaged
column by column (`tools/eval/ensemble.py`). Averaging keeps p10 <= p50 <= p90 and all probability
constraints.

**Spike shift** (`tools/eval/spike_shift.py`). One logit shift per spike class,
p' = sigmoid(logit(p) + b), fitted on validation only (b = +0.45 high, +0.60 low). Section 4.7
explains why only the spike outputs are recalibrated.

**Situation-dependent band width** (`tools/eval/band_width.py`). The p10-p90 band is rescaled around
p50 with one factor per lead block (steps 1-8, 9-40) and direction certainty (|p_up - 0.5| below
0.15, 0.15-0.3, at least 0.3), fitted on validation with the organiser's pinball loss. The factors are
physically sensible: 0.6-0.65 when the direction is clear, 0.85-0.9 in between, 1.05-1.1 when it is
uncertain. p50 and all probabilities are unchanged.

## 3. Results

### 3.1 How we got here (validation)

| Model | MAE | Pinball | Coverage | Spike Brier | Direction Brier |
|---|---|---|---|---|---|
| Organiser baseline | 66.20 | 24.18 | 0.683 | 0.1132 | 0.4509 |
| v1: one quantile model, package data only, 500/400 trees | 43.40 | 11.93 | 0.796 | 0.1026 | 0.4183 |
| v2: + ECMWF weather | 43.51 | 11.94 | 0.772 | 0.1024 | 0.4088 |
| v2s: same, fewer trees | 42.99 | 11.83 | 0.845 | 0.0949 | 0.4005 |
| v4s: v2s + observed wind error | 42.77 | 11.84 | 0.844 | 0.0949 | 0.3952 |
| ens_v4s_v4ms: ECMWF and MET Nordic versions averaged, + spike shift | 42.80 | 11.81 | 0.848 | 0.0921 | 0.3906 |
| mix_v4: structural mixture, same features as v4s, no widening | 41.75 | 12.22 | 0.665 | 0.0918 | 0.3952 |
| mix_v4b: + lead-time blocks, widen 1.4 | 41.71 | 11.51 | 0.829 | 0.0913 | 0.3952 |
| mix_v4mb: MET Nordic version of mix_v4b | 41.38 | 11.60 | 0.824 | 0.0907 | 0.3945 |
| ens_mix: mix_v4b and mix_v4mb averaged | 41.42 | 11.53 | 0.827 | 0.0906 | 0.3906 |
| ens_mix + spike shift (held out) | 41.42 | 11.53 | 0.827 | 0.0889 | 0.3906 |
| ens_mix + band width per situation (held out): previous submission | 41.42 | 11.51 | 0.801 | 0.0889 | 0.3906 |
| mix_v9b: mix_v4b + real-time grid state (all steps) | 41.59 | 11.51 | 0.829 | 0.0912 | 0.3968 |
| mix_v9b for steps 1-8, mix_v4b after | 41.57 | 11.48 | 0.830 | 0.0911 | 0.3933 |
| mix_v9mb: mix_v4mb + real-time grid state (all steps) | 41.35 | 11.59 | 0.827 | 0.0906 | 0.3931 |
| ens_mixg: both split members averaged | 41.29 | 11.50 | 0.828 | 0.0904 | 0.3883 |
| ens_mixg + spike shift + band width per situation (held out): previous submission | 41.29 | 11.48 | 0.800 | 0.0885 | 0.3883 |
| mix_v4b, conditional heads widened x2.0 before mixing (no post-hoc spike shift) | 41.70 | 11.49 | 0.828 | 0.0896 | 0.3952 |
| mix_v4b_s2w: same, trained on the last 7 weeks only (seed 2) | 41.27 | 11.43 | 0.810 | 0.0883 | 0.3979 |
| ens_bag8: 8 split members (2 weather sources x {default, seed 1, 7-week window, asinh target}) | 40.99 | 11.38 | 0.830 | 0.0883 | 0.3852 |
| ens_bag8 + band width per situation (held out) | 40.99 | 11.31 | 0.819 | 0.0883 | 0.3852 |
| ens_final: same, spike probabilities averaged 50/50 with the previous chain's (held-out shift); fallback | 40.99 | 11.31 | 0.819 | 0.0874 | 0.3852 |
| **Submission ens_finald: same chain with short-window direction persistence (v9d / v9md) for steps 1-8 (4.9)** | **40.98** | **11.31** | 0.819 | **0.0873** | **0.3848** |

The band-width step is small: pinball 11.60 with one global width chosen held out, 11.51 with the
per-situation widths held out. Against the in-sample global width (11.53) it is better in 65 % of
day resamples, so we adopt it mainly because it puts coverage on the 0.80 target and keeps bands
narrow only where the direction is clear.

Significance (diagnostic, not the official metric): paired bootstrap over validation days.
- **Submission (ens_bag8 + band width) vs previous submission (ens_mixg + spike shift + band width),
  both held out, `tools/eval/bootstrap_compare.py`:** MAE -0.7 %, pinball -1.4 %, spike Brier -0.2 %,
  direction Brier -0.8 %; better in 100 / 97 / 57 / 92 % of 300 day-block resamples. Spikes are a
  draw: the consistent mixture reaches the same spike Brier as the fitted logit shift did, without a
  fitted parameter.
- **ens_mixg chain vs ens_mix chain (same recalibration steps, both held out):**
  MAE -0.30 %, pinball -0.27 %, spike Brier -0.4 %, direction Brier -0.6 %; better in 100 / 99 / 100 /
  100 % of 300 day-block resamples. The gain is small overall because only 8 of 40 steps change.
- Earlier comparisons (2,000 resamples):
- **ens_mix chain vs ens_v4s_v4ms + shift** (the best single-quantile-model version): MAE -3.2 % (better
  in 100 % of resamples, 90 % interval -4.8 to -2.1 %), pinball -2.3 % (100 %), spike Brier -1.6 %
  (87 %). Direction is identical because both use the same direction classifier.
- **ens_v4s_v4ms vs v2s:** direction Brier -2.4 % (94 %), spike Brier -1.3 % (84 %).

### 3.2 By forecast horizon (submission `ens_finald`, held out, validation; `score.py --output-dir` table)

| Hour ahead | Steps | Rows | MAE | Mean pinball p10/p90 | Coverage | Spike Brier | Direction Brier |
|---|---|---|---|---|---|---|---|
| 1 | 1-4 | 2688 | 37.98 | 10.56 | 0.828 | 0.0777 | 0.3532 |
| 2 | 5-8 | 2684 | 39.79 | 10.92 | 0.806 | 0.0818 | 0.3726 |
| 3 | 9-12 | 2680 | 40.72 | 11.28 | 0.825 | 0.0851 | 0.3828 |
| 4 | 13-16 | 2676 | 40.76 | 11.31 | 0.822 | 0.0863 | 0.3822 |
| 5 | 17-20 | 2672 | 40.88 | 11.32 | 0.815 | 0.0874 | 0.3818 |
| 6 | 21-24 | 2668 | 41.28 | 11.37 | 0.816 | 0.0887 | 0.3863 |
| 7 | 25-28 | 2664 | 41.61 | 11.42 | 0.818 | 0.0900 | 0.3895 |
| 8 | 29-32 | 2660 | 41.92 | 11.50 | 0.819 | 0.0911 | 0.3947 |
| 9 | 33-36 | 2656 | 42.32 | 11.64 | 0.822 | 0.0922 | 0.4007 |
| 10 | 37-40 | 2652 | 42.55 | 11.81 | 0.816 | 0.0933 | 0.4045 |

For reference, the previous chain without bagging (ens_mixg + shift + band width) scored at hours
1 / 2 / 4 / 6 / 8 / 10: MAE 38.1 / 40.1 / 41.1 / 41.7 / 42.2 / 42.8, pinball 10.57 / 10.94 / 11.48 /
11.60 / 11.77 / 11.96, direction Brier 0.356 / 0.379 / 0.386 / 0.389 / 0.397 / 0.408.

Skill decays slowly with lead time. The real-time grid state gives the first hour its edge (direction
Brier -4.8 % and MAE -2.6 % against the members without it). The bagging gains grow with lead time
(pinball -1.5 % at 4 h to -2.3 % at 8 h), which is where single members disagree most. The spike
Brier of the first two hours is slightly worse than with the fitted logit shift and better from 6 h on.

### 3.3 What each part of the model uses (SHAP, member mix_v4b, validation sample)

Share of mean |SHAP| by feature group, for the direction head and the median price heads (%):

| Feature group | Direction | Up price, 0-2 h | Down price, 0-2 h | Up price, 2-10 h | Down price, 2-10 h |
|---|---|---|---|---|---|
| Physical forecasts (wind, consumption, solar, NWP) | **48** | 17 | 6 | **36** | 16 |
| Market state at the origin | 19 | **49** | 29 | 23 | 10 |
| Spot | 19 | 17 | **57** | 20 | **63** |
| Cross-border | 5 | 5 | 6 | 5 | 8 |
| Observed wind error | 3 | 9 | 2 | 7 | 2 |
| Calendar and lead time | 6 | 2 | 1 | 9 | 1 |

Each part of the structure learns from the drivers that physically matter for it:
- **Direction** follows the physical forecasts: wind, consumption and their errors decide whether the
  system ends up short or long.
- **The up-regulation price in the first two hours** follows the current market state (the last
  imbalance prices and mFRR activations persist). Later it follows the physical forecasts.
- **The down-regulation price** follows spot: when the system is long, the price falls from the spot
  level toward the cheapest down-regulation bids.
- **Cross-border signals** (Swedish and Estonian imbalance prices, flows) add a steady 5-8 %. The Nordic
  balancing market is shared, so they are informative but secondary.

The per-row `top_drivers` column lists the three features with the largest SHAP contribution to the
direction head of the first member (`mix_v9b` for steps 1-8, where grid-state features often appear,
and `mix_v4b` after). The table above is for `mix_v4b`.

### 3.4 What the data allows: the error floor (validation, submission rows)

The MAE is a spike-timing score wearing an accuracy label. Decomposing the submission's P50 error by
the realised |imbalance - spot|:

| \|spread\| bucket, EUR/MWh | 0-10 | 10-25 | 25-50 | 50-100 | 100-200 | > 200 |
|---|---|---|---|---|---|---|
| Share of quarter-hours | 21 % | 28 % | 26 % | 16 % | 7 % | 1.8 % |
| Share of MAE | 5 % | 8 % | 15 % | 23 % | 23 % | 26 % |

Reference points on the same 26,700 rows:

| P50 rule | MAE |
|---|---|
| Organiser baseline (last usable price) | 66.2 |
| P50 = spot ("no regulation") | 46.6 |
| **Submission** | **41.0** |
| Oracle: realised direction known, spread = that direction's median | 35.6 |
| Oracle: realised direction and spike class known, conditional medians | 25.0 |

The oracles read the realised outcome and are upper bounds, not models. Spot alone already reaches
46.6, so the whole modelling effort is worth 5.6 EUR/MWh of P50; even perfect direction knowledge
stops at 35.6; and reaching 30 would need to know, hours ahead, which quarter-hours spike. Scaling
the forecast spread toward spot by 0.5 worsens MAE to 43.2 and scaling by 1.25 improves it only to
40.8, so P50 sits where the data wants it. This is why the design effort went into the probabilities
and the band rather than into the point forecast, and why skill should be judged per lead block
against persistence (Belgium: 12-25 % at 1-8 quarter-hours, arXiv 2605.17045; Austria t+15 min: MAE
-12 %, pinball -19 %, arXiv 2605.09061) rather than as a single number.

### 3.5 Reliability of the probabilities

Reliability diagrams (10 probability bins, bins with at least 30 rows, `docs/slides/plots.py`) lie on
the diagonal for the high spike, the low spike and the up-regulation probability: when the model
says 40 %, the event follows about 40 % of the time. The highest populated bins are 50-55 % for the
spike probabilities and 70-75 % for up-regulation; the model does not issue probabilities it cannot
support. Coverage of the P10-P90 band is 80-83 % in every lead block (baseline 68 %). No post-hoc
calibration is applied beyond the held-out band widths described in section 2.

## 4. Findings (the reasoning chain behind the design)

### 4.1 The price is mechanical; the uncertainty is the regulation
The exact rebuild (section 2) means we need not model the pricing rule. The forecastable quantities
are the regulation direction and the balancing energy prices, and both follow from the system's
forecast error.

### 4.2 Model the structure, not a smoothed average
Splitting the forecast into a direction head and price-given-direction heads cut MAE by 1 EUR/MWh and
improved spike Brier without any calibration (mix_v4 vs v4s, same features). The direction head is
the bottleneck now: every member shares it, and the hours with uncertain direction carry most of the
remaining error.

### 4.3 The useful weather signal is the *observed* error, not the NWP
`tools/eval/wind_corrector.py` compares wind forecasts against Fingrid's measured wind generation.
- Persistence of the observed error (measured wind minus Fingrid's day-ahead forecast, decaying with
  lead time) beats Fingrid's day-ahead forecast. MAE is 299 vs 321 MW overall and 235 vs 320 MW at
  0-2 h ahead.
- Learned NWP correctors from 10 sites do **not** beat Fingrid with three summer months of training
  (381-403 MW).
- Our generic power-curve proxy is off by about 1,000 MW, and its error is seasonal: mean wind
  generation was 1,755 MW in training and 2,603 MW in validation. Fingrid's day-ahead wind forecast
  already carries most of the NWP information.

### 4.4 Weather-model disagreement did not help either
Feature sets v6/v6m add the second NWP model's wind, the ECMWF vs MET Nordic disagreement and the
spread of the three wind forecasts (both models and Fingrid). The averaged pair scores 42.78 / 11.80 /
0.0947 / 0.3949 against 42.80 / 11.81 / 0.0936 / 0.3906 without them: noise-level gains and worse
spikes and direction. Large disagreements happen at high wind, when prices sit calmly in the down
mode, so absolute disagreement mostly measures the wind level.

### 4.5 Forecasting the imbalance volume did not improve direction
Direction is the sign of the system imbalance, so we tried a regression on the net activated mFRR
volume (Fingrid 375 + 376, MW) and fed its out-of-fold forecast into the direction head
(`backend/imbalance/volume.py`; 5 time blocks with 1-day gaps). The volume forecast correlates
0.30-0.35 with the realised volume, but direction Brier of P(up) moves only from 0.1967 to 0.1971
(ECMWF member) and 0.1985 to 0.1972 (MET Nordic member): noise. The regressor sees the same features
as the direction classifier, so it adds no new information. Further direction gains need new
information, not re-stacking.

### 4.6 More history did not help the direction head
A direction head trained on public history since 20 Mar 2025 (about 4x the data, expanding window,
strictly out-of-sample, `tools/training/hist_heads.py`) beats a June-only head on its own (Brier
0.2126 vs 0.2175). Inside the main model it adds nothing (ens_v5s_v5ms: 42.73 / 11.83 / 0.0952 /
0.3916). The gains came from new physical information and structure, not from more data of the same
kind.

### 4.7 Calibrate only what is biased
- **Full recalibration does not hold up out of sample.** We tried band width, direction and spike
  calibration together (`tools/eval/calibrate.py`), fitted on one half of the validation days and
  scored on the other. Pinball got worse (+0.7 %), direction got worse (+2.2 %) and only spikes
  improved (-2.3 %).
- **Spikes are under-predicted in every full validation week.** The single quantile models predict
  8.0 % (high) and 9.1 % (low) on average, while 12.1 % and 13.0 % occur. Training is mostly summer,
  and autumn is spikier. The mixture model is closer but still low.
- **Spike shift, held out.** One logit shift per class, fitted on four weeks and scored on the fifth,
  improves spike Brier from 0.0906 to 0.0889 (-2.0 %) for the submission. Probability ranking is
  unchanged.
- **Does the shift transfer to retrained models?** The test forecasts come from models retrained up
  to 4 Oct, so the shift fitted on the validation models is applied to different models.
  `tools/eval/spike_shift_backtest.py` replays the recipe one period earlier, on training data only:
  - early spike models trained on targets usable before 9 Aug;
  - shift fitted on their errors from 9 Aug to 6 Sep (b = +0.74 high, +0.96 low);
  - shift applied to the validation ensemble of the single quantile models.

  Spike Brier on validation improves from 0.0936 to 0.0927, even though that shift is larger than
  the best one for validation. The under-prediction recurs period after period, so we apply the
  validation-fitted shift to the test forecasts. It raises the mean test spike probabilities from
  11.6 % to 16.0 % (high) and from 4.9 % to 7.3 % (low).

- **The shift disappears when the mixture is made consistent (final submission).** Widening the
  conditional quantile heads x2.0 around their medians *before* mixing (instead of widening the mixed
  P10/P90 x1.4 afterwards) raises the mixture's own spike probabilities to the observed rate: the
  spike shift refitted on top of `ens_bag8` is +0.05 (high) and +0.01 (low) and *hurts* held out
  (+1.4 % Brier), so it is dropped. The under-prediction was the under-dispersion of the conditional
  heads (raw coverage 0.67), not a bias of the spike classifier. See 4.9.

### 4.8 Fresh grid state helps only the first two hours
Finland's real-time surplus/deficit is the closest public reading of the quantity that sets the
direction, and Fingrid publishes it within minutes (`tools/eval/fingrid_delay.py`: 1.1-4.1 min over
6 polls for all eight series). With a 15 min rule the model sees the grid 45 min fresher than through
the 60 min measured series. Against `mix_v4b` on the same data, `mix_v9b` improves direction Brier by
5.1 % at steps 1-2 and 3.4 % at steps 3-4 (MAE -3.4 % and -2.5 %), in all five validation weeks.
Beyond step 8 the extra features only add noise (+1 % direction Brier), which cancels the gain in the
overall average (41.59 / 11.51 / 0.0912 / 0.3968 vs 41.71 / 11.51 / 0.0913 / 0.3952). Using the
grid-state members only for the first lead block keeps the gain and removes the noise. This is the
first direction improvement since the observed wind error, and it came, as section 4.6 predicted,
from new information rather than more data of the same kind.

### 4.9 One distribution, three outputs; then average more of it
- **Why the fixed x1.4 band and the spike shift were two patches on one problem.** The mixture
  F = p_up F_up + p_down F_down + p_none 1[x >= 0] already gave P10/P50/P90 and the spike
  probabilities (section 4.2), but the conditional heads are under-dispersed (7 quantile knots on
  6-50k rows each, raw coverage 0.67), so the bands were widened after mixing and the spikes shifted
  separately. Widening each conditional head around its median before mixing (factor 2.0, held out
  per validation week in the 1.7-2.0 range) fixes both from one place: pinball 11.505 -> 11.494 and
  spike Brier 0.0913 -> 0.0896 on `mix_v4b` with no retraining, and the fitted spike shift goes to
  zero. The marginal P50 is taken from the unwidened mixture (widening moves the mixture median when
  the components are asymmetric; MAE 41.70 either way, so this only protects it). Tails beyond the
  5 % / 95 % knots are extrapolated exponentially instead of linearly (negligible on validation,
  but the 0.5 % quantile no longer sits 0.9 knot-widths out on a series that reaches +-5,000 EUR/MWh).
- **Bagging is the largest single gain since the mixture itself.** Per weather source and per lead
  block we average four members: the default fit, a second seed, a member trained on the last seven
  weeks before the cutoff only, and a member whose quantile heads are fitted to asinh(spread / 50)
  (quantiles are equivariant, so they are mapped back exactly). The seven-week member alone is the
  best single model (MAE 41.27, pinball 11.43 on ECMWF; the regime since July is more spiky than
  June), and the asinh member is the most different one. The eight-member average beats the previous
  two-member chain in 100 % (MAE), 97 % (pinball) and 92 % (direction) of day-block resamples.
  `tools/training/bag.py` trains one member per run; `tools/eval/mix_variants.py` scores
  inference-time variants of a trained member without retraining.
- **Spike hedge (final step).** The consistent mixture and the logit-shifted classifier reach the
  same spike Brier by different routes (0.0883 and 0.0885) with different errors, so they are
  worth averaging. Their 50/50 average (weight fixed, not tuned) scores 0.0874 and beats the
  previous submission in 92 % of day-block resamples. Brier is convex, so the average can never be
  worse than the mean of the two; p10/p50/p90 and direction stay from ens_bag8d (averaging those too
  was worse: MAE 41.13). The partner is the unbagged chain of the same members, `ens_mixgd_spk_bw`;
  the result is the submission `ens_finald`.
- **Longer persistence features did not help (not adopted).** Feature set v10 adds spike shares over
  4 / 12 / 24 h, quarter-hours since the last spike, and the 24 h direction mean to v9. Paired by
  seed against v9: MAE 41.58 vs 41.59 and 41.62 vs 41.44, pinball 11.53 vs 11.50 and 11.59 vs 11.49.
  The 4 h windows already in v1 (`dir_run_len`, `dir_mean16`, `spread_std16`) carry the signal; this
  matches the Belgian and Norwegian finding that only the most recent lags matter.
- **Short-window direction persistence did help (adopted, v9d / v9md).** Instead of 24 h shares, v9d
  adds to v9 the share of up / down / none quarter-hours over the last 1 / 2 / 4 h, quarter-hours
  since the direction last changed, up/down flips in 4 h, spike counts over 1 / 3 / 12 h with the time
  since the last high / low spike, and the largest |spread| in 4 h (same sources and 60 min lag group
  as v1; no new data). Single members, steps 1-8: direction Brier 0.3758 -> 0.3726 (ECMWF) and
  0.3671 -> 0.3643 (MET Nordic), MAE -0.2 / -0.3. Swapped in for v9 / v9m through the whole chain,
  `ens_final` -> `ens_finald` on validation: MAE 40.994 -> 40.976, pinball 11.312 -> 11.312, spike
  Brier 0.0874 -> 0.0873, direction Brier 0.3852 -> 0.3848; day-block resamples won 86 % / 52 % / 81 %
  / 98 %. Small but in the same direction on every Level 1 metric; `ens_final` is kept as fallback.

## 5. Data availability and leakage

- Every row is used at origin t only if `first_usable_origin_utc <= t`. All feature access goes through
  `backend/imbalance/features.py` (`Store.get`, `latest_index`), which masks unusable rows as missing.
- Rows we added get conservative availability times:
  - **Fingrid measured wind (75):** end of the quarter-hour + 60 min, then the next full hour.
  - **Fingrid real-time grid state (198, 177, 194, 371, 398, 399, 181, 193):** end of the
    quarter-hour + 15 min, then the next full hour (measured publication delay 1.1-4.1 min, so more
    than 3x margin). Only complete quarter-hours are kept (all 1-3 min values present).
  - **NWP runs:** measured publication delay + 10 min + about 1 h margin, rounded up to the next full
    hour. ECMWF IFS: init + 8 h (measured 6 h 48 min). MET Nordic: init + 2 h (measured 34 min). Only
    the Open-Meteo Single Runs API is used, never a historical-forecast endpoint.
  - Fingrid forecast datasets are never fetched from the API, which keeps only their latest version.
    They come vintaged from the organiser's package (the day-ahead wind forecast, dataset 246, is
    usable from D-1 13:00 Finnish time).
- **Leakage check** (`tools/eval/leakage.py`). For randomly sampled origins, the features are rebuilt
  from a copy of the data from which every row and NWP run not yet usable at that origin has been
  physically deleted. They must match the training and inference features exactly. Feature sets v4
  and v4m pass on 200 random origins each (40 steps, 76 features), covering training, validation and
  test origins, and again on 40 origins after the last change to the feature code. Feature sets v9
  and v9m (grid state, 93 features) pass on 90 and 60 random origins. A unit test
  (`backend/tests/test_grid_state.py`) also checks that changing not-yet-usable rows leaves the
  grid-state features unchanged.
- **Hard guards in training:** no target and no origin after 2026-10-04T20:45Z. The validation
  versions train only on targets usable before 2026-09-06T21:00Z.
- **Calibration data:** the band widths (and, in the spike hedge, the previous chain's spike shift) use
  validation outcomes only, never the test period.
- **Revised values of real-time series.** Fingrid's API returns the current (possibly corrected)
  values, not the first published ones, and the first-published values cannot be verified for past
  dates. We use the dataset values with the conservative publication times above; the real-time
  features are used only for steps 1-8.
- **Pre-June data.** Pre-June Fingrid mFRR/aFRR series are used only for the long-history heads
  (4.6, not in the submission). The pre-June imbalance price is never used, as a target or as a
  feature, because it was calculated under the old pricing rule.
- **Remaining look-ahead, metadata only:** the wind-site locations (OpenStreetMap snapshot, 6 Nov
  2026) and the capacity total (Renewables Finland, 30 Jun 2026) are static. Capacity built later in
  2026 is slightly reflected in the site weights. These are weights of sampling points, not values of
  any time series.

## 6. Economic value (validation, diagnostic)

`tools/eval/economic_value.py` scores a fixed decision rule with the submitted validation forecasts
and the realised prices, and compares it with the same rule on the persistence baseline and with
perfect foresight. One MW of flexibility (an electric boiler or CHP headroom) is dispatched one hour
ahead (step 5 of the origin one hour before delivery): raise output or cut load for the quarter-hour
when P(spike high) >= 0.3, take load when P(spike low) >= 0.3. Each action earns the realised spread
in the acting direction times 0.25 MWh, minus an activation cost per MWh (efficiency, wear, heat-side
rebalancing). The four validation weeks are annualised by 13.

| Activation cost, EUR/MWh | Submission, 1 h ahead | Submission, 4 h ahead | Persistence rule | Perfect foresight |
|---|---|---|---|---|
| 0 | 28.3 kEUR/MW/yr | 20.7 | 22.9 | 61.8 |
| 20 | **15.4** | 7.9 | 10.2 | 50.9 |
| 40 | 2.6 | -4.9 | -2.5 | 40.0 |

The persistence rule acts when the last usable spread exceeds 50 EUR/MWh in either direction; it is a
fair naive strategy (the organiser's constant 12 % spike probabilities never trigger). Acting on the
P50 alone (forecast spread beyond 50) triggers 18 times in four weeks and earns almost nothing: the
point forecast is the wrong decision variable, the probability is the right one. The mean |spread| on
validation is 43.4 EUR/MWh, the expected cost of one MWh of imbalance left uncorrected.

Caveats: four weeks of outcomes; single-price imbalance settlement assumed; no intraday alternative
modelled; marginal costs, heat constraints and already-committed capacity are Turku Energia's internal
data, which the brief names as the next step. The figures scale linearly with the flexible MW and are
meant to size the opportunity, not to forecast a P&L.

## 7. Limitations and risks

- **Four months of summer and early-autumn training data.** October has more wind, the first heating
  demand and the 25 Oct DST change. The spike shift addresses the frequency bias seen so far, but
  October's regime may differ more than September's did.
- **The spike shift is applied to retrained models.** The backtest in section 4.7 supports it, but it
  rests on a single earlier period. If the October spike rate falls back to summer levels, the shift
  will over-predict spikes.
- **The up-regulation heads see fewer rows.** About a third of the training quarter-hours are
  up-regulated (32,875 of 93,620 in the validation version; 6,590 in the 0-2 h block). Their tails are
  the least certain part of the model.
- **Real-time series have gaps.** 84-91 % of quarter-hours are complete for most grid-state series;
  the model then uses the latest complete one (its age is a feature). The 1 h change features are
  missing for about a quarter of test rows, which LightGBM handles as missing values.
- **Model, width and feature-set choices were made on validation.** This is allowed but makes the
  validation scores slightly optimistic. We limited it by choosing between few, physically motivated
  variants, by checking the width week by week, and by bootstrap checks.

## 8. Reproduce

Requires `FINGRID_API_KEY` (free). The Open-Meteo pulls use the free tier and resume from their cache.

```bash
uv sync
uv run python -m tools.cli ingest starter --src tools/starter_package/data
uv run python -m tools.cli ingest windsites
uv run python -m tools.cli ingest locations
uv run python -m tools.cli ingest fingrid --datasets 75 --start 2026-05-31 --end 2026-11-02T07:00
uv run python -m tools.cli ingest fingrid --datasets 198,177,194,371,398,399,181,193 --start 2026-05-31 --end 2026-11-02T07:00
uv run python -m tools.cli ingest openmeteo --models ecmwf_ifs --group wind
uv run python -m tools.cli ingest openmeteo --models metno_nordic --group wind
uv run python -m tools.cli ingest openmeteo --models metno_nordic --group pop
uv run python -m tools.cli features --set v4
uv run python -m tools.cli features --set v4m
uv run python -m tools.cli features --set v9d
uv run python -m tools.cli features --set v9md
for C in mix_v4b mix_v4mb mix_v9db mix_v9mdb; do
  uv run python -m tools.training.mixture_pipeline --config tools/training/configs/$C.yaml   # default member
  for P in val test; do
    # default member re-read with the consistent mixture settings (no retraining) -> <C>_s0
    uv run python -m tools.eval.mix_variants --model $C$([ $P = val ] && echo -val) --period $P --widen 2.0 --modes component50 --tails exp
    cp static_data/work/submissions/${C}$([ $P = val ] && echo -val)__w2.00_component50_exp_$P.csv static_data/work/submissions/${C}_s0$([ $P = val ] && echo -val)_$P.csv
    # bagging members: seed 1; seed 2 on the last 7 weeks before the cutoff; seed 3 with asinh target
    W=$([ $P = val ] && echo 2026-07-20 || echo 2026-08-17); M=$([ $P = val ] && echo val || echo final)
    uv run python -m tools.training.bag --config tools/training/configs/$C.yaml --member s1  --mode $M --widen 2.0 --widen-mode component50 --tail exp
    uv run python -m tools.training.bag --config tools/training/configs/$C.yaml --member s2w --mode $M --train-start $W --widen 2.0 --widen-mode component50 --tail exp
    uv run python -m tools.training.bag --config tools/training/configs/$C.yaml --member s3a --mode $M --widen 2.0 --widen-mode component50 --tail exp
  done
done
for P in val test; do S=$([ $P = val ] && echo -val); M=""
  for V in s0 s1 s2w s3a; do
    uv run python -m tools.eval.step_split --name split_v9db_v4b_$V --early mix_v9db_$V$S --late mix_v4b_$V$S --period $P
    uv run python -m tools.eval.step_split --name split_v9mdb_v4mb_$V --early mix_v9mdb_$V$S --late mix_v4mb_$V$S --period $P
    M="$M split_v9db_v4b_$V split_v9mdb_v4mb_$V"
  done
  uv run python -m tools.eval.ensemble --name ens_bag8d --members $M --period $P
done
uv run python -m tools.eval.band_width --model ens_bag8d --apply
# previous chain of the same members (x1.4 band, spike logit shift, band widths) -> ens_mixgd_spk_bw
for P in val test; do S=$([ $P = val ] && echo -val)
  uv run python -m tools.eval.step_split --name split_v9db_v4b --early mix_v9db$S --late mix_v4b$S --period $P
  uv run python -m tools.eval.step_split --name split_v9mdb_v4mb --early mix_v9mdb$S --late mix_v4mb$S --period $P
  uv run python -m tools.eval.ensemble --name ens_mixgd --members split_v9db_v4b split_v9mdb_v4mb --period $P
done
uv run python -m tools.eval.spike_shift --model ens_mixgd --apply
uv run python -m tools.eval.band_width --model ens_mixgd_spk --apply
# spike columns averaged 50/50 with ens_mixgd_spk_bw (see 4.9) -> ens_finald_test.csv = forecast_backtest.csv
for P in val test; do uv run python -m tools.eval.spike_hedge --base ens_bag8d_bw --other ens_mixgd_spk_bw --name ens_finald --period $P; done
uv run python -m tools.eval.bootstrap_compare --a ens_final --b ens_finald --n 300   # diagnostic
```

Each `mixture_pipeline` run trains the validation and final versions, scores the validation version
with `score.py`, exports the test file through `validate_submission.py` and runs the leakage check.

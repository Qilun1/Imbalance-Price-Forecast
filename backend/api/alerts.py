"""Turns one forecast, and the one before it, into the situations worth a person's attention.

Covers the situations in the challenge brief (section 02, Level 2): spike risk has increased, up or
down regulation is expected, the forecast changed materially, signals conflict, and the situation is
worth an expert review. High uncertainty and stale data are added because the brief asks the solution
to recognise when the error may be large.

Alerts say what to check, never what to do. Open data cannot tell what capacity is free or what it
costs, so the brief limits the first phase to suggestions to review.

Conflicting signals means independent sources disagree, as in the brief: the main forecast is compared
with a second model built on different input data (lgbm_v2 adds ECMWF weather to lgbm_v1's Fingrid
forecasts), made at the same origin. Comparing two outputs of the same model would not show that.

Thresholds were set on validation-period forecasts of lgbm_v1-val (and lgbm_v2-val for the conflict
gaps) only, never on test data (AGENTS.md rule 4). They are rare by design: the percentages below are
shares of validation rows or moves.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.api.labels import label_for
from backend.api.schemas import Alert, Driver, Situation, SituationHour

STEP = pd.Timedelta(minutes=15)
HOUR = pd.Timedelta(hours=1)
DISPLAY_TZ = "UTC"
NORMAL_DATA_AGE_MINUTES = 75
_RISK_KINDS = ("spike_risk", "forecast_changed", "high_uncertainty", "regulation_expected")
_KIND_WORDS = {"spike_risk": "exceptional price risk", "forecast_changed": "a forecast revision",
               "high_uncertainty": "high uncertainty", "regulation_expected": "expected regulation"}


@dataclass(frozen=True)
class Thresholds:
    p50_revision: float = 25.0          # EUR/MWh, top 1 % of hour-on-hour moves
    spike_high_rise: float = 0.16       # top 1 % of hour-on-hour moves
    spike_low_rise: float = 0.21        # top 1 %
    spike_high_level: float = 0.40      # top 1 % of levels
    spike_low_level: float = 0.70       # top 1 %
    interval_width: float = 200.0       # EUR/MWh, top 5 % of P90 - P10 widths
    up_level: float = 0.70              # top 5 %
    down_level: float = 0.93            # top 5 %; down is the usual state, so the bar is high
    conflict_p50_gap: float = 45.0      # EUR/MWh between the two models, top 1 % of rows
    conflict_direction_gap: float = 0.30    # p_up apart and pointing different ways, top 1 %
    conflict_spike_high_gap: float = 0.34   # top 1 %
    conflict_spike_low_gap: float = 0.49    # top 1 %
    stale_minutes: int = 135            # one forecast hour later than normal
    min_quarters: int = 2               # ignore single quarter-hour flickers
    regulation_quarters: int = 4        # regulation must hold for an hour to be worth a note


THRESHOLDS = Thresholds()


def _runs(mask: np.ndarray, min_length: int, bridge: int = 2) -> list[tuple[int, int]]:
    """(first, last) positions of runs holding at least min_length True quarter-hours. Gaps of up to
    `bridge` quarter-hours are closed, so a quiet moment does not split one situation into several."""
    positions = np.flatnonzero(mask)
    if not len(positions):
        return []
    groups = np.split(positions, np.flatnonzero(np.diff(positions) > bridge + 1) + 1)
    return [(int(g[0]), int(g[-1])) for g in groups if len(g) >= min_length]


def _clock(ts: pd.Timestamp) -> str:
    return ts.tz_convert(DISPLAY_TZ).strftime("%H:%M")


def _span(rows: pd.DataFrame) -> str:
    return f"{_clock(rows['delivery_start_utc'].iloc[0])}–{_clock(rows['delivery_start_utc'].iloc[-1] + STEP)} UTC"


def _drivers(rows: pd.DataFrame, n: int = 3) -> list[Driver]:
    """The forecast's top_drivers are SHAP contributions of the direction classifier, so they explain
    the regulation direction, not the price level or the spike probability; the wording says so."""
    counts = Counter(name for text in rows["top_drivers"].dropna() for name in text.split(";") if name)
    return [Driver(id=name, label=label_for(name)) for name, _ in counts.most_common(n)]


def _because(drivers: list[Driver]) -> str:
    names = [d.label for d in drivers]
    if not names:
        return ""
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f" Drivers of the regulation direction: {listed}."


def _alert(kind: str, rows: pd.DataFrame, title: str, sentence: str, check: str, evidence: dict[str, float],
           severity: str = "watch") -> Alert:
    drivers = _drivers(rows)
    return Alert(kind=kind, severity=severity, title=title,
                 message=f"{sentence}{_because(drivers)} Worth checking {check}.", check=check,
                 window_start_utc=rows["delivery_start_utc"].iloc[0],
                 window_end_utc=rows["delivery_start_utc"].iloc[-1] + STEP,
                 drivers=drivers, evidence={k: round(float(v), 4) for k, v in evidence.items()})


def _with_previous(current: pd.DataFrame, previous: pd.DataFrame | None) -> pd.DataFrame:
    cur = current.sort_values("step").reset_index(drop=True)
    columns = ["p50", "p_up", "p_spike_high", "p_spike_low"]
    if previous is None:
        return cur.assign(**{f"{c}_previous": np.nan for c in columns})
    earlier = previous[["delivery_start_utc", *columns]].rename(columns={c: f"{c}_previous" for c in columns})
    return cur.merge(earlier, on="delivery_start_utc", how="left")


def _spike(cur: pd.DataFrame, side: str, rise_at: float, level_at: float, th: Thresholds) -> list[Alert]:
    column = f"p_spike_{side}"
    rise = (cur[column] - cur[f"{column}_previous"]).to_numpy()
    level = cur[column].to_numpy()
    out = []
    for a, b in _runs((rise >= rise_at) | (level >= level_at), th.min_quarters):
        rows = cur.iloc[a:b + 1]
        window_rise = np.nanmax(rise[a:b + 1]) if np.isfinite(rise[a:b + 1]).any() else 0.0
        verb = "has increased" if window_rise >= rise_at else "is elevated"
        wide = bool(((rows["p90"] - rows["p10"]) >= th.interval_width).any())
        note = " Uncertainty is high in this window." if wide else ""
        out.append(_alert("spike_risk", rows, f"Risk of an exceptionally {side} price",
                          f"The risk of an exceptionally {side} price {verb} for {_span(rows)}.{note}",
                          "the production plan and market position",
                          {"peak_probability": level[a:b + 1].max(), "largest_rise": window_rise}))
    return out


def _revision(cur: pd.DataFrame, th: Thresholds) -> list[Alert]:
    change = (cur["p50"] - cur["p50_previous"]).to_numpy()
    out = []
    for a, b in _runs(np.abs(np.nan_to_num(change)) >= th.p50_revision, th.min_quarters):
        rows = cur.iloc[a:b + 1]
        part = change[a:b + 1]
        largest = part[np.argmax(np.abs(part))]
        word = "up" if largest > 0 else "down"
        out.append(_alert("forecast_changed", rows, "Forecast changed since the previous update",
                          f"The price forecast for {_span(rows)} moved {word} by up to {abs(largest):.0f} EUR/MWh "
                          "since the previous update.",
                          "trading and the production plan", {"largest_p50_change": largest}))
    return out


def _regulation(cur: pd.DataFrame, th: Thresholds) -> list[Alert]:
    out = []
    for column, word, level_at in (("p_up", "up", th.up_level), ("p_down", "down", th.down_level)):
        for a, b in _runs(cur[column].to_numpy() >= level_at, th.regulation_quarters):
            rows = cur.iloc[a:b + 1]
            out.append(_alert("regulation_expected", rows, f"{word.capitalize()}-regulation expected",
                              f"The system is expected to need {word}-regulation for {_span(rows)}.",
                              "whether flexible capacity is worth offering to the reserve markets",
                              {"peak_probability": rows[column].max()}))
    return out


def _uncertainty(cur: pd.DataFrame, th: Thresholds) -> list[Alert]:
    width = (cur["p90"] - cur["p10"]).to_numpy()
    out = []
    for a, b in _runs(width >= th.interval_width, th.min_quarters):
        rows = cur.iloc[a:b + 1]
        out.append(_alert("high_uncertainty", rows, "High forecast uncertainty",
                          f"The P10–P90 range for {_span(rows)} is unusually wide, up to {width[a:b + 1].max():.0f} EUR/MWh.",
                          "the market position before relying on the central forecast",
                          {"largest_width": width[a:b + 1].max()}))
    return out


def _conflict(cur: pd.DataFrame, other: pd.DataFrame | None, th: Thresholds) -> list[Alert]:
    """Where the main forecast and the independent second model disagree on the same quarter-hours."""
    if other is None:
        return []
    columns = ["p50", "p_up", "p_down", "p_spike_high", "p_spike_low"]
    both = cur.merge(other[["delivery_start_utc", *columns]], on="delivery_start_utc", how="left",
                     suffixes=("", "_other"))
    gap = {c: (both[c] - both[f"{c}_other"]).abs().to_numpy() for c in columns}
    ways_differ = np.sign(both["p_up"] - both["p_down"]) != np.sign(both["p_up_other"] - both["p_down_other"])
    tests = (("the price level", gap["p50"] >= th.conflict_p50_gap),
             ("the regulation direction", (gap["p_up"] >= th.conflict_direction_gap) & ways_differ.to_numpy()),
             ("the risk of an exceptionally high price", gap["p_spike_high"] >= th.conflict_spike_high_gap),
             ("the risk of an exceptionally low price", gap["p_spike_low"] >= th.conflict_spike_low_gap))
    out = []
    for a, b in _runs(np.logical_or.reduce([hit for _, hit in tests]), th.min_quarters):
        rows = both.iloc[a:b + 1]
        topics = [topic for topic, hit in tests if hit[a:b + 1].any()]
        listed = topics[0] if len(topics) == 1 else ", ".join(topics[:-1]) + " and " + topics[-1]
        out.append(_alert("conflicting_signals", rows, "Models disagree",
                          f"For {_span(rows)} the forecast and a second model built on different input data "
                          f"disagree on {listed}.",
                          "the market situation by hand before relying on the forecast",
                          {"largest_p50_gap": np.nanmax(gap["p50"][a:b + 1]),
                           "largest_direction_gap": np.nanmax(gap["p_up"][a:b + 1]),
                           "largest_spike_gap": np.nanmax(np.maximum(gap["p_spike_high"], gap["p_spike_low"])[a:b + 1])}))
    return out


def _stale(cur: pd.DataFrame, th: Thresholds) -> list[Alert]:
    cutoff = cur["data_cutoff_utc"].iloc[0]
    if pd.isna(cutoff):
        return []
    age = (cur["forecast_origin_utc"].iloc[0] - cutoff) / pd.Timedelta(minutes=1)
    if age < th.stale_minutes:
        return []
    return [Alert(kind="stale_data", severity="review", title="Data is older than usual",
                  message=f"The latest price used is {age:.0f} minutes old; {NORMAL_DATA_AGE_MINUTES} is normal. "
                          "Worth checking the data feeds before relying on this forecast.",
                  check="the data feeds before relying on this forecast",
                  window_start_utc=cur["delivery_start_utc"].iloc[0],
                  window_end_utc=cur["delivery_start_utc"].iloc[-1] + STEP,
                  drivers=[], evidence={"data_age_minutes": float(age)})]


def _expert_reviews(cur: pd.DataFrame, alerts: list[Alert], th: Thresholds) -> list[Alert]:
    """Where two different kinds of risk overlap, the situation deserves a person's judgement."""
    starts = cur["delivery_start_utc"]
    kinds: list[set[str]] = [set() for _ in range(len(cur))]
    for alert in alerts:
        if alert.kind in _RISK_KINDS:
            hit = (starts >= pd.Timestamp(alert.window_start_utc)) & (starts < pd.Timestamp(alert.window_end_utc))
            for i in np.flatnonzero(hit.to_numpy()):
                kinds[i].add(alert.kind)
    out = []
    for a, b in _runs(np.array([len(k) >= 2 for k in kinds]), th.min_quarters):
        rows = cur.iloc[a:b + 1]
        present = [_KIND_WORDS[k] for k in _RISK_KINDS if any(k in s for s in kinds[a:b + 1])]
        listed = ", ".join(present[:-1]) + " and " + present[-1]
        out.append(_alert("expert_review", rows, "Worth an expert review",
                          f"Several signals overlap for {_span(rows)}: {listed}.",
                          "the production plan, trading and use of capacity", {"signals": len(present)},
                          severity="review"))
    return out


def build_alerts(current: pd.DataFrame, previous: pd.DataFrame | None, challenger: pd.DataFrame | None = None,
                 th: Thresholds = THRESHOLDS) -> list[Alert]:
    """Alerts for one forecast, most serious and soonest first. `challenger` is the independent second
    model's forecast from the same origin; without it there is no conflicting-signals alert."""
    cur = _with_previous(current, previous)
    alerts = [*_spike(cur, "high", th.spike_high_rise, th.spike_high_level, th),
              *_spike(cur, "low", th.spike_low_rise, th.spike_low_level, th),
              *_revision(cur, th), *_regulation(cur, th), *_uncertainty(cur, th), *_conflict(cur, challenger, th),
              *_stale(cur, th)]
    alerts += _expert_reviews(cur, alerts, th)
    return sorted(alerts, key=lambda a: (a.severity != "review", a.window_start_utc))


def build_history(alerts_by_origin: dict[pd.Timestamp, list[Alert]]) -> tuple[list[SituationHour], list[Situation]]:
    """Per-hour counts, plus each situation once. A situation runs on while the next hour's forecast
    raises the same kind of alert with the same title for an overlapping window."""
    hours: list[SituationHour] = []
    situations: list[Situation] = []
    open_now: dict[tuple[str, str], list[Situation]] = {}
    for origin in sorted(alerts_by_origin):
        alerts = alerts_by_origin[origin]
        if alerts:
            review = sum(a.severity == "review" for a in alerts)
            hours.append(SituationHour(origin_utc=origin, review=review, watch=len(alerts) - review))
        still_open: dict[tuple[str, str], list[Situation]] = {}
        for alert in alerts:
            key = (alert.kind, alert.title)
            running = next((s for s in open_now.get(key, []) if pd.Timestamp(s.last_origin_utc) == origin - HOUR
                            and alert.window_start_utc < s.alert.window_end_utc
                            and s.alert.window_start_utc < alert.window_end_utc), None)
            if running is None:
                running = Situation(first_origin_utc=origin, last_origin_utc=origin, alert=alert)
                situations.append(running)
            else:
                running.last_origin_utc = origin
            still_open.setdefault(key, []).append(running)
        open_now = still_open
    return hours, situations
